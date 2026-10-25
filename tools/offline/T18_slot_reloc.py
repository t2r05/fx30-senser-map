#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T18_slot_reloc.py · 第七期 T17 补充：16 个槽的 .rela.dyn 记录（谁给槽赋值）

对每个槽 vaddr，在 .rela.dyn 里找 r_offset == 槽地址 的条目，报类型与 addend；
并统计两张注册表页内 r_offset 的重定位数量。
只读 fw/。结果写 audit_raw/T18_task17_slot_reloc.txt + tmp01 副本。
"""
import collections
import os
import sys

from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T18_task17_slot_reloc.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T18_task17_slot_reloc.txt"

SLOTS = {
    0x40FE190: "available0/slot1", 0x40FE198: "available0/slot2",
    0x40FE1B8: "available1/slot1", 0x40FE1C0: "available1/slot2",
    0x40FE1E0: "available2/slot1", 0x40FE1E8: "available2/slot2",
    0x40FE208: "available3/slot1", 0x40FE210: "available3/slot2",
    0x4104810: "multi0/slot1", 0x4104818: "multi0/slot2",
    0x4104838: "multi1/slot1", 0x4104840: "multi1/slot2",
    0x4104860: "multi2/slot1", 0x4104868: "multi2/slot2",
    0x4104888: "multi3/slot1", 0x4104890: "multi3/slot2",
}
PAGES = (0x40FE000, 0x4104000)
lines = []


def w(s=""):
    lines.append(s)


def main():
    ef = ELFFile(open(APPFW, "rb"))
    rd = ef.get_section_by_name(".rela.dyn")
    w("=" * 78)
    w("T18 · T17 补充 · 16 个槽的 .rela.dyn 记录")
    w("=" * 78)
    found = {}
    pagecnt = collections.Counter()
    for rel in rd.iter_relocations():
        off = rel["r_offset"]
        a = rel["r_addend"]
        if off in SLOTS:
            found[off] = (rel["r_info_type"], a)
        if PAGES[0] <= off < PAGES[0] + 0x1000:
            pagecnt[PAGES[0]] += 1
        if PAGES[1] <= off < PAGES[1] + 0x1000:
            pagecnt[PAGES[1]] += 1
    w("    %-12s %-14s %-8s %-12s" % ("槽 vaddr", "名称", "类型", "addend"))
    for s, nm in sorted(SLOTS.items()):
        t, a = found.get(s, ("-", None))
        w("    0x%08X   %-14s %-8s 0x%X%s"
          % (s, nm, t, a if a is not None else 0,
             "  <.bss>" if a is not None and 0x4B6E738 <= a < 0x9DC99F8 else ""))
    w()
    w("    命中 %d / 16" % len(found))
    w("    r_offset 落在注册表页 0x40FE000 的重定位：%d" % pagecnt[PAGES[0]])
    w("    r_offset 落在注册表页 0x4104000 的重定位：%d" % pagecnt[PAGES[1]])
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
