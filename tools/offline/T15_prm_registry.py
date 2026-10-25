#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_prm_registry.py · 第六期 T1 第 4 步：走完整张 {key -> 存储} 注册表

由 T15_prm_key.py 已知：注册表在文件偏移 0x40EE180 附近，条目 40(0x28) 字节，
布局（u32/u64 混合）：
  +0x00 u32 类型(恒 3)  +0x04 u32 key(0x02CF0000|id)
  +0x08 u32 0x00010000  +0x0C u32 0
  +0x10 u64 .bss 指针1  +0x18 u64 .bss 指针2
  +0x20 u32 索引        +0x24 u32 0

本脚本：
  1) 以 0x40EE180 为种子向上/向下按 40 字节扩展，找出表格边界
  2) 打印 0x0C24-0x0C3C 区间的所有键及其 .bss 地址、索引
  3) 汇总：available / multi 家族的映射表
只读 fw/。结果写 audit_raw/T15_task1_registry.txt + tmp01 副本。
"""
import os
import struct
import sys

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task1_registry.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task1_registry.txt"

SEED = 0x40EE180
ESZ = 0x28
BSS_LO, BSS_SZ = 0x04B6E738, 0x0525B2C0
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()

    def ent(p):
        if p < 0 or p + ESZ > len(data):
            return None
        t = struct.unpack("<I", data[p:p + 4])[0]
        key = struct.unpack("<I", data[p + 4:p + 8])[0]
        f8 = struct.unpack("<I", data[p + 8:p + 12])[0]
        p1 = struct.unpack("<Q", data[p + 0x10:p + 0x18])[0]
        p2 = struct.unpack("<Q", data[p + 0x18:p + 0x20])[0]
        idx = struct.unpack("<I", data[p + 0x20:p + 0x24])[0]
        return t, key, f8, p1, p2, idx

    def valid(p):
        e = ent(p)
        if e is None:
            return False
        t, key, f8, p1, p2, idx = e
        return t == 3 and (key & 0xFFFF0000) == 0x02CF0000

    lo = SEED
    while valid(lo - ESZ):
        lo -= ESZ
    hi = SEED
    while valid(hi + ESZ):
        hi += ESZ

    w("=" * 78)
    w("T15 · T1 第4步 · {key -> .bss} 注册表")
    w("=" * 78)
    n = (hi - lo) // ESZ + 1
    w("表格范围：文件偏移 0x%X - 0x%X，条目 %d 个，条目大小 0x%X" % (lo, hi, n, ESZ))
    w()

    w("[1] 全表（key / id / .bss 指针1 / 指针2 / 索引）")
    w("    %-14s %-7s %-11s %-11s %-7s %s"
      % ("entry@", "id", "bss_ptr1", "bss_ptr2", "index", "备注"))
    rows = []
    for p in range(lo, hi + 1, ESZ):
        e = ent(p)
        if e is None:
            continue
        t, key, f8, p1, p2, idx = e
        i = key & 0xFFFF
        p1c = "<.bss>" if BSS_LO <= p1 < BSS_LO + BSS_SZ else ""
        p2c = "<.bss>" if BSS_LO <= p2 < BSS_LO + BSS_SZ else ""
        rows.append((p, i, key, p1, p2, idx))
        mark = ""
        if 0x0C2C <= i <= 0x0C33:
            mark = "★"
        w("    0x%08X  0x%04X 0x%08X%s 0x%08X%s %-7d %s"
          % (p, i, p1, p1c, p2, p2c, idx, mark))
    w()

    w("[2] 0x0C2C-0x0C33 区段专表")
    w("    %-7s %-12s %-12s %-12s %s" % ("id", "注册表偏移", ".bss 指针1", ".bss 指针2", "索引"))
    for p, i, key, p1, p2, idx in rows:
        if 0x0C2C <= i <= 0x0C33:
            w("    0x%04X  0x%08X   0x%08X   0x%08X   %d" % (i, p, p1, p2, idx))
    w()

    w("[3] 事实核对")
    w("    条目里两个指针是否相等：%s"
      % all(p1 == p2 for _, _, _, p1, p2, _ in rows))
    w("    全部指针落在 .bss 范围 [0x%X,0x%X)：%s"
      % (BSS_LO, BSS_LO + BSS_SZ,
         all(BSS_LO <= p1 < BSS_LO + BSS_SZ for _, _, _, p1, _, _ in rows)))
    w("    .bss 指针步长（同 index 相邻）：见上表")
    w("=" * 78)

    for path in (OUT_MAIN, OUT_COPY):
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
