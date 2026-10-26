#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T18_slot_consumers.py · 第七期 T17（doc 20 §六）：重定位驱动槽的消费者分析

四件事：
  1) 校验 PRM 8 个条目对应的 16 个槽地址（每条目 +0x10 / +0x18 两个 u64 指针）
     —— 表1 available：vaddr 0x40FE1xx；表2 multi：vaddr 0x41048xx
  2) 扫「谁读这些槽」：adrp xM,#0x40FE000 / #0x4104000 + ldr（含 page±0x1000 跨页）
  3) 0 命中时的跨模块调查：lib/*.so 里哪些 DT_NEEDED 引用 appFw.so
  4) 统计 .rela.dyn 里 addend 落在 0x8E58xxx（PRM 参数区）的重定位数量与页分布
只读 fw/。结果写 audit_raw/T18_task17_slots.txt + tmp01 副本。
用法：
  "$PY" -u T18_slot_consumers.py
"""
import collections
import glob
import os
import struct
import sys

import numpy as np
from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
LIBDIR = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                      "nflasha15_unpacked", "lib")
APPFW = os.path.join(LIBDIR, "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T18_task17_slots.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T18_task17_slots.txt"

# 条目文件偏移（T1 实测）→ 名称
ENTRIES = [
    ("available0", 0x40EE180), ("available1", 0x40EE1A8),
    ("available2", 0x40EE1D0), ("available3", 0x40EE1F8),
    ("multi0", 0x40F4800), ("multi1", 0x40F4828),
    ("multi2", 0x40F4850), ("multi3", 0x40F4878),
]
PRM_LO, PRM_HI = 0x8E58000, 0x8EA0000
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()
    ef = ELFFile(open(APPFW, "rb"))
    secs = []
    for s in ef.iter_sections():
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

    def q(va):
        o, _ = va2off(va)
        if o is None or o + 8 > len(data):
            return None
        return struct.unpack("<Q", data[o:o + 8])[0]

    w("=" * 78)
    w("T18 · 第七期 T17 · 重定位驱动槽的消费者分析")
    w("=" * 78)
    w("appFw.so size=%d" % len(data))
    w()

    # ---- 1) 槽地址与内容
    w("[1] 8 个 PRM 条目 -> 16 个槽（每条目 +0x10 / +0x18）")
    w("    %-11s %-10s %-12s %-12s %-12s" % ("参数", "条目偏移", "条目vaddr", "槽1 (+0x10)", "槽2 (+0x18)"))
    slots = []
    for name, fo in ENTRIES:
        va, sec = off2va(fo)
        s1, s2 = va + 0x10, va + 0x18
        v1, v2 = q(s1), q(s2)
        slots.append((s1, name, "slot1", v1))
        slots.append((s2, name, "slot2", v2))
        w("    %-11s 0x%08X 0x%08X   0x%08X   0x%08X"
          % (name, fo, va, s1, s2))
    w()
    w("    槽内容（vaddr -> 值）：")
    for s, name, tag, v in slots:
        w("      0x%08X (%s/%s) = 0x%X%s"
          % (s, name, tag, v if v is not None else 0,
             "  <.bss>" if v is not None and 0x4B6E738 <= v < 0x9DC99F8 else ""))
    w()
    w("    槽地址是否 8 字节对齐：%s" % all(s % 8 == 0 for s, _, _, _ in slots))
    w("    两个槽内容是否相同：%s" % all(q(s1) == q(s2) for s1, _, _, _ in slots for s2 in [0] + [0]))
    dup = 0
    for i in range(0, len(slots), 2):
        if q(slots[i][0]) == q(slots[i + 1][0]):
            dup += 1
    w("    逐条目两槽相等的条目数：%d / 8" % dup)
    w()

    # ---- 2) 谁读这些槽
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    ts = ef.get_section_by_name(".text")
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))
    pages = {s & ~0xFFF for s, _, _, _ in slots}
    w("[2] 消费者扫描：adrp 页 %s（含 page±0x1000）" % ", ".join("0x%X" % p for p in sorted(pages)))
    target = {s: (nm, tg) for s, nm, tg, _ in slots}
    hits = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        try:
            reg = ins.operands[0].reg
            pg = ins.operands[1].imm
        except Exception:
            continue
        if not any(p - 0x1000 <= pg <= p + 0x1000 for p in pages):
            continue
        regs = {reg: pg}
        for x in insns[i + 1:i + 12]:
            if x.mnemonic == "adrp":
                if x.operands and x.operands[0].type == ARM64_OP_REG and x.operands[0].reg in regs:
                    del regs[x.operands[0].reg]
                continue
            if x.mnemonic == "add" and len(x.operands) == 3:
                o0, o1, o2 = x.operands
                if (o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG and o2.type == ARM64_OP_IMM
                        and o1.reg in regs):
                    regs[o0.reg] = regs[o1.reg] + o2.imm
                    continue
            if x.mnemonic in ("ldr", "ldur", "ldrb", "str", "strb") and x.operands:
                mem = None
                for op in x.operands:
                    if op.type == ARM64_OP_MEM:
                        mem = op.mem
                if mem is None or mem.base not in regs:
                    continue
                v = regs[mem.base] + mem.disp
                if v in target:
                    j = i
                    while j > 0 and insns[j - 1].mnemonic != "ret":
                        j -= 1
                    hits.append((ins.address, x.address, insns[j].address, v, x.mnemonic, x.op_str))
                    if x.mnemonic.startswith("ldr") and x.operands[0].type == ARM64_OP_REG:
                        regs.pop(x.operands[0].reg, None)
                    continue
                if x.mnemonic.startswith("ldr") and x.operands[0].type == ARM64_OP_REG:
                    regs.pop(x.operands[0].reg, None)
    w("    命中 %d 处" % len(hits))
    for a, x, f, v, mn, ops in hits[:40]:
        w("      adrp@0x%08X 访问@0x%08X func=0x%08X -> 0x%08X (%s/%s)  %s %s"
          % (a, x, f, v, target[v][0], target[v][1], mn, ops))
    w("    涉及函数 %d 个" % len(set(h[2] for h in hits)))
    w()

    # ---- 3) 跨模块：哪些 lib/*.so 依赖 appFw.so
    w("[3] 跨模块调查：lib/*.so 的 DT_NEEDED 是否含 appFw.so")
    sos = sorted(glob.glob(os.path.join(LIBDIR, "*.so")))
    w("    lib/ 下 .so 共 %d 个" % len(sos))
    depend = []
    for p in sos:
        try:
            e2 = ELFFile(open(p, "rb"))
            dyn = e2.get_section_by_name(".dynamic")
            needed = []
            if dyn:
                for tag in dyn.iter_tags():
                    if tag.entry.d_tag == "DT_NEEDED":
                        needed.append(tag.needed)
            if any("appFw" in n for n in needed):
                depend.append((os.path.basename(p), needed))
        except Exception:
            continue
    for nm, nd in depend:
        w("      %-28s NEEDED=%s" % (nm, ",".join(nd)))
    w("    引用 appFw.so 的模块数：%d" % len(depend))
    w()

    # ---- 4) .rela.dyn 里 addend 落在 PRM 区的统计
    w("[4] .rela.dyn 中 addend 落在 PRM 区 [0x%X,0x%X) 的重定位" % (PRM_LO, PRM_HI))
    rd = ef.get_section_by_name(".rela.dyn")
    pagecnt = collections.Counter()
    in_prm = 0
    in_bkid = 0
    total = 0
    if rd:
        for rel in rd.iter_relocations():
            total += 1
            a = rel["r_addend"]
            if a is None:
                continue
            if PRM_LO <= a < PRM_HI:
                in_prm += 1
                pagecnt[a & ~0xFFF] += 1
            if 0x8340000 <= a < 0x8350000:
                in_bkid += 1
    w("    .rela.dyn 条目总数 %d" % total)
    w("    addend 在 PRM 区：%d" % in_prm)
    w("    addend 在 BKID 区 [0x8340000,0x8350000)：%d" % in_bkid)
    w("    PRM 区按页分布（前 15）：")
    for pg, c in pagecnt.most_common(15):
        w("      0x%06X : %d" % (pg, c))
    w()

    w("[5] 判定数据")
    w("    槽读点 = %d ；跨模块依赖 appFw.so 的模块 = %d" % (len(hits), len(depend)))
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
