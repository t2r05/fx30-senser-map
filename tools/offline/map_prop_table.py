#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
map_prop_table.py —— 解出 appFw.so 里的「属性访问器表」：
  .data.rel.ro 中 0x58 字节/条，结构
     +0x00  u64  property id
     +0x08  fn   attach/create
     +0x10..+0x48  8 个访问器桩（set/get 成对 + copy/sync）
     +0x50  fn   detach/destroy
  每个桩体是 adrp+ldr/str 形式，直接指向 .bss 里的 u32 全局。
输出：id -> 桩地址 -> .bss 目标地址。

用法: map_prop_table.py [FX30|FX3|A6700] [--dump=0xEE,0xEF]
"""
import sys, struct, os
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
STRIDE = 0x58
NSTUB = 8


def load(path):
    with open(path, 'rb') as f:
        e = ELFFile(f)
        secs = {}
        for s in e.iter_sections():
            if s['sh_size'] and s['sh_type'] in ('SHT_PROGBITS', 'SHT_NOBITS'):
                secs[s.name] = (s['sh_addr'], s['sh_size'], s['sh_type'])
        dsec = {}
        for s in e.iter_sections():
            if s['sh_type'] == 'SHT_PROGBITS':
                dsec[s.name] = (s['sh_addr'], s.data())
    return secs, dsec


def find_table(dr_base, d, t0, t1):
    """扫描 stride=0x58 的记录：id 小、8 个桩都落在 .text。"""
    recs = []
    n = len(d)
    for i in range(0, n - STRIDE, 8):
        idv = struct.unpack_from('<Q', d, i)[0]
        if not (0 <= idv <= 0x2000):
            continue
        ok = True
        stubs = []
        for k in range(NSTUB):
            v = struct.unpack_from('<Q', d, i + 0x10 + k * 8)[0]
            if not (t0 <= v < t1):
                ok = False
                break
            stubs.append(v)
        if not ok:
            continue
        nxt = struct.unpack_from('<Q', d, i + STRIDE)[0] if i + STRIDE + 8 <= n else None
        recs.append((dr_base + i, idv, stubs, nxt))
    return recs


def chains(recs):
    """只保留 id 连续递增的链。"""
    by_addr = {r[0]: r for r in recs}
    out = []
    for a, idv, stubs, nxt in recs:
        if nxt is None:
            continue
        nx = by_addr.get(a + STRIDE)
        if nx and nx[1] == idv + 1:
            out.append((a, idv, stubs))
    # 补最后一条
    if out:
        last = max(out, key=lambda x: x[0])
        for a, idv, stubs, nxt in recs:
            if a == last[0] + STRIDE and idv == last[1] + 1:
                out.append((a, idv, stubs))
    return out


def decode_stub(md, code, base, va, bss_lo, bss_hi):
    """解码单桩，返回它读写的 .bss 目标地址列表。"""
    off = va - base
    blob = code[off:off + 32]
    page = None
    tgts = []
    for ins in md.disasm(blob, va):
        if ins.mnemonic == 'adrp':
            page = ins.operands[1].imm
        elif ins.mnemonic in ('ldr', 'str', 'ldrb', 'strb', 'ldrh', 'strh'):
            mem = ins.operands[1].mem
            if page is None:
                continue
            a = page + mem.disp
            if bss_lo <= a < bss_hi:
                tgts.append((a, ins.mnemonic))
        elif ins.mnemonic in ('ret', 'b'):
            break
    return tgts


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'FX30'
    only = None
    for a in sys.argv[2:]:
        if a.startswith('--dump='):
            only = set(int(x, 0) for x in a.split('=', 1)[1].split(','))
    path = FILES[name]
    secs, dsec = load(path)
    t0, tsz, _ = secs['.text']
    t1 = t0 + tsz
    dr_b, dr_d = dsec['.data.rel.ro']
    bss_lo, bss_sz, _ = secs['.bss']
    bss_hi = bss_lo + bss_sz

    recs = find_table(dr_b, dr_d, t0, t1)
    ch = chains(recs)
    print('# %s  候选记录 %d 条 | 连续链内 %d 条' % (name, len(recs), len(ch)))
    if not ch:
        return
    ids = [c[1] for c in ch]
    print('# id 范围 0x%X .. 0x%X  (共 %d)  连续=%s' %
          (min(ids), max(ids), len(ids), (max(ids) - min(ids) + 1) == len(ids)))
    print('# 记录基址 0x%08X   末条 0x%08X  表长 0x%X' % (ch[0][0], ch[-1][0], ch[-1][0] - ch[0][0] + STRIDE))

    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    code = dsec['.text'][1]
    tbase = t0

    out = []
    for a, idv, stubs in ch:
        allt = []
        for s in stubs:
            allt.append(decode_stub(md, code, tbase, s, bss_lo, bss_hi))
        flat = [t for lst in allt for t in lst]
        prim = [t for t in flat if t[1] in ('str', 'strb', 'strh')]
        rd = [t for t in flat if t[1] in ('ldr', 'ldrb', 'ldrh')]
        out.append((idv, a, flat, prim, rd))
        if only is None or idv in only:
            print('\n## id 0x%04X  记录 0x%08X' % (idv, a))
            for k, s in enumerate(stubs):
                tg = allt[k]
                print('   stub[%d] 0x%08X -> %s' % (k, s, ', '.join('%s 0x%X' % (m, x) for x, m in tg) or '-'))

    tsv = os.path.join('diff3_wb', 'prop_table_%s.tsv' % name)
    os.makedirs('diff3_wb', exist_ok=True)
    with open(tsv, 'w', encoding='utf-8') as f:
        f.write('id\trecord_va\tbss_targets\tset_count\tget_count\n')
        for idv, a, flat, prim, rd in out:
            uniq = sorted(set(x for x, _ in flat))
            f.write('0x%04X\t0x%08X\t%s\t%d\t%d\n' %
                    (idv, a, ' '.join('0x%X' % u for u in uniq), len(set(x for x, _ in prim)), len(set(x for x, _ in rd))))
    print('\n# 写出 %s  (%d 条)' % (tsv, len(out)))
    # bss 覆盖统计
    allb = set()
    for _, _, flat, _, _ in out:
        allb |= set(x for x, _ in flat)
    print('# 覆盖 .bss 不同 u32 槽位 %d 个' % len(allb))


if __name__ == '__main__':
    main()
