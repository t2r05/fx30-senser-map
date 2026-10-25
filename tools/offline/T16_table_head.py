#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T16_table_head.py · 从 0x3202FE4 回溯表头 + 用表头地址反查引用

步骤（严格按指令）：
  1) 判定 0x3202FE4 是 vaddr 还是文件偏移（两种都试）
  2) 以 16 字节步长向后 / 向前回溯，直到条目不再满足
        u32[0] == u32[1] && u32[2] < 0x1000
     → 报起始 vaddr、条目数、首/末条目 u32 值
  3) 用【表头 vaddr】搜：
       (a) qword 指针引用（全文件）
       (b) adrp 页 + add/ldr 位移匹配（全 .text）
只读 fw/。结果写 audit_raw/T16_table_head.txt + tmp01 副本。
用法：
  "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -u T16_table_head.py
"""
import collections
import os
import struct
import sys

import numpy as np
from capstone import Cs
from capstone import CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
APPFW = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                     "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T16_table_head.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T16_table_head.txt"

SEED = 0x3202FE4
ESZ = 16
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

    w("=" * 78)
    w("T16 · 表头回溯 + 引用反查")
    w("=" * 78)
    w("appFw.so size=%d" % len(data))
    va, sec = off2va(SEED) if SEED < len(data) else (None, None)
    w("0x%X 作为文件偏移 -> vaddr 0x%X (%s)" % (SEED, va or 0, sec))
    vo, sec2 = va2off(SEED)
    w("0x%X 作为 vaddr     -> 文件偏移 0x%X (%s)" % (SEED, vo or 0, sec2))
    # 选一个能映射的作为基准
    if vo is not None:
        base_off, base_va, base_sec = vo, SEED, sec2
    else:
        base_off, base_va, base_sec = SEED, va, sec
    w("采用：文件偏移 0x%X / vaddr 0x%X / 段 %s" % (base_off, base_va, base_sec))
    w()

    def ent_u32(off):
        if off < 0 or off + ESZ > len(data):
            return None
        a, b, c = struct.unpack("<III", data[off:off + 12])
        return a, b, c

    def ok(e):
        return e is not None and e[0] == e[1] and e[2] < 0x1000

    w("[1] 种子条目 u32 = %s，满足条件：%s"
      % (ent_u32(base_off), ok(ent_u32(base_off))))
    # 若种子不满足，先在 ±0x400 内找最近满足的条目
    if not ok(ent_u32(base_off)):
        found = None
        for k in range(1, ESZ * 64):
            for o in (base_off - k * ESZ, base_off + k * ESZ):
                if ok(ent_u32(o)):
                    found = o
                    break
            if found:
                break
        w("    种子不满足，最近满足的条目在文件偏移 0x%X（距种子 %+d 字节）"
          % (found, found - base_off) if found else "    种子不满足，±0x400 内未找到满足条目")
        if found is None:
            w("=" * 78)
            for path in (OUT_MAIN, OUT_COPY):
                d = os.path.dirname(path)
                if not os.path.isdir(d):
                    os.makedirs(d)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(lines))
            print("\n".join(lines))
            return
        base_off = found
    w()

    # ---- 向后 / 向前回溯
    fwd = base_off
    n_fwd = 0
    while ok(ent_u32(fwd + ESZ)):
        fwd += ESZ
        n_fwd += 1
    back = base_off
    n_back = 0
    while ok(ent_u32(back - ESZ)):
        back -= ESZ
        n_back += 1
    head = back
    tail = fwd
    n = (tail - head) // ESZ + 1
    head_va, head_sec = off2va(head)
    tail_va, _ = off2va(tail)
    w("[2] 表范围")
    w("    表头 文件偏移 0x%X  vaddr 0x%X  (%s)" % (head, head_va, head_sec))
    w("    表尾 文件偏移 0x%X  vaddr 0x%X" % (tail, tail_va))
    w("    条目数 %d（种子前 %d 条 + 种子 + 种子后 %d 条），步长 %d" % (n, n_back, n_fwd, ESZ))
    w("    首条目 u32 = %s" % (ent_u32(head),))
    w("    末条目 u32 = %s" % (ent_u32(tail),))
    w("    表头是否 16B 对齐：%s（vaddr & 0xF = 0x%X）" % (head_va % 16 == 0, head_va % 16))
    w()
    w("    前 8 条：")
    for i in range(8):
        o = head + i * ESZ
        if o > tail:
            break
        w("      +0x%03X 0x%08X: %s" % (i * ESZ, off2va(o)[0], ent_u32(o)))
    w("    后 4 条：")
    for i in range(4):
        o = tail - i * ESZ
        if o < head:
            break
        w("      -0x%03X 0x%08X: %s" % (i * ESZ, off2va(o)[0], ent_u32(o)))
    w()

    # ---- (a) qword 指针引用表头
    u64 = np.frombuffer(data[:len(data) // 8 * 8], dtype="<u8")
    w("[3] qword 指针引用【表头 0x%X】" % head_va)
    pos = np.nonzero(u64 == np.uint64(head_va))[0]
    w("    命中 %d 处 %s" % (len(pos), ", ".join("0x%X" % (int(p) * 8) for p in pos[:8])))
    # 也查表头 ±0（含非对齐）
    pat = struct.pack("<Q", head_va)
    j = data.find(pat)
    unaligned = []
    while j >= 0:
        unaligned.append(j)
        j = data.find(pat, j + 1)
    w("    非对齐搜索命中 %d 处 %s"
      % (len(unaligned), ", ".join("0x%X" % x for x in unaligned[:8])))
    w()

    # ---- (b) adrp 页 + 位移匹配
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    ts = elf.get_section_by_name(".text")
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))
    page = head_va & ~0xFFF
    off_in = head_va - page
    w("[4] adrp 页 0x%X + 位移 0x%X 的匹配（全 .text，%d 条指令）" % (page, off_in, len(insns)))
    hits = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        try:
            reg = ins.operands[0].reg
            pg = ins.operands[1].imm
        except Exception:
            continue
        if not (page - 0x1000 <= pg <= page + 0x1000):
            continue
        regs = {reg: pg}
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
                    if v == head_va:
                        j = i
                        while j > 0 and insns[j - 1].mnemonic != "ret":
                            j -= 1
                        hits.append((ins.address, x.address, insns[j].address, x.mnemonic, x.op_str))
                    regs[o0.reg] = v
                    continue
            if x.mnemonic in ("ldr", "str", "ldrb", "strb") and x.operands:
                mem = None
                for op in x.operands:
                    if op.type == ARM64_OP_MEM:
                        mem = op.mem
                if mem and mem.base in regs and regs[mem.base] + mem.disp == head_va:
                    j = i
                    while j > 0 and insns[j - 1].mnemonic != "ret":
                        j -= 1
                    hits.append((ins.address, x.address, insns[j].address, x.mnemonic, x.op_str))
    w("    命中 %d 处" % len(hits))
    for a, x, f, mn, ops in hits[:40]:
        w("      adrp@0x%08X  访问@0x%08X  func=0x%08X  %s %s" % (a, x, f, mn, ops))
    w()
    cnt = collections.Counter(h[2] for h in hits)
    w("    涉及函数 %d 个：%s" % (len(cnt), ", ".join("0x%X×%d" % (k, v) for k, v in cnt.most_common(8))))
    w()

    # ---- 稳健性检查：表内全部条目地址逐个再搜一遍（先按页过滤 adrp，避免 6×680 万次）
    w("[4b] 稳健性：表内 %d 个条目地址逐个搜（qword 对齐/非对齐 + adrp 位移匹配）" % n)
    entry_vas = [off2va(head + i * ESZ)[0] for i in range(n)]
    pmin, pmax = (head_va & ~0xFFF) - 0x1000, (tail_va & ~0xFFF) + 0x1000
    adrp_idx = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "adrp" or len(ins.operands) < 2:
            continue
        try:
            adrp_idx.append((i, ins.operands[0].reg, ins.operands[1].imm))
        except Exception:
            continue
    adrp_idx = [(i, r, pg) for (i, r, pg) in adrp_idx if pmin <= pg <= pmax]
    w("    预筛：目标页区间 [0x%X, 0x%X] 内的 adrp 共 %d 条" % (pmin, pmax, len(adrp_idx)))
    total_q = total_a = 0
    for ev in entry_vas:
        qn = len(np.nonzero(u64 == np.uint64(ev))[0])
        pt = struct.pack("<Q", ev)
        uq = 0
        j = data.find(pt)
        while j >= 0:
            uq += 1
            j = data.find(pt, j + 1)
        an = 0
        for (i, reg, pg) in adrp_idx:
            regs = {reg: pg}
            for x in insns[i + 1:i + 10]:
                if x.mnemonic == "adrp":
                    if x.operands and x.operands[0].type == ARM64_OP_REG and x.operands[0].reg in regs:
                        del regs[x.operands[0].reg]
                    continue
                if x.mnemonic == "add" and len(x.operands) == 3:
                    o0, o1, o2 = x.operands
                    if (o0.type == ARM64_OP_REG and o1.type == ARM64_OP_REG
                            and o2.type == ARM64_OP_IMM and o1.reg in regs):
                        if regs[o1.reg] + o2.imm == ev:
                            an += 1
                        regs[o0.reg] = regs[o1.reg] + o2.imm
                        continue
                if x.mnemonic in ("ldr", "str", "ldrb", "strb") and x.operands:
                    mem = None
                    for op in x.operands:
                        if op.type == ARM64_OP_MEM:
                            mem = op.mem
                    if mem and mem.base in regs and regs[mem.base] + mem.disp == ev:
                        an += 1
        total_q += qn + uq
        total_a += an
        w("      0x%08X : qword 对齐 %d / 非对齐 %d / adrp 匹配 %d" % (ev, qn, uq, an))
    w("    合计：qword %d，adrp %d" % (total_q, total_a))
    w()
    w("[5] 判定")
    w("    表头 qword 引用 = %d ；adrp 匹配 = %d" % (len(pos) + len(unaligned), len(hits)))
    w("    表内 6 个条目地址合计引用 = %d" % (total_q + total_a))
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
