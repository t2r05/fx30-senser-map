#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a7c2_attr_probe.py —— 用「连续 .text 函数指针链」定位属性访问器表

为什么换判据：
    之前的 find_prop_table.py / T4 都在找「等距且严格递增的 id 列」，
    这个判据隐含假设「每条第 0 字段是 id 且 id 连续」。A7C2 上不成立，
    但属性访问器表的**本质**是「一条记录里串着若干个访问器函数指针」，
    这个特征与 id 是否连续无关。

做法：
    1. 读 .data.rel.ro 原始字节
    2. 用 .rela.dyn 的 R_AARCH64_RELATIVE 把槽位还原成运行时值
       （文件里这些位置通常是 0，真值在 r_addend）
    3. 逐槽分类：(T)EXT / (B)SS / (R)ODATA / (D)ATA / (0)零 / (?)
    4. 找连续 >=MIN_RUN 个 T 的 run，统计 run 长度与相邻 run 的间距

输出：audit_raw/A7C2_attr_probe.txt
"""
import os
import sys
from collections import Counter

import numpy as np
from elftools.elf.elffile import ELFFile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'audit_raw')

REL = 'firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so'
MODELS = {
    'FX30': 'fw/out',
    'FX3': 'fw/fx3out',
    'A6700': 'fw/a6700out',
    'A7C2': 'fw/a7c2out',
}
MIN_RUN = 6          # 连续多少个 TEXT 指针才算一条记录
R_RELATIVE = 1027


def load(model):
    """返回 (vals[runtime value per 8B slot], base, sections dict)"""
    path = os.path.join(ROOT, MODELS[model], REL)
    if not os.path.exists(path):
        raise SystemExit('缺文件 %s' % path)
    f = open(path, 'rb')
    e = ELFFile(f)
    dr = e.get_section_by_name('.data.rel.ro')
    raw = dr.data()
    base = dr['sh_addr']
    n = len(raw) // 8
    vals = np.frombuffer(raw[:n * 8], dtype='<u8').copy()

    secs = {}
    for nm in ('.text', '.rodata', '.data', '.bss', '.data.rel.ro'):
        s = e.get_section_by_name(nm)
        if s is not None:
            secs[nm] = (s['sh_addr'], s['sh_addr'] + s['sh_size'])

    # 还原 RELATIVE
    reladyn = e.get_section_by_name('.rela.dyn')
    rel_off, rel_add = [], []
    if reladyn is not None:
        for r in reladyn.iter_relocations():
            if r['r_info_type'] != R_RELATIVE:
                continue
            off = r['r_offset']
            if base <= off < base + n * 8:
                rel_off.append((off - base) // 8)
                rel_add.append(r['r_addend'] & 0xFFFFFFFFFFFFFFFF)
    if rel_off:
        vals[np.array(rel_off, dtype=np.int64)] = np.array(rel_add, dtype=np.uint64)

    meta = {'n_rel': len(rel_off), 'secs': secs}
    f.close()
    return vals, base, meta


def classify(vals, secs):
    """返回字符数组：T/B/R/D/0/?"""
    cls = np.full(len(vals), ord('?'), dtype=np.uint8)
    cls[vals == 0] = ord('0')
    for ch, nm in (('T', '.text'), ('B', '.bss'), ('R', '.rodata'), ('D', '.data')):
        if nm not in secs:
            continue
        lo, hi = secs[nm]
        cls[(vals >= lo) & (vals < hi)] = ord(ch)
    return cls


def runs_of(cls, want, min_len):
    """返回 [(start_idx, length), ...]"""
    mask = (cls == ord(want))
    if not mask.any():
        return []
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    out = []
    for s, t in zip(starts, ends):
        if t - s >= min_len:
            out.append((int(s), int(t - s)))
    return out


def probe(model, fh):
    vals, base, meta = load(model)
    cls = classify(vals, meta['secs'])
    n = len(vals)
    w = fh.write

    w('\n' + '=' * 78 + '\n')
    w('=== %s ===\n' % model)
    w('.data.rel.ro %#x  %d 槽 (8B)  RELATIVE %d 条\n' % (base, n, meta['n_rel']))
    cnt = Counter(chr(c) for c in cls)
    tot = float(n)
    w('槽分类: ' + '  '.join('%s=%d(%.1f%%)' % (k, v, v * 100 / tot)
                             for k, v in cnt.most_common()))
    w('\n')

    for min_len in (MIN_RUN, 8, 10, 12):
        rr = runs_of(cls, 'T', min_len)
        w('连续 TEXT >=%2d : %5d 条 run\n' % (min_len, len(rr)))
        if not rr:
            continue
        lens = Counter(l for _, l in rr)
        w('   run 长度分布: %s\n' % dict(sorted(lens.items())[:12]))
        starts = [s for s, _ in rr]
        if len(starts) > 1:
            gaps = Counter(b - a for a, b in zip(starts, starts[1:]))
            w('   相邻 run 起始间距 Top8: %s\n'
              % [(g, c) for g, c in gaps.most_common(8)])

    # 最可能的 stride = 间距众数；在它上面看结构
    rr = runs_of(cls, 'T', MIN_RUN)
    if len(rr) < 3:
        w('  run 太少，无法推断 stride\n')
        return
    starts = np.array([s for s, _ in rr])
    gaps = Counter(b - a for a, b in zip(starts, starts[1:]))
    stride, _ = gaps.most_common(1)[0]
    w('\n--- 主导 stride = %d 槽 (%#x B) ---\n' % (stride, stride * 8))

    # 每个 run 的「记录起始」= run 起点往前数到 stride 边界
    # 直接看：run 起点模 stride 的余数分布
    phases = Counter(int(s % stride) for s in starts)
    w('run 起点 %% stride 的相位分布: %s\n' % phases.most_common(8))

    ph, phc = phases.most_common(1)[0]
    sel = [int(s) for s in starts if s % stride == ph]
    # 记录起点 = run 起点往前推 ph 个槽（run 起点不是记录起点）
    recs = [s - ph for s in sel if s - ph >= 0]
    w('相位 %d 的 %d 条 run -> 记录起点 = run起点 - %d 槽\n' % (ph, len(sel), ph))
    if recs:
        w('首条记录 %#x\n' % (base + recs[0] * 8))
    w('\n前 8 条记录，逐槽分类 + 值：\n')
    show = min(stride, 16)
    for idx, g in enumerate(recs[:8]):
        if g + stride > n:
            continue
        w('  rec[%d] @%#x\n' % (idx, base + g * 8))
        w('    cls  ' + ''.join(chr(c) for c in cls[g:g + stride]) + '\n')
        w('    val  ' + ' '.join('%x' % int(vals[g + k]) for k in range(min(stride, show))) + '\n')

    # 首槽是否像 id：小整数且递增
    w('\n记录首槽值抽样（判断是否像 id）：\n')
    ids = [int(vals[g]) for g in recs[:24] if g < n]
    w('  %s\n' % [hex(x) for x in ids])
    # 再试第 2 槽
    ids2 = [int(vals[g + 1]) for g in recs[:24] if g + 1 < n]
    w('  第2槽: %s\n' % [hex(x) for x in ids2])


def main():
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, 'A7C2_attr_probe.txt')
    with open(dst, 'w', encoding='utf-8') as fh:
        fh.write('属性访问器表定位（连续 TEXT 指针链判据）\n')
        for m in MODELS:
            try:
                probe(m, fh)
            except Exception as exc:  # noqa: BLE001
                fh.write('\n=== %s === 出错: %r\n' % (m, exc))
            fh.flush()
    print('写出 %s' % dst)
    # 同时回显 A7C2 段
    txt = open(dst, encoding='utf-8').read()
    i = txt.find('=== A7C2 ===')
    print(txt[i:] if i >= 0 else '(没找到 A7C2 段)')


if __name__ == '__main__':
    sys.exit(main())
