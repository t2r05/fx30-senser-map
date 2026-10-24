#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_prop_table.py — 在 .data.rel.ro 里定位「属性访问器表」的 stride 与范围

背景：FX30 的表已知是 0x58 字节/条（id 在 +0x00，u64；+0x08..+0x50 是访问器指针）。
      但 A6700 / A7C2 上按 0x58 找不到，说明 stride 或布局变了。
      本脚本不假设 stride，而是搜索「等距且严格 +1 递增的 u32 列」——
      这是 id 索引表最显著的特征。

方法：
  对每个候选 stride（0x10..0x200，步 8）与每个相位 start（0..stride，步 8）：
    取数列 data[start], data[start+stride], data[start+2*stride], ...
    找最长的一段「严格 +1 递增、且值 < 0x8000」的连续项。
  最优者即属性表。

用法：
  python find_prop_table.py              # 三机型都跑
  python find_prop_table.py A7C2
"""
import os
import sys

import numpy as np
from elftools.elf.elffile import ELFFile

ROOT = os.path.dirname(os.path.abspath(__file__))
REL = 'firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so'
MODELS = {
    'FX30': 'fw/out',
    'FX3': 'fw/fx3out',
    'A6700': 'fw/a6700out',
    'A7C2': 'fw/a7c2out',
}
def _fw_root():
    """解包后的固件目录根：优先 $FW_ROOT，其次脚本所在目录往上找"""
    cand = os.environ.get('FW_ROOT')
    if cand and os.path.isdir(cand):
        return cand
    for up in (ROOT, os.path.join(ROOT, '..'), os.path.join(ROOT, '..', '..'),
               os.path.join(ROOT, '..', '..', '..')):
        if os.path.isdir(os.path.join(up, 'fw', 'out')):
            return up
    return ROOT


FW_ROOT = _fw_root()
ID_MAX = 0x8000
MIN_LEN = 30


def longest_inc_run(seq):
    """返回 (长度, 起点索引)；要求严格 +1 且 < ID_MAX"""
    n = len(seq)
    if n < 2:
        return 0, 0
    ok = seq < ID_MAX
    good = np.zeros(n, dtype=bool)
    good[1:] = (seq[1:] == seq[:-1] + 1) & ok[1:] & ok[:-1]
    padded = np.concatenate(([False], good, [False]))
    d = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    if len(starts) == 0:
        return 0, 0
    lens = ends - starts
    k = int(lens.argmax())
    return int(lens[k]) + 1, int(starts[k])


def scan(model):
    path = os.path.join(FW_ROOT, MODELS[model], REL)
    if not os.path.exists(path):
        print('[!] 缺文件：%s' % path)
        return None
    with open(path, 'rb') as f:
        e = ELFFile(f)
        dr = e.get_section_by_name('.data.rel.ro')
        data = dr.data()
        base = dr['sh_addr']

    arr = np.frombuffer(data, dtype='<u4')
    best = []
    for stride in range(0x10, 0x201, 8):
        step = stride // 4          # 以 u32 为单位
        if step < 2:
            continue
        for start_byte in range(0, stride, 8):
            if start_byte % 4:
                continue
            s0 = start_byte // 4
            seq = arr[s0::step]
            L, pos = longest_inc_run(seq)
            if L >= MIN_LEN:
                best.append((L, stride, start_byte, pos, int(seq[pos])))
    best.sort(reverse=True)

    print('=== %s ===  .data.rel.ro %d B  base=%#x' % (model, len(data), base))
    if not best:
        print('    无候选（>= %d 项）' % MIN_LEN)
        return None
    seen = set()
    shown = 0
    out = None
    for L, stride, start_byte, pos, first_id in best:
        if stride in seen:
            continue
        seen.add(stride)
        addr = base + start_byte + pos * stride
        last_id = first_id + L - 1
        print('    stride=%#05x 相位=%#04x  递增 %5d 项  id %#06x..%#06x  首址 %#010x  表长 %#x'
              % (stride, start_byte, L, first_id, last_id, addr, L * stride))
        if out is None:
            out = {'stride': stride, 'lens': L, 'first_addr': addr,
                   'id0': first_id, 'id1': last_id, 'base': base, 'size': len(data)}
        shown += 1
        if shown >= 5:
            break
    return out


def main():
    want = sys.argv[1:] or list(MODELS)
    res = {}
    for m in want:
        if m not in MODELS:
            print('未知机型 %s' % m)
            continue
        res[m] = scan(m)
        print()
    if len(res) >= 2:
        print('=' * 78)
        print('汇总')
        print('=' * 78)
        print('%-7s %-9s %-8s %-22s %s' % ('机型', 'stride', '条数', 'id 范围', '首址'))
        for m, r in res.items():
            if not r:
                print('%-7s %-9s' % (m, '(未找到)'))
                continue
            print('%-7s %#05x     %-8d %#06x..%#06x        %#010x'
                  % (m, r['stride'], r['lens'], r['id0'], r['id1'], r['first_addr']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
