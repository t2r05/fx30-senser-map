#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_prm_multi.py · 第六期 T1 补充：multi 家族所在的第二张 {key -> .bss} 表

已知 multi0/1/2 的键 0x02CF0C30/31/32 在文件偏移 0x40F47D0 一带（另一张表），
本脚本以 0x40F47DC 为种子按 0x28 步长双向扩展，打印该表全部条目，
用于确定 multi3 的 id 与 .bss 地址。
只读 fw/。结果写 audit_raw/T15_task1_multi.txt + tmp01 副本。
"""
import os
import struct
import sys

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task1_multi.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task1_multi.txt"
SEED = 0x40F4800
ESZ = 0x28
BSS_LO, BSS_SZ = 0x04B6E738, 0x0525B2C0
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()

    def ent(p):
        t = struct.unpack("<I", data[p:p + 4])[0]
        key = struct.unpack("<I", data[p + 4:p + 8])[0]
        p1 = struct.unpack("<Q", data[p + 0x10:p + 0x18])[0]
        p2 = struct.unpack("<Q", data[p + 0x18:p + 0x20])[0]
        idx = struct.unpack("<I", data[p + 0x20:p + 0x24])[0]
        return t, key, p1, p2, idx

    def valid(p):
        if p < 0 or p + ESZ > len(data):
            return False
        t, key, p1, p2, idx = ent(p)
        return t == 3 and (key & 0xFFFF0000) == 0x02CF0000

    lo = SEED
    while valid(lo - ESZ):
        lo -= ESZ
    hi = SEED
    while valid(hi + ESZ):
        hi += ESZ

    w("=" * 78)
    w("T15 · T1 补充 · multi 家族所在的第二张注册表")
    w("=" * 78)
    w("表范围 0x%X-0x%X，条目 %d 个" % (lo, hi, (hi - lo) // ESZ + 1))
    w()
    w("    %-11s %-7s %-12s %-12s %-7s" % ("entry@", "id", "bss_ptr1", "bss_ptr2", "index"))
    for p in range(lo, hi + 1, ESZ):
        t, key, p1, p2, idx = ent(p)
        i = key & 0xFFFF
        mark = " ★" if 0x0C2C <= i <= 0x0C40 else ""
        w("    0x%08X  0x%04X  0x%08X   0x%08X   %-7d%s" % (p, i, p1, p2, idx, mark))
    w()
    w("[核对] 该表 .bss 指针是否都在 .bss 内：%s"
      % all(BSS_LO <= ent(p)[2] < BSS_LO + BSS_SZ for p in range(lo, hi + 1, ESZ)))
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
