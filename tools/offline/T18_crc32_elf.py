#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T18_crc32_elf.py · 第八期 T2：反汇编 uc_crc32sum.elf，确认 CRC32 参数

判据：
  1) 在文件里找标准 CRC32 的 256 项表（前 4 项 = 00 00 00 00 / 96 30 07 77 / 2C 61 0E EE / BA 51 09 99）
  2) 找多项式常量 0xEDB88320（反射）/ 0x04C11DB7（非反射）、初值 0xFFFFFFFF
  3) 反汇编引用该表的函数，看循环形态（按字节取数 -> xor -> 查表）
  4) 是否把文件名/长度纳入计算：看调用点参数（此处只报指令事实）
只读 tmp01/updater_unpacked/bin/uc_crc32sum.elf。结果写 audit_raw/T18_task2_crc32elf.txt + tmp01 副本。
"""
import os
import struct
import sys

import numpy as np
from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG
from elftools.elf.elffile import ELFFile

ELF = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\updater_unpacked\bin\uc_crc32sum.elf"
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T18_task2_crc32elf.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T18_task2_crc32elf.txt"
TAB_HEAD = struct.pack("<IIII", 0x00000000, 0x77073096, 0xEE0E612C, 0x990951BA)
lines = []


def w(s=""):
    lines.append(s)


def main():
    if not os.path.isfile(ELF):
        sys.exit("缺少：%s" % ELF)
    data = open(ELF, "rb").read()
    ef = ELFFile(open(ELF, "rb"))
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

    w("=" * 78)
    w("T18 · T2 · uc_crc32sum.elf CRC32 参数")
    w("=" * 78)
    w("size=%d  sections=%s" % (len(data), ", ".join("%s(0x%X,0x%X)" % (n, a, s) for n, o, s, a in secs)))
    w()

    # 1) 标准表
    w("[1] 标准 CRC32 表（前 4 项 00 00 00 00 / 96 30 07 77 / 2C 61 0E EE / BA 51 09 99）")
    hits = []
    i = data.find(TAB_HEAD)
    while i >= 0:
        hits.append(i)
        i = data.find(TAB_HEAD, i + 1)
    w("    命中 %d 处 %s" % (len(hits), ", ".join("0x%X(vaddr 0x%X)" % (h, off2va(h)[0] or 0) for h in hits)))
    for h in hits[:2]:
        va, sec = off2va(h)
        vals = struct.unpack("<4I", data[h:h + 16])
        w("    表@0x%X (%s)：前 4 项 = %s" % (h, sec, " ".join("%08X" % v for v in vals)))
        # 校验表是否完整 1024 字节（标准生成法：每项由索引做 8 次位迭代）
        ok = True
        for k in range(256):
            v = struct.unpack("<I", data[h + k * 4:h + k * 4 + 4])[0]
            c = k
            for _ in range(8):
                c = ((c >> 1) ^ (0xEDB88320 if c & 1 else 0)) & 0xFFFFFFFF
            if v != c:
                ok = False
                break
        w("        256 项标准生成校验（poly=0xEDB88320）：%s" % ok)
    w()

    # 2) 常量
    w("[2] 常量搜索")
    for name, val in (("0xEDB88320(反射多项式)", 0xEDB88320), ("0x04C11DB7(非反射多项式)", 0x04C11DB7),
                      ("0xFFFFFFFF(全 1)", 0xFFFFFFFF), ("0xFFFFFFFF xor 后常量", 0xFFFFFFFF)):
        pat = struct.pack("<I", val)
        pos = []
        j = data.find(pat)
        while j >= 0 and len(pos) < 8:
            pos.append(j)
            j = data.find(pat, j + 1)
        w("    %-26s 命中 %d 处 %s" % (name, len(pos), ", ".join("0x%X" % p for p in pos[:6])))
    w()

    # 3) 反汇编
    w("[3] 反汇编（.text 全部，找引用 CRC 表的循环）")
    ts = ef.get_section_by_name(".text")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    md.skipdata = True
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))
    real = [x for x in insns if x.id != 0]
    w("    .text vaddr=0x%X size=%d 指令=%d（含数据跳过 %d）"
      % (ts["sh_addr"], ts["sh_size"], len(real), len(insns) - len(real)))
    tab_vas = [off2va(h)[0] for h in hits if off2va(h)[0]]
    w("    表 vaddr：%s" % ", ".join("0x%X" % t for t in tab_vas))
    # 找 adrp 到表页 + add/ldr 命中表地址
    cands = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        try:
            reg = ins.operands[0].reg
            pg = ins.operands[1].imm
        except Exception:
            continue
        if not any((t & ~0xFFF) - 0x1000 <= pg <= (t & ~0xFFF) + 0x1000 for t in tab_vas):
            continue
        regs = {reg: pg}
        for x in insns[i + 1:i + 12]:
            if x.mnemonic == "add" and len(x.operands) == 3:
                o0, o1, o2 = x.operands
                if (o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG and o2.type == ARM64_OP_IMM
                        and o1.reg in regs):
                    v = regs[o1.reg] + o2.imm
                    if v in tab_vas:
                        cands.append((ins.address, x.address))
                    regs[o0.reg] = v
                    continue
            if x.mnemonic in ("ldr", "ldrb") and x.operands:
                mem = None
                for op in x.operands:
                    if op.type == ARM64_OP_MEM:
                        mem = op.mem
                if mem and mem.base in regs and regs[mem.base] + mem.disp in tab_vas:
                    cands.append((ins.address, x.address))
    w("    引用 CRC 表的指令组：%d 处 %s"
      % (len(cands), ", ".join("0x%X" % a for a, _ in cands[:6])))
    for a, x in cands[:2]:
        k = next(i for i, y in enumerate(insns) if y.address == a)
        w("    --- 上下文 @0x%X ---" % a)
        for y in insns[max(0, k - 12): k + 28]:
            mark = ">>" if y.address in (a, x) else "  "
            w("      %s 0x%08X  %-8s %s" % (mark, y.address, y.mnemonic, y.op_str))
    w()
    w("    --- 全文 .text 反汇编（%d 条）---" % len(insns))
    for y in insns:
        if y.id == 0:
            w("      0x%08X  .byte      %s" % (y.address, y.op_str))
        else:
            w("      0x%08X  %-10s %s" % (y.address, y.mnemonic, y.op_str))
    w()
    # 单独展开 CRC 工作函数 0x4012EC 起的区间
    w("    --- 函数 0x4012EC .. 0x401908 展开 ---")
    for y in insns:
        if 0x4012EC <= y.address < 0x401908:
            w("      0x%08X  %-10s %s" % (y.address, y.mnemonic, y.op_str))
    w()

    w("[4] 字符串（看是否有文件名/长度参与）")
    strs = []
    cur = b""
    for b in data:
        if 32 <= b < 127:
            cur += bytes([b])
        else:
            if len(cur) >= 6:
                strs.append(cur.decode("latin-1"))
            cur = b""
    for s in strs[:25]:
        w("    %s" % s)
    w("    合计 >=6 字符串 %d 个" % len(strs))
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
