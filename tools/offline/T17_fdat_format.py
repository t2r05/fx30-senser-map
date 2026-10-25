#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T17_fdat_format.py · 第七期 T1：firmware.fdat 容器格式

做法：
  1) 列 fw/out 下的固件文件与大小（只读）
  2) 打印 fdat 头部 256 字节（hex + ascii），识别 magic
  3) 假设验证：fdat = [522B 头] + updater.img + firmware.tar
     用字节相等校验各段的边界
  4) 头部逐字段解码：u32 视图全部列出，并与「各段大小 / zlib.crc32(各段)」比对
  5) 统计 'ustar' 出现位置，确认 tar 是整段嵌入
只读 fw/（只 open('rb')，不写回）。结果写 audit_raw/T17_task1_fdat.txt + tmp01 副本。
用法：
  "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -u T17_fdat_format.py
"""
import os
import struct
import sys
import zlib

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw\out"
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T17_task1_fdat.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T17_task1_fdat.txt"
FDAT = os.path.join(FW, "firmware.fdat")
TAR = os.path.join(FW, "firmware.tar")
UPD = os.path.join(FW, "updater.img")
lines = []


def w(s=""):
    lines.append(s)


def main():
    for p in (FDAT, TAR):
        if not os.path.isfile(p):
            sys.exit("缺少：%s" % p)
    fdat = open(FDAT, "rb").read()
    tar = open(TAR, "rb").read()
    upd = open(UPD, "rb").read() if os.path.isfile(UPD) else b""

    w("=" * 78)
    w("T17 · 第七期 T1 · firmware.fdat 容器格式")
    w("=" * 78)
    w("firmware.fdat  %d B" % len(fdat))
    w("firmware.tar   %d B" % len(tar))
    w("updater.img    %d B" % len(upd))
    w("fdat - tar = %d B" % (len(fdat) - len(tar)))
    w("512 + updater.img = %d B" % (512 + len(upd)))
    w()

    # ---- 头部
    head = fdat[:256]
    w("[1] 头部 0..0xFF（hex / ascii）")
    for off in range(0, 256, 16):
        ch = head[off:off + 16]
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in ch)
        w("    %04X  %s  |%s|" % (off, " ".join("%02X" % b for b in ch), asc))
    w()
    w("    前 8 字节 ascii = %r" % head[:8].decode("latin-1"))
    w("    前 8 字节 u64le = 0x%016X" % struct.unpack("<Q", head[:8])[0])
    w()

    # ---- 假设验证：三段式
    w("[2] 假设验证：fdat = [512B 头] + updater.img + firmware.tar")
    layout_ok = True
    if upd:
        seg1 = fdat[512:512 + len(upd)]
        eq1 = seg1 == upd
        w("    fdat[0x200:0x200+%d] == updater.img : %s" % (len(upd), eq1))
        layout_ok &= eq1
        off_tar = 512 + len(upd)
    else:
        off_tar = 512
    seg2 = fdat[off_tar:off_tar + len(tar)]
    eq2 = seg2 == tar
    w("    fdat[0x%X:0x%X+%d] == firmware.tar : %s" % (off_tar, off_tar, len(tar), eq2))
    layout_ok &= eq2
    tail = fdat[off_tar + len(tar):]
    w("    尾部剩余 %d B" % len(tail))
    if tail:
        w("    尾部前 32B = %s" % tail[:32].hex())
    w("    三段式假设成立：%s" % layout_ok)
    w()

    # ---- tar 整段嵌入的旁证
    us_fdat = []
    i = fdat.find(b"ustar")
    while i >= 0 and len(us_fdat) < 8:
        us_fdat.append(i)
        i = fdat.find(b"ustar", i + 1)
    us_tar = []
    i = tar.find(b"ustar")
    while i >= 0 and len(us_tar) < 8:
        us_tar.append(i)
        i = tar.find(b"ustar", i + 1)
    w("[3] 'ustar' 前 8 处  fdat=%s  tar=%s" % (us_fdat, us_tar))
    w("    tar 内 ustar 相对偏移 = fdat 内偏移 - %d ？ %s"
      % (off_tar, all(a - off_tar == b for a, b in zip(us_fdat, us_tar))))
    w()

    # ---- 头部 u32 字段全表
    crc_tar = zlib.crc32(tar) & 0xFFFFFFFF
    crc_upd = zlib.crc32(upd) & 0xFFFFFFFF if upd else 0
    w("[4] 头部 u32 字段（0x000-0x0FF），并与大小/CRC32 比对")
    w("    zlib.crc32(tar) = 0x%08X    zlib.crc32(updater.img) = 0x%08X" % (crc_tar, crc_upd))
    w("    tar size = 0x%X  updater.img size = 0x%X  fdat size = 0x%X"
      % (len(tar), len(upd), len(fdat)))
    w()
    w("    %-6s %-10s %-10s %s" % ("off", "u32", "ascii", "匹配"))
    for off in range(0, 256, 4):
        v = struct.unpack("<I", head[off:off + 4])[0]
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in head[off:off + 4])
        m = []
        if v == len(tar):
            m.append("=tar大小")
        if v == len(upd):
            m.append("=updater大小")
        if v == crc_tar:
            m.append("=crc32(tar)")
        if v == crc_upd and upd:
            m.append("=crc32(updater)")
        if v == len(fdat):
            m.append("=fdat大小")
        w("    0x%03X  0x%08X  |%s|  %s" % (off, v, asc, ",".join(m)))
    w()

    # ---- u64 视图（可能存 64 位大小）
    w("[5] 头部 u64 字段（0x000-0x0FF，步长 8）")
    for off in range(0, 128, 8):
        v = struct.unpack("<Q", head[off:off + 8])[0]
        m = []
        if v == len(tar):
            m.append("=tar大小")
        if v == len(upd):
            m.append("=updater大小")
        if v == off_tar:
            m.append("=tar起始偏移")
        if v == len(fdat):
            m.append("=fdat大小")
        w("    0x%03X  0x%016X  %s" % (off, v, ",".join(m)))
    w()

    # ---- 反向构造可行性
    w("[6] 反向构造可行性（只做判定，不写任何固件）")
    w("    组成：%s" % ("512B 头 + updater.img + firmware.tar" if layout_ok else "未验证"))
    w("    需保留的头字段：magic 8B + 其后 504B（含若干 u32/u64，见 [4][5]）")
    w("    可重建部分：updater.img、firmware.tar（字节相等）")
    w("    需重算部分：头部中与大小/CRC 相关的字段（若有）")
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
