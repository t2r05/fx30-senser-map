#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_t2_dispatch.py · 第六期 T2：谁引用 handler 表（0x40717C8 一带）与描述符表（0x51EC00 一带）

T15_t2_vtable.py 直接按 adrp 页搜 0x4071000/0x51E000 得到 0 命中 —— 说明引用可能写成
`adrp 0x4070000 + add #0x17C8`（跨页粒度）。本脚本改为按「page + imm == 目标地址范围」匹配。

目标范围：
  handler 表     vaddr [0x4071700, 0x4071A00)
  描述符表       vaddr [0x51EC00, 0x51EE00)
只读 fw/。结果写 audit_raw/T15_task2_dispatch.txt + tmp01 副本。
"""
import collections
import os
import sys

from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task2_dispatch.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task2_dispatch.txt"
RANGES = [(0x4071700, 0x4071A00, "handler表"), (0x51EC00, 0x51EE00, "描述符表")]
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()
    elf = ELFFile(open(APPFW, "rb"))
    ts = elf.get_section_by_name(".text")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))

    def in_range(v):
        for lo, hi, tag in RANGES:
            if lo <= v < hi:
                return tag
        return None

    hits = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        try:
            reg = ins.operands[0].reg
            page = ins.operands[1].imm
        except Exception:
            continue
        # 近似范围：page 落在目标 ±0x20000
        if not any(lo - 0x20000 <= page < hi + 0x20000 for lo, hi, _ in RANGES):
            continue
        regs = {reg: page}
        for x in insns[i + 1:i + 10]:
            if x.mnemonic == "adrp":
                if x.operands and x.operands[0].type == ARM64_OP_REG and x.operands[0].reg in regs:
                    del regs[x.operands[0].reg]
                continue
            if x.mnemonic == "add" and len(x.operands) == 3:
                o0, o1, o2 = x.operands
                if (o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG and o2.type == ARM64_OP_IMM
                        and o1.reg in regs):
                    v = regs[o1.reg] + o2.imm
                    tag = in_range(v)
                    if tag:
                        j = i
                        while j > 0 and insns[j - 1].mnemonic != "ret":
                            j -= 1
                        hits.append((ins.address, x.address, insns[j].address, v, tag))
                    regs[o0.reg] = v
                    continue
            if x.mnemonic in ("ldr", "str") and x.operands:
                mem = None
                for op in x.operands:
                    if op.type == ARM64_OP_MEM:
                        mem = op.mem
                if mem and mem.base in regs:
                    v = regs[mem.base] + mem.disp
                    tag = in_range(v)
                    if tag:
                        j = i
                        while j > 0 and insns[j - 1].mnemonic != "ret":
                            j -= 1
                        hits.append((ins.address, x.address, insns[j].address, v, tag))

    w("=" * 78)
    w("T15 · T2 · handler/描述符表的引用点（page+imm 匹配）")
    w("=" * 78)
    cnt = collections.Counter((h[4], h[2]) for h in hits)
    w("命中 %d 处，涉及 (表, 函数) 组合 %d 个" % (len(hits), len(cnt)))
    w()
    w("    %-12s %-12s %-12s %-12s %s" % ("表", "adrp@", "访问@", "func@", "目标地址"))
    for a, x, f, v, tag in hits[:60]:
        w("    %-12s 0x%08X 0x%08X 0x%08X 0x%08X" % (tag, a, x, f, v))
    if len(hits) > 60:
        w("    ... 其余 %d 处略" % (len(hits) - 60))
    w()
    w("[按函数汇总]")
    for (tag, f), c in cnt.most_common(15):
        w("    %-12s func=0x%08X  引用 %d 次" % (tag, f, c))
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
