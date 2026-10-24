#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bkid_drive_compare.py — 四机型 BKID 表里「驱动模式」相关项的归一化对照

解决的问题：
  各机型 BKID 表的**命名规范不同**，直接按大写关键词筛会漏掉：
    FX30 / FX3 : `BKID_APP_setting_drive_mode_cont_shooting`     （小写）
    A7C2       : `BKID_APP_SETTING_DRIVE_MODE_CONT_SHOOTING`     （全大写）
  本脚本按**大小写不敏感**筛选，再归一化成统一 key 做集合对照。

用法：
  python bkid_drive_compare.py                # 全部四机型，输出对照
  python bkid_drive_compare.py --dump A7C2    # 只列某机型的全部匹配项
  python bkid_drive_compare.py --pat cont     # 只看含某子串的项
"""
import argparse
import os
import re
import struct
import sys
from collections import OrderedDict

from elftools.elf.elffile import ELFFile

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = 'fw/%s/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so'
MODELS = OrderedDict([
    ('FX30', BASE % 'out'),
    ('FX3', BASE % 'fx3out'),
    ('A6700', BASE % 'a6700out'),
    ('A7C2', BASE % 'a7c2out'),
])

# 解包后的固件目录根：优先 $FW_ROOT，其次脚本所在目录往上找
def _fw_root():
    cand = os.environ.get('FW_ROOT')
    if cand and os.path.isdir(cand):
        return cand
    for up in (ROOT, os.path.join(ROOT, '..'), os.path.join(ROOT, '..', '..'),
               os.path.join(ROOT, '..', '..', '..')):
        if os.path.isdir(os.path.join(up, 'fw', 'out')):
            return up
    return ROOT


FW_ROOT = _fw_root()


def load_rows(path):
    """扫 {char* name, u32 id, u32 meta} 表，返回 [(va, id, meta, name)]"""
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        secs = {s.name: s for s in elf.iter_sections() if s['sh_type'] == 'SHT_PROGBITS'}
        ro = secs['.rodata']
        ro_d = ro.data()
        ro_a = ro['sh_addr']
        ro_end = ro_a + len(ro_d)
        dr = secs['.data.rel.ro']
        d = dr.data()
        base = dr['sh_addr']

        rows = []
        seen = set()
        for i in range(0, len(d) - 16, 8):
            ptr = struct.unpack_from('<Q', d, i)[0]
            if not (ro_a <= ptr < ro_end):
                continue
            idv = struct.unpack_from('<I', d, i + 8)[0]
            meta = struct.unpack_from('<I', d, i + 12)[0]
            if not (0 < idv < 0x10000):
                continue
            off = ptr - ro_a
            s = ro_d[off:off + 200].split(b'\x00')[0]
            if len(s) < 3:
                continue
            try:
                txt = s.decode('latin1')
            except Exception:
                continue
            if not all(32 <= ord(c) < 127 for c in txt):
                continue
            key = (txt, idv)
            if key in seen:
                continue
            seen.add(key)
            rows.append((base + i, idv, meta, txt))
    return rows


def norm(name):
    """归一化：去 BKID_ 前缀、全大写、统一 MR_ / SETTING_ 差异"""
    n = name
    for p in ('BKID_APP_', 'BKID_'):
        if n.startswith(p):
            n = n[len(p):]
    n = n.upper()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', metavar='MODEL')
    ap.add_argument('--pat', default='drive_mode')
    ap.add_argument('--csv')
    a = ap.parse_args()

    pat = a.pat.lower()
    data = OrderedDict()
    for m, rel in MODELS.items():
        if a.dump and m != a.dump:
            continue
        p = os.path.join(FW_ROOT, rel)
        if not os.path.exists(p):
            print('[!] %s 缺文件：%s' % (m, p))
            continue
        rows = load_rows(p)
        sel = [r for r in rows if pat in r[3].lower()]
        data[m] = {'rows': rows, 'sel': sel}
        print('[%s] 表 %d 条，含 %r 的 %d 条' % (m, len(rows), pat, len(sel)))

    if a.dump:
        rows = data[a.dump]['sel']
        print('\n%-12s %-8s %-6s %s' % ('va', 'id', 'meta', 'name'))
        for va, idv, meta, txt in sorted(rows, key=lambda r: r[1]):
            print('0x%08X   0x%04X   %-6d %s' % (va, idv, meta, txt))
        return 0

    # ---- 归一化集合对照
    sets = OrderedDict()
    for m, v in data.items():
        s = {}
        for va, idv, meta, txt in v['sel']:
            s.setdefault(norm(txt), []).append((idv, txt))
        sets[m] = s

    allkeys = sorted({k for s in sets.values() for k in s})

    print('\n' + '=' * 100)
    print('一、归一化名称覆盖率（哪台机器有 / 没有）')
    print('=' * 100)
    mods = list(sets.keys())
    print('%-58s ' % '归一化名称' + ' '.join('%6s' % m for m in mods))
    print('-' * 100)
    for k in allkeys:
        marks = ['   ✓  ' if k in sets.get(m, {}) else '   ·  ' for m in mods]
        ids = [sets[m][k][0][0] if k in sets.get(m, {}) else None for m in mods]
        idtxt = ' '.join(('%04X' % i).rjust(6) if i is not None else '     -' for i in ids)
        print('%-58s ' % k[:58] + idtxt)

    print('\n' + '=' * 100)
    print('二、归属统计')
    print('=' * 100)
    for m in mods:
        s = sets[m]
        cnt = {mm: sum(1 for k in s if k in sets.get(mm, {})) for mm in mods}
        print('%-6s 唯一 %3d 条；' % (m, sum(1 for k in s if all(k not in sets.get(o, {}) for o in mods if o != m)))
              + '  与各机型共有：' + '  '.join('%s=%d' % (o, cnt[o]) for o in mods if o != m))

    print('\n' + '=' * 100)
    print('三、关键项 id 对照（连拍四档 / 自拍定时 / 单张）')
    print('=' * 100)
    keys = ['SETTING_DRIVE_MODE_CONT_SHOOTING', 'SETTING_DRIVE_MODE_SELF_TIMER',
            'SETTING_DRIVE_MODE_1_IMAGE_SHOOTING', 'SETTING_DRIVE_MODE_CONT_SELF_TIMER',
            'LIMIT_CONT_SHOOTING_HI_PLUS', 'LIMIT_CONT_SHOOTING_HI',
            'LIMIT_CONT_SHOOTING_MID', 'LIMIT_CONT_SHOOTING_LO',
            'LIMIT_CONTINUOUS_SHOOTING_HI_PLUS', 'LIMIT_CONTINUOUS_SHOOTING_HI',
            'LIMIT_CONTINUOUS_SHOOTING_MID', 'LIMIT_CONTINUOUS_SHOOTING_LO',
            'CONT_SHOOTING_LIMITED', 'DIAL_POS_CONT_SHOOTING_HI_PLUS',
            'DL_HI_PLUS_IN_ELECTRIC_SHUTTER', 'CONT_SHOOTING_NON_LIMITED']
    print('%-46s ' % '归一化名称' + ' '.join('%6s' % m for m in mods))
    print('-' * 100)
    for k in keys:
        row = []
        for m in mods:
            hit = None
            for kk, vv in sets[m].items():
                if kk.endswith(k) or k in kk:
                    hit = vv[0][0]
                    break
            row.append(('%04X' % hit).rjust(6) if hit else ('-').rjust(6))
        flag = '' if any(x.strip() != '-' for x in row) else '   (四机型皆无)'
        print('%-46s ' % k + ' '.join(row) + flag)

    if a.csv:
        import csv
        with open(a.csv, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['归一化名称'] + mods)
            for k in allkeys:
                w.writerow([k] + [('%04X' % sets[m][k][0][0]) if k in sets.get(m, {}) else '' for m in mods])
        print('\n[+] CSV: %s' % a.csv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
