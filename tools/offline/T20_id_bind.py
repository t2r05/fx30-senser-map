#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T20_id_bind.py · 第十期 T3（实证版）：id -> .got 槽 -> 回调 的显式绑定扫描

发现：0x19692D0 函数里存在模式
    mov w0, #0xcXX
    movk w0, #1, lsl #16        ; 键 = 0x00010000 | id
    str w0, [x21, #off]
    adrp x0, #<page>
    ldr  x0, [x0, #disp]        ; 取数据源回调指针
    bl   0x19685b4

本脚本全 .text 扫该模式，输出：
    id | 键 | 槽 vaddr | 槽内回调（.rela.dyn addend）| 回调返回值 | 所在函数
只读 fw/。结果写 audit_raw/T20_task3_id_bind.txt + tmp01 副本。
"""
import collections
import os
import struct
import sys

from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T20_task3_id_bind.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T20_task3_id_bind.txt"
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

    # 槽 -> 回调（重定位 addend）
    rel = {}
    for r in ef.get_section_by_name(".rela.dyn").iter_relocations():
        rel[r["r_offset"]] = r["r_addend"]

    def cb_value(a):
        """回调首 2 条指令是 mov w0,#imm; ret 时返回 imm，否则 None"""
        if a is None or a not in idx_of:
            return None
        i = idx_of[a]
        x1, x2 = insns[i], insns[i + 1]
        if x1.mnemonic in ("mov", "movz") and x1.op_str.replace(" ", "").startswith("w0,#") \
                and x2.mnemonic == "ret":
            try:
                return int(x1.op_str.split("#")[1], 0)
            except Exception:
                return None
        return None

    def func_start(i):
        j = i
        while j > 0 and insns[j - 1].mnemonic != "ret":
            j -= 1
            if i - j > 800:
                break
        return insns[j].address

    pairs = []
    for i, ins in enumerate(insns):
        if ins.mnemonic not in ("mov", "movz"):
            continue
        ops = ins.op_str.replace(" ", "")
        if not ops.startswith("w0,#"):
            continue
        try:
            imm = int(ops.split("#")[1], 0)
        except Exception:
            continue
        if not (0x0C00 <= imm <= 0x0CFF):
            continue
        # 向后 3 条内须有 movk w0, #1, lsl #16
        k = None
        for j in range(i + 1, min(i + 4, len(insns))):
            if insns[j].mnemonic == "movk" and insns[j].op_str.replace(" ", "") == "w0,#1,lsl#16":
                k = j
                break
        if k is None:
            continue
        # 再向后 10 条内找 adrp+ldr
        slot = None
        for j in range(k + 1, min(k + 11, len(insns))):
            if insns[j].mnemonic == "adrp" and len(insns[j].operands) >= 2:
                reg = insns[j].operands[0].reg
                pg = insns[j].operands[1].imm
                for x in insns[j + 1:j + 4]:
                    if x.mnemonic == "ldr" and x.operands:
                        mem = None
                        for op in x.operands:
                            if op.type == ARM64_OP_MEM:
                                mem = op.mem
                        if mem and mem.base == reg:
                            slot = pg + mem.disp
                            break
            if slot:
                break
        if slot:
            pairs.append((imm, slot, func_start(i), ins.address))

    w("=" * 78)
    w("T20 · T3 · id -> .got 槽 -> 回调 的显式绑定")
    w("=" * 78)
    w("模式：mov w0,#0xcXX ; movk w0,#1,lsl#16 ; … ; adrp+ldr 槽 ; bl")
    w("命中配对 %d 条" % len(pairs))
    w()
    w("    %-7s %-11s %-11s %-11s %-7s %s"
      % ("id", "键", "槽 vaddr", "槽内回调", "返回值", "函数@"))
    for imm, slot, f, site in sorted(pairs):
        cb = rel.get(slot)
        val = cb_value(cb) if cb is not None else None
        w("    0x%04X 0x%08X 0x%08X 0x%08X %-7s 0x%08X"
          % (imm, 0x00010000 | imm, slot, cb if cb is not None else 0,
             ("%d" % val) if val is not None else "?", f))
    w()

    w("[重点] 0x0C2C-0x0C33")
    for imm, slot, f, site in sorted(pairs):
        if 0x0C2C <= imm <= 0x0C33:
            cb = rel.get(slot)
            val = cb_value(cb) if cb is not None else None
            w("    id 0x%04X -> 槽 0x%08X -> 回调 0x%08X (返回 %s)  @func 0x%08X"
              % (imm, slot, cb or 0, ("%d" % val) if val is not None else "?", f))
    w()

    w("[统计]")
    w("    配对总数 %d；涉及函数 %d" % (len(pairs), len(set(f for _, _, f, _ in pairs))))
    cnt = collections.Counter(f for _, _, f, _ in pairs)
    for f, c in cnt.most_common(5):
        w("      函数 0x%08X : %d 条" % (f, c))
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
