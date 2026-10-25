#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T18_update_order.py · 第八期 T3：startupdate.sh 的分区写入顺序梳理

只做静态文本解析：
  1) 列 bin/ 下全部 .sh，逐个抽取：引用的 /dev/nflashaX、.sum 文件、外部命令（uc_*/ud_*）
  2) 按脚本名 + 行号给出「设备节点 -> 操作」表
  3) 汇总「更新流程顺序」（从 startupdate.sh / endupdate.sh 的调用链）
  4) 单独回答：只改 nflasha15 会牵动哪些分区（按脚本里实际出现的节点与操作）
只读 tmp01/updater_unpacked/。结果写 audit_raw/T18_task3_update_order.txt + tmp01 副本。
"""
import os
import re
import sys

ROOT = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\updater_unpacked"
BIN = os.path.join(ROOT, "bin")
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T18_task3_update_order.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T18_task3_update_order.txt"

NODE = re.compile(r"/dev/nflasha([0-9A-Fa-f]+)")
SUM = re.compile(r"([A-Za-z0-9_]+)\.sum")
CMD = re.compile(r"\b(uc_[a-z0-9_]+\.elf|ud_[a-z0-9_]+\.elf|getledval\.elf|us_[a-z0-9_]+\.sh|[a-z_]*firmup[a-z0-9_]*\.elf)\b")
lines = []


def w(s=""):
    lines.append(s)


def main():
    if not os.path.isdir(BIN):
        sys.exit("缺少：%s" % BIN)
    scripts = sorted(f for f in os.listdir(BIN) if f.endswith(".sh"))
    w("=" * 78)
    w("T18 · T3 · 更新脚本的分区节点与顺序")
    w("=" * 78)
    w("脚本 %d 个：%s" % (len(scripts), ", ".join(scripts)))
    w()

    w("[1] 逐脚本抽取（设备节点 / .sum / 命令）")
    w("    %-24s %-22s %-22s %s" % ("脚本", "设备节点", ".sum", "命令"))
    for s in scripts:
        p = os.path.join(BIN, s)
        txt = open(p, "r", encoding="latin-1").read()
        nodes = sorted(set("nflasha" + m for m in NODE.findall(txt)))
        sums = sorted(set(m + ".sum" for m in SUM.findall(txt)))
        cmds = sorted(set(CMD.findall(txt)))
        w("    %-24s %-22s %-22s %s"
          % (s, ",".join(nodes) or "-", ",".join(sums) or "-",
             ",".join(cmds[:5]) + ("..." if len(cmds) > 5 else "")))
    w()

    w("[2] 设备节点 -> 操作（按脚本/行号）")
    w("    %-16s %-24s %-6s %s" % ("节点", "脚本", "行", "语句"))
    for s in scripts:
        p = os.path.join(BIN, s)
        for i, ln in enumerate(open(p, "r", encoding="latin-1").read().split("\n"), 1):
            t = ln.strip()
            if t.startswith("#"):
                continue
            for m in NODE.finditer(t):
                w("    %-16s %-24s %-6d %s" % ("nflasha" + m.group(1), s, i, t[:90]))
    w()

    w("[3] 流程顺序（按被调用关系）")
    order = [
        ("1", "startupdate.sh", "预检 + 保留 Backup.bin（nflasha2）+ 取 dat2/dat3（nflasha1）+ 清 tmp（nflasha10）"),
        ("2", "us_crc32sum*.sh", "按分区校验 .sum（各脚本自带 TARGET_DIR 与 EXEC）"),
        ("3", "us_mkfs.sh", "edisx.elf 写分区表（/dev/nflasha）+ nflasha2 挂载/格式化"),
        ("4", "us_r_firmup.sh EMIF", "★ 主体韧体写入（脚本不在本包内，由 /usr/bin 提供）"),
        ("5", "us_r_fpga_updater.sh R_VUP", "★ FPGA 更新（同上，不在本包内）"),
        ("6", "endupdate.sh", "重写 Backup.bin（nflasha2）+ 擦 MPR（ud_lerase /dev/nflasha 4）+ 格式化 nflasha24"),
    ]
    for no, sc, desc in order:
        w("    %-3s %-26s %s" % (no, sc, desc))
    w()

    w("[4] 与 nflasha15 的关系")
    w("    - nflasha15 只出现在 0701_part_image_sum/part_image.sum 里（dev/nflasha15 行）")
    w("    - 本包内没有任何 .sh 直接写 /dev/nflasha15：主体写入在 us_r_firmup.sh（缺）里")
    w("    - 更新流程本身会触碰：nflasha1(dat2/dat3 读) / nflasha2(Backup.bin 读写) /")
    w("      nflasha4(擦 MPR) / nflasha10(tmp) / nflasha23(PMBp) / nflasha24(用户区格式化)")
    w("    - 这些动作与「改不改 nflasha15 内容」无关，是升级流程固有步骤")
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
