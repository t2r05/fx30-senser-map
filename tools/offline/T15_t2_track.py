#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T15_t2_track.py · 第六期 T2 合并包（§8.3）：12 个 .bss 地址的「写入点」+「读取+分支点」

目标地址（vaddr）：
  PRM 层 0x8E58170/174/178/17C  → adrp 页 0x8E58000，偏移 0x170/174/178/17C
  PRM 层 0x8E58BB0/BB4/BB8/BBC  → adrp 页 0x8E58000，偏移 0xBB0/BB4/BB8/BBC
  BKID   0x83461A4/A8/AC/300    → adrp 页 0x8346000，偏移 0x1A4/1A8/1AC/300

判据（全部只靠反汇编，不搜数据指针）：
  写入点 = adrp 命中目标页 + 其后 12 条内出现 str  w?, [<该寄存器>, #目标偏移]
  读取点 = adrp 命中目标页 + 其后 12 条内出现 ldr  w?, [<该寄存器>, #目标偏移]
  判定点 = 读取点之后 8 条内出现 cmp / cbz / cbnz / tst / cset / b.cond
每条命中都报：指令地址、所在函数起始（向前找最近 ret 之后）、上下文 5 条。
候选函数数 > 200 时只报「有分支的读取」/「有 str 的写入」，并明示收窄。

只读 fw/。结果写 audit_raw/T15_task2_track.txt + tmp01 副本。
用法：
  "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -u T15_t2_track.py
"""
import collections
import os
import sys

from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_MEM, ARM64_OP_REG, ARM64_OP_IMM
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T15_task2_track.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T15_task2_track.txt"

PAGE_PRM = 0x8E58000
PAGE_BKID = 0x8346000
TARGETS = {
    0x8E58170: ("available0(PRM)", PAGE_PRM, 0x170),
    0x8E58174: ("available1(PRM)", PAGE_PRM, 0x174),
    0x8E58178: ("available2(PRM)", PAGE_PRM, 0x178),
    0x8E5817C: ("available3(PRM)", PAGE_PRM, 0x17C),
    0x8E58BB0: ("multi0(PRM)", PAGE_PRM, 0xBB0),
    0x8E58BB4: ("multi1(PRM)", PAGE_PRM, 0xBB4),
    0x8E58BB8: ("multi2(PRM)", PAGE_PRM, 0xBB8),
    0x8E58BBC: ("multi3(PRM)", PAGE_PRM, 0xBBC),
    0x83461A4: ("available0(BKID)", PAGE_BKID, 0x1A4),
    0x83461A8: ("available1(BKID)", PAGE_BKID, 0x1A8),
    0x83461AC: ("available2(BKID)", PAGE_BKID, 0x1AC),
    0x8346300: ("available3(BKID)", PAGE_BKID, 0x300),
}
BRANCH = ("cmp", "cbz", "cbnz", "tbz", "tbnz", "tst", "cset", "csinc", "csel",
          "b.eq", "b.ne", "b.lt", "b.gt", "b.le", "b.ge", "b.hi", "b.ls")
lines = []


def w(s=""):
    lines.append(s)


def main():
    data = open(APPFW, "rb").read()
    elf = ELFFile(open(APPFW, "rb"))
    ts = elf.get_section_by_name(".text")
    taddr, toff, tsize = ts["sh_addr"], ts["sh_offset"], ts["sh_size"]
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    insns = list(md.disasm(data[toff:toff + tsize], taddr))
    idx_of = {ins.address: i for i, ins in enumerate(insns)}

    def func_start(i):
        j = i
        while j > 0 and insns[j - 1].mnemonic != "ret":
            j -= 1
            if i - j > 600:
                break
        return insns[j].address

    # ---- 扫描 adrp 目标页
    hits = collections.defaultdict(lambda: {"wr": [], "rd": []})
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        try:
            dst = ins.operands[0].reg
            page = ins.operands[1].imm
        except Exception:
            continue
        if page not in (PAGE_PRM, PAGE_BKID):
            continue
        # 该页对应的 4 个目标
        cand = {v: (name, off) for v, (name, pg, off) in TARGETS.items() if pg == page}
        # 寄存器 -> (累计偏移)；支持 add/mov 别名（add x3, x0, #0x170 这种）
        regs = {dst: 0}
        for x in insns[i + 1:i + 14]:
            if x.mnemonic == "adrp":
                # 基址寄存器被重新绑定 -> 失效
                if x.operands and x.operands[0].type == ARM64_OP_REG and x.operands[0].reg in regs:
                    del regs[x.operands[0].reg]
                continue
            if x.mnemonic == "add" and len(x.operands) == 3:
                o0, o1, o2 = x.operands
                if (o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG
                        and o2.type == ARM64_OP_IMM and o1.reg in regs):
                    regs[o0.reg] = regs[o1.reg] + o2.imm
                    continue
            if x.mnemonic in ("mov", "orr") and len(x.operands) == 2:
                o0, o1 = x.operands
                if o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG and o1.reg in regs:
                    regs[o0.reg] = regs[o1.reg]
                    continue
            if x.mnemonic in ("ldr", "str", "ldrb", "strb", "ldur", "stur") and x.operands:
                mem = None
                for op in x.operands:
                    if op.type == ARM64_OP_MEM:
                        mem = op.mem
                if mem is None or mem.base not in regs:
                    continue
                disp = mem.disp + regs[mem.base]
                for v, (name, off) in cand.items():
                    if disp == off:
                        key = "wr" if x.mnemonic.startswith("str") else "rd"
                        hits[v][key].append((ins.address, x.address, func_start(i), i, x))
                # ldr 覆盖目标寄存器 -> 失效
                if x.mnemonic.startswith("ldr") and x.operands[0].type == ARM64_OP_REG:
                    regs.pop(x.operands[0].reg, None)
    # ---- 读取点之后 8 条内是否有分支
    rd_total = {v: len(hits[v]["rd"]) for v in TARGETS}
    for v in TARGETS:
        rd2 = []
        for (a, xa, fs, i, x) in hits[v]["rd"]:
            branch = None
            for y in insns[idx_of[x.address] + 1: idx_of[x.address] + 9]:
                if y.mnemonic in BRANCH or y.mnemonic.startswith("b."):
                    branch = y
                    break
            rd2.append((a, xa, fs, i, x, branch))
        hits[v]["rd"] = rd2

    # ---- 汇总表
    w("=" * 78)
    w("T15 · 第六期 T2 合并包 · 12 个 .bss 地址的写入点 / 读取+分支点")
    w("=" * 78)
    w("appFw.so .text vaddr=0x%X 指令数=%d" % (taddr, len(insns)))
    w()
    w("    %-22s %-7s %-6s %-24s %-6s %-6s %-22s %s"
      % ("地址", "写入点", "读点", "写入函数(前3)", "带分支", "读函数数", "读+分支函数(前3)", "备注"))
    summary = []
    for v in sorted(TARGETS):
        name = TARGETS[v][0]
        wr = hits[v]["wr"]
        rd = [r for r in hits[v]["rd"] if r[5] is not None]
        wf = collections.Counter(r[2] for r in wr).most_common(3)
        rf = collections.Counter(r[2] for r in rd).most_common(3)
        both = "★写+读分支都有" if wr and rd else ""
        w("    0x%08X %-12s %-7d %-6d %-24s %-6d %-6d %-22s %s"
          % (v, name, len(wr), rd_total[v], ",".join("0x%X" % a for a, _ in wf),
             len(rd), len(set(r[2] for r in hits[v]["rd"])),
             ",".join("0x%X" % a for a, _ in rf), both))
        summary.append((v, name, len(wr), len(rd), both))
    w()
    w("[注] 收窄判据：读取点只统计「其后 8 条内有 cmp/cbz/cbnz/tst/b.cond」的；"
      "写入点只统计 str/strb 到目标偏移的。")
    w()

    # ---- 明细
    for v in sorted(TARGETS):
        name = TARGETS[v][0]
        w("-" * 78)
        w("[0x%08X] %s  写入 %d 处 / 读+分支 %d 处"
          % (v, name, len(hits[v]["wr"]), len([r for r in hits[v]["rd"] if r[5]])))
        for tag, lst in (("W", hits[v]["wr"]), ("R", hits[v]["rd"])):
            for item in lst[:12]:
                if tag == "W":
                    a, xa, fs, i, x = item
                    br = None
                else:
                    a, xa, fs, i, x, br = item
                    if br is None:
                        continue
                w("    %s  site=0x%08X  insn=0x%08X  func=0x%08X  %s %s"
                  % (tag, a, xa, fs, x.mnemonic, x.op_str))
                if br is not None:
                    w("        分支：0x%08X %s %s" % (br.address, br.mnemonic, br.op_str))
                for y in insns[max(0, i - 2): i + 4]:
                    mark = ">>" if y.address == xa else "  "
                    w("        %s 0x%08X  %-8s %s" % (mark, y.address, y.mnemonic, y.op_str))
        w()

    w("=" * 78)
    for path in (OUT_MAIN, OUT_COPY):
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
