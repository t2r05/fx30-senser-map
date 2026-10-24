#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
attr_three_gen.py —— 三代属性访问器表对照 + 驱动模式属性地址导出

三代结构（2026-10-24 实测）：

    FX30 / FX3   基址 0x0402EB20  stride 0x58 (11 槽)  id 在 +0x28，10 个访问器
    A6700        基址 0x04818040  stride 0x50 (10 槽)  无 id 字段，下标即 id
    A7C2         基址 0x0571A578  stride 0x68 (13 槽)  无 id 字段，下标即 id

旧文档把 FX30 的「id 字段地址 0x0402EB48」当成了「记录起点」，导致
所有字段偏移整体错 0x28；步长 0x58 没错，所以按 id 定位一直是对的。

输出：
    audit_raw/attr_three_gen.tsv   机型 / id / 名称 / 表内偏移 / 访问器数 / .bss 地址(去重)
    audit_raw/attr_three_gen.txt   人类可读对照
"""
import os
import sys

import numpy as np
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'audit_raw')

REL = 'firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so'
LAYOUT = {                      # model: (dir, table_base, stride_bytes, id_slot or None)
    'FX30': ('fw/out', 0x0402EB20, 0x58, 5),
    # FX3 基址不是 FX30 同址！FX3 的 .data.rel.ro 起点比 FX30 低 0x3D38，
    # 表基址随之 = 0x0402EB20 - 0x3D38 = 0x0402ADE8（校验：前 6 条 +0x28 = 0..5）
    'FX3': ('fw/fx3out', 0x0402ADE8, 0x58, 5),
    'A6700': ('fw/a6700out', 0x04818040, 0x50, None),
    'A7C2': ('fw/a7c2out', 0x0571A578, 0x68, None),
}
# 关注的属性 id（按各机型实际 BKID id）
WATCH = {
    'FX30': [(0x02AF, 'menu_drive_mode'), (0x02B1, 'dial_hi'), (0x02B3, 'dial_mid'),
             (0x02B5, 'dial_lo'), (0x04B8, 'cont_shooting'), (0x04BA, 'cont_limited'),
             (0x0278, 'self_timer')],
    'FX3': [(0x02AF, 'menu_drive_mode'), (0x02B1, 'dial_hi'), (0x04B8, 'cont_shooting'),
            (0x04BA, 'cont_limited')],
    'A6700': [(0x02B4, 'menu_drive_mode'), (0x02B6, 'dial_hi'), (0x04B9, 'cont_shooting'),
              (0x04BB, 'cont_limited'), (0x12D5, 'dial_hi_plus')],
    'A7C2': [(0x02B4, 'menu_drive_mode'), (0x02B6, 'dial_hi'), (0x04B9, 'cont_shooting'),
             (0x04BB, 'cont_limited'), (0x12D1, 'dial_hi_plus')],
}
R_RELATIVE = 1027


def load(d):
    path = os.path.join(ROOT, d, REL)
    f = open(path, 'rb')
    e = ELFFile(f)
    dr = e.get_section_by_name('.data.rel.ro')
    base = dr['sh_addr']
    raw = dr.data()
    n = len(raw) // 8
    vals = np.frombuffer(raw[:n * 8], dtype='<u8').copy()
    rel = e.get_section_by_name('.rela.dyn')
    offs, adds = [], []
    if rel is not None:
        for r in rel.iter_relocations():
            if r['r_info_type'] != R_RELATIVE:
                continue
            o = r['r_offset']
            if base <= o < base + n * 8:
                offs.append((o - base) // 8)
                adds.append(r['r_addend'] & 0xFFFFFFFFFFFFFFFF)
    if offs:
        vals[np.array(offs, dtype=np.int64)] = np.array(adds, dtype=np.uint64)
    secs = {}
    for nm in ('.text', '.rodata', '.data', '.bss'):
        s = e.get_section_by_name(nm)
        if s is not None:
            secs[nm] = (s['sh_addr'], s['sh_addr'] + s['sh_size'])
    tdata = e.get_section_by_name('.text').data()
    f.close()
    return vals, base, secs, tdata


MD = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def bss_hits(vals, base, secs, tdata, func_addr, maxins=48):
    """反汇编 func_addr 前 maxins 条指令，返回其访问到的 .bss 地址集合"""
    tlo, thi = secs['.text']
    if not (tlo <= func_addr < thi):
        return set()
    off = func_addr - tlo
    ins = list(MD.disasm(tdata[off:off + maxins * 4], func_addr))
    blo, bhi = secs['.bss']
    out, page = set(), None
    for i in ins:
        if i.mnemonic == 'adrp':
            try:
                page = int(i.op_str.split(',')[1].strip().lstrip('#'), 0)
            except Exception:  # noqa: BLE001
                page = None
            continue
        if page is None:
            continue
        if i.mnemonic in ('ldr', 'str', 'ldrb', 'strb', 'ldrh', 'strh',
                          'add', 'ldrsb', 'ldrsw', 'ldurb', 'sturb'):
            for o in i.op_str.split(',')[1:]:
                o = o.strip().lstrip('#')
                if ']' in o:
                    o = o.split(']')[0].strip().lstrip('#')
                try:
                    x = int(o, 0)
                except Exception:  # noqa: BLE001
                    continue
                a = page + x if x < 0x1000 else x
                if blo <= a < bhi:
                    out.add(a)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    lines = []
    rows = []
    for model, (d, tbase, stride, id_slot) in LAYOUT.items():
        path = os.path.join(ROOT, d, REL)
        if not os.path.exists(path):
            lines.append('%s: 缺固件' % model)
            continue
        vals, base, secs, tdata = load(d)
        n = len(vals)
        nslot = stride // 8
        lines.append('')
        lines.append('=' * 76)
        lines.append('=== %s ===  表基址 %#x  stride %#x (%d 槽)  id_slot=%s'
                     % (model, tbase, stride, nslot, id_slot))
        for rid, label in WATCH.get(model, []):
            a = tbase + rid * stride
            i = (a - base) // 8
            if i < 0 or i + nslot > n:
                lines.append('  id %#06x %-16s 越界' % (rid, label))
                continue
            rec = [int(v) for v in vals[i:i + nslot]]
            if id_slot is not None:
                got = rec[id_slot]
                idok = (got == rid)
                ptrs = [v for k, v in enumerate(rec) if k != id_slot]
            else:
                got = None
                idok = True
                ptrs = rec
            hits = set()
            for v in ptrs:
                hits |= bss_hits(vals, base, secs, tdata, v)
            uni = sorted(hits)
            lines.append('  id %#06x %-16s @%#010x  槽=%d  指针=%d  访问器命中 .bss=%d'
                         % (rid, label, a, nslot, len(ptrs), len(uni)))
            if id_slot is not None:
                lines.append('        记录内 id=%#x %s' % (got, 'OK' if idok else 'MISMATCH'))
            if uni:
                lines.append('        .bss: %s' % ' '.join('%x' % x for x in uni[:16]))
                rows.append((model, rid, label, a, nslot, len(uni),
                             ' '.join('%x' % x for x in uni)))
            else:
                rows.append((model, rid, label, a, nslot, 0, ''))

    dst_tsv = os.path.join(OUT, 'attr_three_gen.tsv')
    with open(dst_tsv, 'w', encoding='utf-8') as fh:
        fh.write('model\tid\tlabel\ttable_addr\tslots\tn_bss\tbss_addrs\n')
        for r in rows:
            fh.write('%s\t%d\t%s\t%#x\t%d\t%d\t%s\n' % r)

    dst_txt = os.path.join(OUT, 'attr_three_gen.txt')
    with open(dst_txt, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('\n写出 %s\n     %s' % (dst_tsv, dst_txt))


if __name__ == '__main__':
    sys.exit(main())
