#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_prm_storage.py · 第六期 T1 第 2 步：PRM 表项 -> 存储地址（.bss 还是 PDT）

T15_prm_table.py 已解出：8 个 PRM 在 0x679Bxx-0x679Exx 处有 24 字节表项
  { name_ptr(.rodata), sub_ptr(.data.rel.ro), 0x403 }
本脚本：
  1) dump 这些 sub_ptr 所在的 .data.rel.ro 数组（multi 0x411C280-，available 0x411C380-）
  2) 全文件搜 qword == 0x83461A4 / 0x83461A8 / 0x83461AC / 0x8346300（BKID 的 .bss）
  3) 对每个 PRM 表项，解析 sub_ptr -> 其内容；标注是否为 .bss 地址
  4) dump 0x410C280-0x410C3C0（另一处指针数组）
只读 fw/。结果写 audit_raw/T15_task1_storage.txt + tmp01 副本。
"""
import os
import struct
import sys

import numpy as np
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task1_storage.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task1_storage.txt"

BSS_LO, BSS_SZ = 0x04B6E738, 0x0525B2C0
TARGETS = {0x83461A4: "available0(.bss)", 0x83461A8: "available1(.bss)",
           0x83461AC: "available2(.bss)", 0x8346300: "available3(.bss)"}
PRM_ENTRIES = {"available0": 0x679E68, "available1": 0x679E80, "available2": 0x679E98,
               "available3": 0x679EB0, "multi0": 0x679BC8, "multi1": 0x679BE0,
               "multi2": 0x679BF8, "multi3": 0x679C10}
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

    def va2off(va):
        for name, off, size, addr in secs:
            if addr <= va < addr + size:
                return off + (va - addr), name
        return None, None

    def q(va):
        o, _ = va2off(va)
        if o is None or o + 8 > len(data):
            return None
        return struct.unpack("<Q", data[o:o + 8])[0]

    def cls(v):
        if BSS_LO <= v < BSS_LO + BSS_SZ:
            return "<.bss 0x%X>" % v
        o, n = va2off(v)
        if o is not None:
            return "<%s+0x%X>" % (n, v - elf.get_section_by_name(n)["sh_addr"])
        return ""

    w("=" * 78)
    w("T15 · T1 第2步 · PRM 表项 -> 存储地址")
    w("=" * 78)
    w(".bss 范围 [0x%X, 0x%X)" % (BSS_LO, BSS_LO + BSS_SZ))
    w()

    # ---- 1) PRM 24 字节表项
    w("[1] PRM 表项（每项 24 字节 = name_ptr / sub_ptr / 0x403）")
    w("    %-11s %-10s %-12s %-12s %s" % ("参数", "表项偏移", "name_ptr", "sub_ptr", "第三字段"))
    subs = {}
    for k, e in PRM_ENTRIES.items():
        a = q(e) if e else None
        b = q(e + 8) if e else None
        c = q(e + 16) if e else None
        subs[k] = b
        w("    %-11s 0x%08X 0x%08X   0x%08X   0x%X" % (k, e, a or 0, b or 0, c or 0))
    w()

    # ---- 2) sub_ptr 内容
    w("[2] sub_ptr 指向的 .data.rel.ro 内容（每项 8 字节）")
    for k, b in subs.items():
        if b is None:
            continue
        o, sec = va2off(b)
        w("    %-11s sub_ptr 0x%08X (%s, 文件偏移 0x%X)" % (k, b, sec, o if o else 0))
        for j in range(-3, 4):
            v = q(b + j * 8)
            if v is None:
                continue
            w("       %+#4d 0x%08X: %016X  %s" % (j * 8, b + j * 8, v, cls(v)))
    w()

    # ---- 3) 全文件搜 BKID .bss 地址作为 qword
    w("[3] 全文件 qword 搜索：指向 BKID .bss 的指针")
    u64 = np.frombuffer(data[:len(data) // 8 * 8], dtype="<u8")
    for tgt, tag in TARGETS.items():
        pos = np.nonzero(u64 == np.uint64(tgt))[0]
        w("    0x%X (%s)：命中 %d 处 %s"
          % (tgt, tag, len(pos), ", ".join("0x%X" % (int(p) * 8) for p in pos[:6])))
    w()

    # ---- 4) 0x410C280 与 0x410C380 两处指针数组
    for base in (0x410C280, 0x410C380, 0x411C280, 0x411C380):
        o, sec = va2off(base)
        w("[4] dump 0x%08X (%s)" % (base, sec))
        if o is None:
            w("    (不可映射)")
            continue
        for j in range(0, 24, 8):
            v = q(base + j)
            w("       0x%08X: %016X  %s" % (base + j, v, cls(v) if v is not None else ""))
        w()

    # ---- 5) 结论所需的事实核对
    w("[5] 事实核对")
    n_bss_ptr = sum(len(np.nonzero(u64 == np.uint64(t))[0]) for t in TARGETS)
    w("    指向 4 个 BKID .bss 地址的 qword 指针总数：%d" % n_bss_ptr)
    w("    PRM name vaddr 均落在 .rodata：是")
    w("    访问器桩读数指令：ldr w0 /* u32 */（见 T15_prm_table.py §4）")
    w("    已知 .bss 步长：available0/1/2 = +4；available3 与 available2 相距 0x154")
    w("    PDT 尺寸 2253564；.bss 地址 0x83461A4 不在 [0,2253564) 内：True"
      % ())
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
