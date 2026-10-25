#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T20_got_bind.py · 第十期 T3：从 8 个 .got 槽反查代码引用与附近 id 常量

槽：0x47B8278 / 0x47B8280 / 0x47B8288 / 0x47B8290
    0x47B9AD0 / 0x47B9AD8 / 0x47B9AE0 / 0x47B9AE8
做法：
  1 扫 adrp 页 0x47B8000 / 0x47B9000（含 page±0x1000）+ add/mov 别名
  2 命中 ldr 到目标槽 -> 记为读取点，记录函数起点
  3 读取点前后各 20 条内找：立即数 0x0C2C–0x0C33、0x02CFxxxx 键、mov/movk 组合
只读 fw/。结果写 audit_raw/T20_task3_got_bind.txt + tmp01 副本。
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
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T20_task3_got_bind.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T20_task3_got_bind.txt"

SLOTS = {
    0x47B8278: "available0", 0x47B8280: "available1", 0x47B8288: "available2",
    0x47B8290: "available3", 0x47B9AD0: "multi0", 0x47B9AD8: "multi1",
    0x47B9AE0: "multi2", 0x47B9AE8: "multi3",
}
ID_RANGE = set(range(0x0C2C, 0x0C3C))
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()
    ef = ELFFile(open(APPFW, "rb"))
    ts = ef.get_section_by_name(".text")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    md.skipdata = True
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))
    idx_of = {x.address: i for i, x in enumerate(insns)}

    def func_start(i):
        j = i
        while j > 0 and insns[j - 1].mnemonic != "ret":
            j -= 1
            if i - j > 600:
                break
        return insns[j].address

    pages = {0x47B8000, 0x47B9000}
    sites = []
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
                if (o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG
                        and o2.type == ARM64_OP_IMM and o1.reg in regs):
                    regs[o0.reg] = regs[o1.reg] + o2.imm
                    continue
            if x.mnemonic in ("ldr", "ldur") and x.operands:
                mem = None
                for op in x.operands:
                    if op.type == ARM64_OP_MEM:
                        mem = op.mem
                if mem is None or mem.base not in regs:
                    continue
                v = regs[mem.base] + mem.disp
                if v in SLOTS:
                    j = idx_of.get(x.address, i)
                    sites.append((x.address, v, func_start(j), j))
    w("=" * 78)
    w("T20 · T3 · .got 槽的代码读取点与附近 id 常量")
    w("=" * 78)
    w(".text 指令数 %d；8 个槽的读取点合计 %d" % (len(insns), len(sites)))
    w()

    w("[1] 逐槽统计")
    w("    %-12s %-11s %-8s %-10s %s" % ("槽", "vaddr", "读取点", "相关函数", "常量命中"))
    per = collections.defaultdict(list)
    for a, v, f, j in sites:
        per[v].append((a, f, j))
    for v, nm in sorted(SLOTS.items(), key=lambda kv: kv[1]):
        lst = per.get(v, [])
        w("    %-12s 0x%08X %-8d %-10d %s"
          % (nm, v, len(lst), len(set(f for _, f, _ in lst)), "-"))
    w()

    w("[2] 读取点 ±20 条内的常量扫描（0x0C2C–0x0C33 / 0x02CFxxxx / mov+movk）")
    w("    %-11s %-11s %-11s %-6s %s" % ("槽vaddr", "读取@", "函数@", "id?", "附近立即数/键"))
    hit_total = 0
    for v, nm in sorted(SLOTS.items(), key=lambda kv: kv[1]):
        for a, f, j in per.get(v, [])[:20]:
            lo, hi = max(0, j - 20), min(len(insns), j + 21)
            consts = []
            ids = []
            for y in insns[lo:hi]:
                for op in y.operands:
                    if op.type != ARM64_OP_IMM:
                        continue
                    im = op.imm
                    if im in ID_RANGE:
                        ids.append("0x%04X" % im)
                    if (im & 0xFFFF0000) == 0x02CF0000:
                        consts.append("key 0x%08X" % im)
                    elif 0x2CF == im or (im & 0xFFFF) == 0x02CF:
                        consts.append("0x%X" % im)
            if ids or consts:
                hit_total += 1
            w("    %-11X 0x%08X 0x%08X %-6s %s"
              % (v, a, f, ",".join(ids) or "-",
                 ",".join(sorted(set(consts))[:6]) or "-"))
    w("    有 id/键命中的读取点：%d / %d" % (hit_total, len(sites)))
    w()

    w("[3] 结论数据")
    w("    8 个槽读取点 = %d ；id 常量命中 = %d ；key 命中 = %d"
      % (len(sites), sum(1 for a, v, f, j in sites
                        if any(op.type == ARM64_OP_IMM and op.imm in ID_RANGE
                               for y in insns[max(0, j - 20):j + 21] for op in y.operands)),
         sum(1 for a, v, f, j in sites
             if any(op.type == ARM64_OP_IMM and (op.imm & 0xFFFF0000) == 0x02CF0000
                    for y in insns[max(0, j - 20):j + 21] for op in y.operands))))
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
