#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T17_fdat_crc.py · 第七期 T1 补充：头部 0x008 的 u32(0x72AE7FD0) 是不是 CRC

枚举候选组合（zlib.crc32，LE 存放），逐一比对：
  - tar / updater.img 整段
  - fdat 的若干子区间（含/不含 512B 头、含/不含自己）
  - header 各子区间，以及「把 0x008 处 4 字节清零后」的 header
另外报告该值按大端解释 = 0xD07FAE72 的比对结果。
只读 fw/。结果写 audit_raw/T17_task1_crc.txt + tmp01 副本。
"""
import os
import struct
import sys
import zlib

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw\out"
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T17_task1_crc.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T17_task1_crc.txt"
lines = []


def w(s=""):
    lines.append(s)


def main():
    fdat = open(os.path.join(FW, "firmware.fdat"), "rb").read()
    tar = open(os.path.join(FW, "firmware.tar"), "rb").read()
    upd = open(os.path.join(FW, "updater.img"), "rb").read()
    f0 = struct.unpack("<I", fdat[8:12])[0]
    fb = struct.unpack(">I", fdat[8:12])[0]

    w("=" * 78)
    w("T17 · T1 补充 · 头部 0x008 = 0x%08X（BE 视图 0x%08X）的 CRC 归属" % (f0, fb))
    w("=" * 78)

    cands = []
    # 整段
    cands.append(("tar 全文", zlib.crc32(tar) & 0xFFFFFFFF))
    cands.append(("updater.img 全文", zlib.crc32(upd) & 0xFFFFFFFF))
    cands.append(("updater+tar", zlib.crc32(fdat[512:]) & 0xFFFFFFFF))
    cands.append(("fdat 全文", zlib.crc32(fdat) & 0xFFFFFFFF))
    # header 子区间
    hdr = fdat[:512]
    for lo, hi in ((0, 512), (8, 512), (12, 512), (16, 512), (32, 512), (48, 512),
                   (12, 0x20), (0x0C, 0x30), (0x20, 0x40), (0x30, 0x60)):
        cands.append(("header[0x%X:0x%X]" % (lo, hi), zlib.crc32(hdr[lo:hi]) & 0xFFFFFFFF))
    # 把 0x008 清零后的 header / fdat
    h2 = bytearray(hdr)
    h2[8:12] = b"\x00\x00\x00\x00"
    cands.append(("header 0x008 清零 全长", zlib.crc32(bytes(h2)) & 0xFFFFFFFF))
    f2 = bytearray(fdat[:512])
    f2[8:12] = b"\x00\x00\x00\x00"
    cands.append(("header 0x008 清零 [0:0x30]", zlib.crc32(bytes(f2[:0x30])) & 0xFFFFFFFF))
    # 尾段（512 头之后各段）
    cands.append(("fdat[512:512+0xFB000]", zlib.crc32(fdat[512:512 + 0xFB000]) & 0xFFFFFFFF))

    w("    %-32s %-12s %-6s" % ("候选范围", "crc32", "匹配"))
    for name, v in cands:
        w("    %-32s 0x%08X   %s" % (name, v, "★" if v in (f0, fb) else ""))

    # 额外：CRC32 变体（反射/初值）快速试
    def crc32_variant(data, init, refin):
        c = init
        for b in data:
            if refin:
                c ^= b
                for _ in range(8):
                    c = (c >> 1) ^ (0xEDB88320 if c & 1 else 0)
            else:
                c ^= (b << 24)
                for _ in range(8):
                    c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
        return c & 0xFFFFFFFF

    w()
    w("[2] 变体试算（只对 header[0:0x200]，init=0/0xFFFFFFFF × refin T/F）")
    for init in (0, 0xFFFFFFFF):
        for refin in (True, False):
            v = crc32_variant(hdr, init, refin)
            hit = "★" if v in (f0, fb) else ""
            w("    init=0x%08X refin=%-5s -> 0x%08X %s" % (init, refin, v, hit))
    w()
    w("[3] 与头部其它字段的关系")
    w("    0x010 u32 = %d (0x%X)  0x014 u32 = %d (0x%X)"
      % (struct.unpack("<I", hdr[0x10:0x14])[0], struct.unpack("<I", hdr[0x10:0x14])[0],
         struct.unpack("<I", hdr[0x14:0x18])[0], struct.unpack("<I", hdr[0x14:0x18])[0]))
    w("    0x020 u32 = 0x%X（十进制 %d，可能是版本 6.01）"
      % (struct.unpack("<I", hdr[0x20:0x24])[0], struct.unpack("<I", hdr[0x20:0x24])[0]))
    w("    0x024 u32 = 0x%X" % struct.unpack("<I", hdr[0x24:0x28])[0])
    w("    0x030 u32 = 0x%X（= tar 起始偏移 0x%X）"
      % (struct.unpack("<I", hdr[0x30:0x34])[0], 512 + len(upd)))
    w("    0x034 u32 = 0x%X（= tar 大小 0x%X）"
      % (struct.unpack("<I", hdr[0x34:0x38])[0], len(tar)))
    w("    0x048 u32 = 0x%X（= updater 大小 0x%X）"
      % (struct.unpack("<I", hdr[0x48:0x4C])[0], len(upd)))
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
