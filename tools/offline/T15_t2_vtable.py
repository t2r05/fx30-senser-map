#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_t2_vtable.py · 第六期 T2 路线A：访问器桩是否被放进函数表（vtable/dispatch）

背景：T15_t2_track.py 显示 12 个 .bss 地址只有 adrp 直连的桩内读写，
      且 T14_bss_callers 显示直接 `bl` 到桩 = 0 处 ⇒ 桩很可能通过函数表间接调用。
本脚本：
  1) 全文件搜 qword == 各访问器桩地址
  2) 对命中的表，dump 其上下文，并统计该表里相邻条目（推测 stride）
  3) 搜 adrp 引用该表页的代码，列出所在函数
只读 fw/。结果写 audit_raw/T15_task2_vtable.txt + tmp01 副本。
"""
import collections
import os
import struct
import sys

import numpy as np
from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task2_vtable.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task2_vtable.txt"

STUBS = {
    "get 0x0C2C": 0x028C145C, "set 0x0C2C": 0x028C1450,
    "get 0x0C2D": 0x028C13D8, "set 0x0C2D": 0x028C13CC,
    "get 0x0C2E": 0x028C1354, "set 0x0C2E": 0x028C1348,
    "get 0x0C33": 0x02919354,
}
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

    def va2off(v):
        for name, off, size, addr in secs:
            if addr <= v < addr + size:
                return off + (v - addr), name
        return None, None

    u64 = np.frombuffer(data[:len(data) // 8 * 8], dtype="<u8")
    w("=" * 78)
    w("T15 · T2 路线A · 访问器桩的 qword 引用（函数表）")
    w("=" * 78)
    table_pages = set()
    for tag, a in STUBS.items():
        pos = np.nonzero(u64 == np.uint64(a))[0]
        w("[%s] 0x%X  qword 引用 %d 处 %s"
          % (tag, a, len(pos), ", ".join("0x%X" % (int(p) * 8) for p in pos[:6])))
        for p in pos[:3]:
            fo = int(p) * 8
            va, sec = off2va(fo)
            w("    表位置 文件 0x%X  vaddr 0x%X（%s）" % (fo, va or 0, sec))
            if va:
                table_pages.add(va & ~0xFFF)
            for k in range(-2, 3):
                q = fo + k * 8
                if q < 0 or q + 8 > len(data):
                    continue
                v = struct.unpack("<Q", data[q:q + 8])[0]
                mark = ""
                if v in STUBS.values():
                    mark = " <stub>"
                w("      %+#4X 0x%X: %016X%s" % (q - fo, q, v, mark))
    w()

    w("[2] 引用这些表页的代码（adrp 目标 = 表页）")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    ts = elf.get_section_by_name(".text")
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))
    cnt = collections.Counter()
    sites = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        page = ins.operands[1].imm & ~0xFFF
        if page in table_pages:
            j = i
            while j > 0 and insns[j - 1].mnemonic != "ret":
                j -= 1
            cnt[insns[j].address] += 1
            sites.append((ins.address, insns[j].address, page))
    w("    表页：%s" % ", ".join("0x%X" % p for p in sorted(table_pages)))
    w("    引用点 %d 处，涉及函数 %d 个" % (len(sites), len(cnt)))
    for a, f, p in sites[:30]:
        w("      0x%08X  func=0x%08X  page=0x%X" % (a, f, p))
    if len(sites) > 30:
        w("      ... 其余 %d 处略" % (len(sites) - 30))
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
