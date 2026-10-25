#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T24_flags.py · 第十三期 T1/T2/T3：按 A7CR「产品标志（2 字节，按 column）」模型找 FX30 的表

Part0 0x3094C00 区域定性（边界 / 256·257·512 是否为分隔符 / 0:1 比例 / 结构）
Part1 .data+.rodata 里「2 字节项 ∈{0,1}、连续 ≥16、0/1 混合」的组（步长 2/4/8）
Part2 列标志候选：u16 序列中 [5..7]=1 且 [8]=0（我方列号 5/6/7 显示、8 隐藏）
Part3 相距 184 字节的两个 2 字节项成族（A7CR FL2/FL3 间距 0xB8）
Part4 选择能力候选（0x0000 紧邻 0x0101 / 两个连续 0 字节）
只读 fw/。结果写 audit_raw/T24_flags.txt + tmp01 副本。
"""
import collections
import os
import struct
import sys

import numpy as np
from elftools.elf.elffile import ELFFile

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
P30 = os.path.join(FW, "out", "firmware.tar_unpacked", "0700_part_image", "dev",
                   "nflasha15_unpacked", "lib", "appFw.so")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T24_flags.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T24_flags.txt"
lines = []


def w(s=""):
    lines.append(s)


def main():
    d = open(P30, "rb").read()
    ef = ELFFile(open(P30, "rb"))
    secs = []
    for s in ef.iter_sections():
        if s["sh_size"] and s["sh_type"] != "SHT_NOBITS":
            secs.append((s.name, s["sh_offset"], s["sh_size"], s["sh_addr"]))
    secs.sort(key=lambda x: x[1])
    ro = ef.get_section_by_name(".rodata")
    da = ef.get_section_by_name(".data")
    ranges = [(".rodata", ro["sh_offset"], ro["sh_offset"] + ro["sh_size"]),
              (".data", da["sh_offset"], da["sh_offset"] + da["sh_size"])]

    w("=" * 78)
    w("T24 · 第十三期 · 产品标志表搜索（A7CR 模型：2 字节 / 按 column）")
    w("=" * 78)

    # ---------- Part0：0x3094C00 区域定性
    w("[Part0] 0x3094C00 区域定性")
    lo, hi = 0x3094B00, 0x3095600
    u16 = np.frombuffer(d[lo:hi - ((hi - lo) % 2)], dtype="<u2")
    cnt = collections.Counter(u16.tolist())
    w("    窗口 0x%X-0x%X（%d 个 u16）" % (lo, hi, len(u16)))
    w("    值分布 Top-10：%s" % ", ".join("%d:%d" % (k, v) for k, v in cnt.most_common(10)))
    # 256/257/512 的位置
    pos_big = [lo + 2 * i for i, v in enumerate(u16.tolist()) if v in (256, 257, 512, 514)]
    w("    含 256/257/512/514 的位置：%d 个，前 12：%s"
      % (len(pos_big), ", ".join("0x%X" % p for p in pos_big[:12])))
    gaps = [pos_big[i + 1] - pos_big[i] for i in range(len(pos_big) - 1)] if len(pos_big) > 1 else []
    if gaps:
        gc = collections.Counter(gaps)
        w("    这些位置的间隔分布 Top-6：%s" % ", ".join("%d:%d" % (k, v) for k, v in gc.most_common(6)))
    # 边界：从 0x3094C00 向两侧找「非 0/1 且非 256/257/512」的连续带
    def is_ui(v):
        return v in (0, 1, 256, 257, 512, 514, 2, 6)

    a = 0x3094C00
    b = a
    while b + 2 <= len(d) and is_ui(struct.unpack("<H", d[b:b + 2])[0]):
        b += 2
        if b - a > 0x2000:
            break
    c = a
    while c - 2 >= 0 and is_ui(struct.unpack("<H", d[c - 2:c])[0]):
        c -= 2
        if a - c > 0x2000:
            break
    w("    边界扩展：lo=0x%X hi=0x%X（长 %d B）" % (c, b, b - c))
    # 结构假设：每 0x20 字节是否一块（看 256/257/512 是否在块首）
    blk = [p for p in pos_big if (p - c) % 0x20 == 0]
    w("    256/257/512 中位于「相对 lo 的 0x20 对齐位置」：%d / %d" % (len(blk), len(pos_big)))
    blk2 = [p for p in pos_big if (p - c) % 0x10 == 0]
    w("    位于 0x10 对齐位置：%d / %d" % (len(blk2), len(pos_big)))
    w()

    # ---------- Part1：u16 组扫描
    w("[Part1] 2 字节 0/1 成组（步长 2/4/8，组≥16，0/1 混合）")
    groups = []
    for sname, a0, b0 in ranges:
        for stride in (2, 4, 8):
            step = stride
            n = (b0 - a0) // step
            raw = np.frombuffer(d[a0:a0 + n * step], dtype="<u2")
            vals = raw[::step // 2]
            ok = (vals <= 1)
            # 连续 True 段
            idx = 0
            while idx < len(ok):
                if ok[idx]:
                    j = idx
                    while j < len(ok) and ok[j]:
                        j += 1
                    L = j - idx
                    if L >= 16:
                        seg = vals[idx:j]
                        if seg.min() != seg.max():  # 混合
                            groups.append((a0 + idx * step, step, L, sname,
                                           int((seg == 0).sum()), int((seg == 1).sum())))
                    idx = j
                else:
                    idx += 1
    w("    命中组 %d 个" % len(groups))
    w("    %-11s %-5s %-6s %-5s %-5s %-6s %-9s %s"
      % ("组起点", "步长", "项数", "0数", "1数", "比例1", "4个1+2个0", "段"))
    for g0, step, L, sname, n0, n1 in groups[:40]:
        seg = np.frombuffer(d[g0:g0 + L * step], dtype="<u2")[::step // 2]
        has = False
        for k in range(len(seg) - 5):
            if list(seg[k:k + 6]) == [1, 1, 1, 1, 0, 0]:
                has = True
                break
        w("    0x%08X %-5d %-6d %-5d %-5d %-6.2f %-9s %s"
          % (g0, step, L, n0, n1, n1 / L, "是" if has else "否", sname))
    if len(groups) > 40:
        w("    ... 其余 %d 组略" % (len(groups) - 40))
    w()

    # ---------- Part2：列标志候选（[5..7]=1, [8]=0）
    w("[Part2] 列标志候选：u16 序列 [5]=[6]=[7]=1 且 [8]=0（列 5/6/7 显示、8 隐藏）")
    cands = []
    for sname, a0, b0 in ranges:
        u = np.frombuffer(d[a0:a0 + ((b0 - a0) // 2) * 2], dtype="<u2")
        n = len(u)
        for i in range(n - 10):
            win = u[i:i + 10]
            if win[5] == 1 and win[6] == 1 and win[7] == 1 and win[8] == 0:
                if win[9] == 0 or True:
                    cands.append((a0 + i * 2, sname, win.tolist()))
    w("    命中 %d 处" % len(cands))
    for off, sname, win in cands[:20]:
        w("    0x%08X %-10s 10 项=%s" % (off, sname, win))
    w()

    # ---------- Part3：184 字节成族
    w("[Part3] 相距 0xB8(184) 的两个 2 字节项成族")
    fam = []
    for sname, a0, b0 in ranges:
        # 只看 Part1 命中的组内
        pass
    for g0, step, L, sname, n0, n1 in groups:
        seg = np.frombuffer(d[g0:g0 + L * step], dtype="<u2")[::step // 2]
        if step == 2 and L >= 92:
            for i in range(L - 92):
                if seg[i] == 1 and seg[i + 92] == 1:
                    fam.append((g0 + i * 2, g0 + i * 2 + 184))
    # 也对全 .rodata/.data 按 184 间隔找 0/1
    fam_all = []
    for sname, a0, b0 in ranges:
        u = np.frombuffer(d[a0:a0 + ((b0 - a0) // 2) * 2], dtype="<u2")
        for i in range(len(u) - 92):
            if u[i] <= 1 and u[i + 92] <= 1:
                # 要求前 4 与后 2 构成 1,1,1,1,0,0 模式
                if i + 6 <= len(u) and list(u[i:i + 6]) == [1, 1, 1, 1, 0, 0]:
                    fam_all.append(a0 + i * 2)
    w("    组内命中 %d 对；全段「4 个 1 + 2 个 0 且 +184 处也存在 0/1」= %d 处"
      % (len(fam), len(fam_all)))
    for o in fam_all[:12]:
        w("      0x%08X  (+184 -> 0x%08X)" % (o, o + 184))
    w()

    # ---------- Part4：选择能力候选
    w("[Part4] 选择能力候选（0x0000 且紧邻 0x0101 / 两个连续 0 字节）")
    sel = []
    for sname, a0, b0 in ranges:
        u = np.frombuffer(d[a0:a0 + ((b0 - a0) // 2) * 2], dtype="<u2")
        for i in range(len(u) - 2):
            if u[i] == 0 and u[i + 1] == 0x0101:
                sel.append((a0 + i * 2, sname, "0 后接 0x0101"))
    w("    命中 %d 处" % len(sel))
    for o, sname, why in sel[:12]:
        w("      0x%08X %-10s %s" % (o, sname, why))
    w("=" * 78)

    for path in (OUT_MAIN, OUT_COPY):
        dd = os.path.dirname(path)
        if not os.path.isdir(dd):
            os.makedirs(dd)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
