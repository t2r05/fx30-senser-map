#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_prm_key.py · 第六期 T1 第 3 步：用 0x02CFxxxx 键找 {key -> 存储} 表

背景：T14_bss_callers 里出现过 `mov w24,#0xc33 ; movk w24,#0x2cf,lsl#16`（键 0x02CF0C33），
      说明 PRM/BKID 用 0x02CF0000|id 的空间做键。本脚本：
  1) 搜 4 个 available id 的键（0x02CF0C2C/2D/2E/33）在文件里的 4 字节出现位置
  2) 对每个命中，dump ±0x40 字节（u32 视图 + u64 视图）
  3) 判断条目里是否出现 .bss 地址或小整数默认值
只读 fw/。结果写 audit_raw/T15_task1_key.txt + tmp01 副本。
"""
import os
import struct
import sys

import numpy as np
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task1_key.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task1_key.txt"
BSS_LO, BSS_SZ = 0x04B6E738, 0x0525B2C0
IDS = [0x0C2C, 0x0C2D, 0x0C2E, 0x0C33]
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()
    elf = ELFFile(open(APPFW, "rb"))
    secs = []
    for s in elf.iter_sections():
        if s["sh_size"] and s["sh_type"] != "SHT_NOBITS":
            secs.append((s.name, s["sh_offset"], s["sh_size"], s["sh_addr"]))
    secs.sort(key=lambda x: x[1])

    def off2va(o):
        for name, off, size, addr in secs:
            if off <= o < off + size:
                return addr + (o - off), name
        return None, None

    w("=" * 78)
    w("T15 · T1 第3步 · 0x02CFxxxx 键 -> 条目")
    w("=" * 78)
    for i in IDS:
        key = struct.pack("<I", 0x02CF0000 | i)
        pos = []
        j = data.find(key)
        while j >= 0:
            pos.append(j)
            j = data.find(key, j + 1)
        w("[key 0x%08X] id 0x%04X  命中 %d 处" % (0x02CF0000 | i, i, len(pos)))
        for p in pos[:4]:
            va, sec = off2va(p)
            w("    文件偏移 0x%X  vaddr 0x%X (%s)" % (p, va or 0, sec))
            base = (p // 8) * 8
            for k in range(-4, 5):
                q = base + k * 8
                if q < 0 or q + 8 > len(data):
                    continue
                v64 = struct.unpack("<Q", data[q:q + 8])[0]
                lo = struct.unpack("<I", data[q:q + 4])[0]
                hi = struct.unpack("<I", data[q + 4:q + 8])[0]
                mark = ""
                if BSS_LO <= v64 < BSS_LO + BSS_SZ:
                    mark = "<.bss 0x%X>" % v64
                elif BSS_LO <= lo < BSS_LO + BSS_SZ:
                    mark = "<.bss 0x%X (low32)>" % lo
                w("      %+#4X 0x%08X: q=%016X  u32=[%08X, %08X]  %s"
                  % (q - p, q, v64, lo, hi, mark))
        w()
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
