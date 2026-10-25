#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T19_callbacks.py · 第九期 T1/T2：数据源回调族全表 + available 初值链路

T1：
  1) 枚举 .text 里所有「mov w0,#imm ; ret」两指令函数（含 movz），记 地址/返回值
  2) 反向：每个回调地址在文件里的 qword 引用（8B 对齐 + 非对齐），按段分类
  3) 识别 24 字节描述符记录 {callback, got_slot, 0x403}（.rela.dyn 区）
  4) 在每条记录 ±0x60 内找 0x02CF0000|id 键，做 id ↔ 回调 ↔ 初值 映射
T2：
  5) 8 个 PRM .bss 槽（0x8E58170..7C / 0x8E58BB0..BC）在数据里的 qword 引用分类：
     RELATIVE 重定位 / 描述符记录 / 无
只读 fw/。结果写 audit_raw/T19_task1_callbacks.txt + tmp01 副本。
"""
import collections
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
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T19_task1_callbacks.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T19_task1_callbacks.txt"
BSS_SLOTS = {0x8E58170: "available0", 0x8E58174: "available1", 0x8E58178: "available2",
             0x8E5817C: "available3", 0x8E58BB0: "multi0", 0x8E58BB4: "multi1",
             0x8E58BB8: "multi2", 0x8E58BBC: "multi3"}
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

    def sec_of_off(o):
        for name, off, size, addr in secs:
            if off <= o < off + size:
                return name
        return "?"

    ts = ef.get_section_by_name(".text")
    tlo, thi = ts["sh_addr"], ts["sh_addr"] + ts["sh_size"]
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    md.skipdata = True
    insns = list(md.disasm(data[ts["sh_offset"]:ts["sh_offset"] + ts["sh_size"]], ts["sh_addr"]))

    w("=" * 78)
    w("T19 · 第九期 T1/T2 · 数据源回调族 + available 初值链路")
    w("=" * 78)
    w("appFw.so size=%d  .text [0x%X,0x%X)" % (len(data), tlo, thi))
    w()

    # ---- 1) 枚举 2 指令回调
    cbs = []
    for i in range(len(insns) - 1):
        x, y = insns[i], insns[i + 1]
        if x.id == 0 or y.id == 0:
            continue
        if x.mnemonic not in ("mov", "movz", "movn"):
            continue
        if y.mnemonic != "ret":
            continue
        ops = x.op_str.replace(" ", "")
        if not ops.startswith("w0,#"):
            continue
        try:
            imm = int(ops.split("#")[1], 0)
        except Exception:
            continue
        # 函数边界：前一条应为 ret / 或本地址是 4/8 字节对齐块起点
        prev_ok = (i == 0) or insns[i - 1].mnemonic == "ret" or insns[i - 1].id == 0
        cbs.append((x.address, imm, prev_ok))
    w("[1] 「mov w0,#imm ; ret」回调候选 %d 个（前一条为 ret/数据：%d）"
      % (len(cbs), sum(1 for _, _, p in cbs if p)))
    valcnt = collections.Counter(v for _, v, _ in cbs)
    w("    返回值分布（Top 12）：%s"
      % ", ".join("%d:%d" % (v, c) for v, c in valcnt.most_common(12)))
    w()

    u64 = np.frombuffer(data[:len(data) // 8 * 8], dtype="<u8")
    cbaddrs = np.array(sorted({a for a, _, _ in cbs}), dtype=np.uint64)

    # ---- 2) 反向引用（一次 np.isin，避免逐回调全表扫）
    w("[2] 回调地址的 qword 引用（按段）")
    mask = np.isin(u64, cbaddrs)
    pos_all = np.nonzero(mask)[0]
    refs = collections.defaultdict(list)
    for p in pos_all:
        fo = int(p) * 8
        va, nm = off2va(fo)
        refs[int(u64[p])].append((fo, va, nm))
    secstat = collections.Counter(nm for a in refs for _, _, nm in refs[a])
    w("    有引用的回调 %d / %d；引用位置按段：%s"
      % (len(refs), len(cbs), dict(secstat)))
    w()

    # ---- 3) 24 字节描述符记录 {callback, got_slot, 0x403}
    w("[3] 24 字节描述符记录（.rela.dyn 区，{callback, got_slot, 0x403}）")
    recs = []
    for a in sorted(cbaddrs):
        for fo, va, nm in refs[a]:
            base = (fo // 8) * 8
            q0 = struct.unpack("<Q", data[base:base + 8])[0]
            q1 = struct.unpack("<Q", data[base + 8:base + 16])[0]
            q2 = struct.unpack("<Q", data[base + 16:base + 24])[0]
            if q0 == a and tlo <= q1 < thi and q2 == 0x403:
                recs.append((base, a, q1))
            elif q0 == a and 0x47B0000 <= q1 < 0x47B0000 + 0x20000 and q2 == 0x403:
                recs.append((base, a, q1))
    gotrecs = [r for r in recs if 0x47B0000 <= r[2] < 0x47B0000 + 0x20000]
    w("    识别到 %d 条（其中第二字段落在 .got 区 %d 条）" % (len(recs), len(gotrecs)))
    w()

    # ---- 4) id 关联：记录 ±0x60 内找 0x02CFxxxx
    w("[4] 记录 ±0x60 内搜索 0x02CF0000|id 键")
    w("    %-10s %-12s %-12s %-8s %s" % ("记录偏移", "callback", "got_slot", "初值", "附近 key"))
    nkey = 0
    rows = []
    for base, a, slot in sorted(gotrecs)[:120]:
        keys = []
        for k in range(-0x60, 0x61, 4):
            o = base + k
            if o < 0 or o + 4 > len(data):
                continue
            v = struct.unpack("<I", data[o:o + 4])[0]
            if (v & 0xFFFF0000) == 0x02CF0000:
                keys.append(v & 0xFFFF)
        imm = dict((x, y) for x, y, _ in cbs).get(a, -1)
        if keys:
            nkey += 1
        rows.append((base, a, slot, imm, keys))
        w("    0x%08X 0x%08X   0x%08X   %-8d %s"
          % (base, a, slot, imm, ",".join("0x%04X" % k for k in keys) or "-"))
    if len(gotrecs) > 120:
        w("    ... 其余 %d 条略（文件里是全集）" % (len(gotrecs) - 120))
    w("    附近有关键字的记录：%d / %d" % (nkey, len(gotrecs)))
    w()

    # ---- 5) T2：.bss 槽的引用分类
    w("[5] T2 · available/multi 的 .bss 槽引用分类")
    rela = ef.get_section_by_name(".rela.dyn")
    reloc_addends = collections.defaultdict(list)
    for rel in rela.iter_relocations():
        reloc_addends[rel["r_addend"]].append(rel["r_offset"])
    w("    %-12s %-10s %-10s %-26s %s"
      % ("槽", "vaddr", "qword 引用", "引用的段", "作为 r_addend 的重定位"))
    slot_arr = np.array(sorted(BSS_SLOTS), dtype=np.uint64)
    smask = np.isin(u64, slot_arr)
    spos = np.nonzero(smask)[0]
    slot_refs = collections.defaultdict(list)
    for p in spos:
        slot_refs[int(u64[p])].append(off2va(int(p) * 8))
    for s, nm in sorted(BSS_SLOTS.items()):
        locs = slot_refs.get(s, [])
        ras = reloc_addends.get(s, [])
        w("    %-12s 0x%08X %-10d %-26s %d 处 %s"
          % (nm, s, len(locs),
             ",".join(sorted({n for _, n in locs})) or "-",
             len(ras), ", ".join("0x%X" % x for x in ras[:3])))
    w()

    # ---- 6) 值 = 0 且被当作数据源的回调
    w("[6] 返回值为 0 且出现在描述符记录里的回调")
    zero = [(b, a, slot) for b, a, slot in gotrecs if dict((x, y) for x, y, _ in cbs).get(a) == 0]
    w("    计 %d 条" % len(zero))
    for b, a, slot in zero[:40]:
        w("      记录 0x%08X  callback 0x%08X  got 0x%08X" % (b, a, slot))
    w()
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
