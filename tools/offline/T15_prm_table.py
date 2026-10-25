#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_prm_table.py · 第六期 T1：PRM 参数表结构 / 存储位置 / 字段宽度 / 默认值

做法（严格按 TRAE-PACK-6 §3 T1 + §7.2 顺序）：
  1) 把 8 个 PRM 名称的文件偏移映射成 vaddr（按 ELF 段 sh_offset/sh_addr）。
  2) 在全文件里搜指向该 vaddr 的 qword 指针（8 字节对齐 + 非对齐都查）。
  3) 对每个指针点，按 8 字节对齐 dump ±0x60 字节，标出哪些 qword 是"合法 vaddr"。
  4) 反汇编 available 族访问器桩，判断读数用 ldrb（u8）还是 ldr（u32）。
  5) 输出对照表：名称 / 文件偏移 / 表项地址 / 解出的 id / 存储地址 / 默认值 / 置信度。

只读 fw/。结果写 audit_raw/T15_task1_prm.txt + tmp01 副本。
用法：
  "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -u T15_prm_table.py
"""
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
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task1_prm.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task1_prm.txt"

AVAIL = [60488119, 60488168, 60488217, 60488266]
MULTI = [60486695, 60486740, 60486785, 60486830]
ACCESSOR0 = {0x0C2C: 0x028C145C, 0x0C2D: 0x028C13D8, 0x0C2E: 0x028C1354, 0x0C33: 0x02919354}
KNOWN_BSS = {0x0C2C: 0x83461A4, 0x0C2D: 0x83461A8, 0x0C2E: 0x83461AC, 0x0C33: 0x8346300}
BSS_LO, BSS_SZ = 0x04B6E738, 0x0525B2C0
PDT_SIZE = 2253564

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

    def va2off(va):
        for name, off, size, addr in secs:
            if addr <= va < addr + size:
                return off + (va - addr), name
        return None, None

    def is_va(v):
        return va2off(v)[0] is not None

    w("=" * 78)
    w("T15 · 第六期 T1 · PRM 表结构 / 存储 / 宽度 / 默认值")
    w("=" * 78)
    w("appFw.so size=%d  .bss 范围 [0x%X, 0x%X)" % (len(data), BSS_LO, BSS_LO + BSS_SZ))
    w()

    # ---- 1) 名称 -> vaddr
    w("[1] PRM 名称偏移 -> vaddr")
    names = {}
    for tag, offs in (("available", AVAIL), ("multi", MULTI)):
        for i, o in enumerate(offs):
            end = data.find(b"\x00", o)
            nm = data[o:end].decode("latin-1")
            va, sec = off2va(o)
            names[(tag, i)] = (o, va, sec, nm)
            w("    %-10s%d  文件偏移 %d  0x%X  vaddr 0x%08X (%s)  %s"
              % (tag, i, o, o, va, sec, nm[:60]))
    w()

    # ---- 2) 搜 qword 指针
    u64 = np.frombuffer(data[:len(data) // 8 * 8], dtype="<u8")
    w("[2] 指向这些 vaddr 的 qword 指针")
    ptr_hits = {}
    for (tag, i), (o, va, sec, nm) in names.items():
        pos = np.nonzero(u64 == np.uint64(va))[0]
        ptr_hits[(tag, i)] = [int(p) * 8 for p in pos]
        w("    %-10s%d  vaddr 0x%08X  命中 %d 处：%s"
          % (tag, i, va, len(pos),
             ", ".join("0x%X" % (int(p) * 8) for p in pos[:6]) + (" ..." if len(pos) > 6 else "")))
    w()

    # ---- 3) dump 表项
    w("[3] 表项 dump（8 字节对齐，±0x60；qword 若为合法 vaddr 标 <va>）")
    for (tag, i), (o, va, sec, nm) in names.items():
        hits = ptr_hits[(tag, i)]
        if not hits:
            w("    %s%d（0x%X）：无 qword 指针命中" % (tag, i, o))
            continue
        p = hits[0]
        w("    %s%d  name@0x%X  ptr@0x%X（vaddr 0x%08X/%s）"
          % (tag, i, o, p, off2va(p)[0] or 0, off2va(p)[1] or "?"))
        base = (p // 8) * 8
        for k in range(-12, 13):
            q = base + k * 8
            if q < 0 or q + 8 > len(data):
                continue
            v = struct.unpack("<Q", data[q:q + 8])[0]
            mark = ""
            vo = va2off(v)
            if vo[0] is not None:
                mark = "<va %s+0x%X>" % (vo[1], v - elf.get_section_by_name(vo[1])["sh_addr"])
            w("      %+#5X 0x%08X: %016X  %s" % (q - p, q, v, mark))
        w()

    # ---- 4) 访问器桩宽度
    ts = elf.get_section_by_name(".text")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    tf = data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]]
    w("[4] available 族访问器[0] 反汇编（判断 ldrb / ldr）")
    for i, a in ACCESSOR0.items():
        code = tf[a - ts["sh_addr"]: a - ts["sh_addr"] + 0x40]
        w("    id 0x%04X  stub 0x%08X  (.bss 已知 0x%X)" % (i, a, KNOWN_BSS.get(i, 0)))
        for ins in md.disasm(code, a):
            w("      0x%08X  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
            if ins.mnemonic in ("ret", "br"):
                break
        w()

    # ---- 5) 汇总表
    w("[5] 汇总")
    w("    %-12s %-10s %-12s %-10s %-12s %-8s" % ("参数", "文件偏移", "name vaddr", "ptr 站点", "解出存储", "宽度"))
    for (tag, i), (o, va, sec, nm) in names.items():
        hits = ptr_hits[(tag, i)]
        w("    %-12s 0x%08X   0x%08X   %-10s %-12s %-8s"
          % ("%s%d" % (tag, i), o, va,
             ("0x%X" % hits[0]) if hits else "-",
             "%s" % ("(见 dump)"), "?"))
    w()
    w("[6] 已知 .bss 对照：available0/1/2 = 0x83461A4 / 0x83461A8 / 0x83461AC（+4 步长），"
      "available3 = 0x8346300；均在 .bss 内：%s"
      % all(BSS_LO <= v < BSS_LO + BSS_SZ for v in KNOWN_BSS.values()))
    w("[7] PDT 尺寸 %d；.bss 与 PDT 是否重叠：N/A（不同地址空间）" % PDT_SIZE)
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
