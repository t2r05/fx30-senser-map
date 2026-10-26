#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T17_fdat_rebuild.py · 第七期 T1 实证：按解出的配方反向构造 fdat，并逐字节比对

配方（上一轮已解出）：
  fdat = header(512) + updater.img + firmware.tar
  header[0x000:0x008] = "UDTRFIRM"
  header[0x008:0x00C] = u32le(zlib.crc32(header[0x00C:0x200]))
  header[0x00C:0x200] = 其余字段（含 0x030 tar偏移 / 0x034 tar大小 / 0x048 updater大小）

本脚本：
  1) 在内存里重建 header，与原始 header 比对
  2) 流式比对：原始 fdat vs (重建 header + updater.img + firmware.tar)
  3) 只把重建的 512B header 写到 tmp01/fdat_rebuild/（不写 900MB 固件）
  4) 顺带列出 firmware.tar 里的 *_sum 条目（确认 sum 文本在 tar 内）
只读 fw/（open('rb')），不修改、不删除、不重新解包。
结果写 audit_raw/T17_task1_rebuild.txt + tmp01 副本。
用法：
  "$PY" -u T17_fdat_rebuild.py
"""
import hashlib
import os
import struct
import sys
import zlib

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw\out"
TMP = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\fdat_rebuild"
OUT_MAIN = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\audit_raw\T17_task1_rebuild.txt"
OUT_COPY = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\tmp01\T17_task1_rebuild.txt"

FDAT = os.path.join(FW, "firmware.fdat")
TAR = os.path.join(FW, "firmware.tar")
UPD = os.path.join(FW, "updater.img")
CHUNK = 1 << 20
lines = []


def w(s=""):
    lines.append(s)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def main():
    for p in (FDAT, TAR):
        if not os.path.isfile(p):
            sys.exit("缺少：%s" % p)
    if not os.path.isdir(TMP):
        os.makedirs(TMP)

    # ---- 1) 重建 header
    hdr = bytearray(open(FDAT, "rb").read(512))
    orig_hdr = bytes(hdr)
    crc = zlib.crc32(bytes(hdr[0x00C:0x200])) & 0xFFFFFFFF
    hdr[0x008:0x00C] = struct.pack("<I", crc)
    w("=" * 78)
    w("T17 · T1 实证 · 反向构造 fdat 并逐字节比对")
    w("=" * 78)
    w("[1] 重建 header")
    w("    magic            = %r" % bytes(hdr[0:8]).decode("latin-1"))
    w("    原 0x008 u32      = 0x%08X" % struct.unpack("<I", orig_hdr[8:12])[0])
    w("    重算 crc32[0xC:0x200] = 0x%08X" % crc)
    w("    重建 header == 原 header : %s" % (bytes(hdr) == orig_hdr))
    rebuild_path = os.path.join(TMP, "header_rebuilt.bin")
    with open(rebuild_path, "wb") as fh:
        fh.write(bytes(hdr))
    w("    重建 header 已写到临时目录：%s (%d B)" % (rebuild_path, len(hdr)))
    w()

    # ---- 2) 流式比对 fdat vs (header + updater + tar)
    w("[2] 流式比对：fdat vs (重建 header + updater.img + firmware.tar)")
    n_hdr, n_upd, n_tar = 512, os.path.getsize(UPD), os.path.getsize(TAR)
    total = n_hdr + n_upd + n_tar
    fdat_size = os.path.getsize(FDAT)
    w("    期望总长 = %d + %d + %d = %d ；实际 %d ；相等：%s"
      % (n_hdr, n_upd, n_tar, total, fdat_size, total == fdat_size))

    eq = True
    diff_at = None
    pos = 0
    with open(FDAT, "rb") as f_fdat, open(UPD, "rb") as f_upd, open(TAR, "rb") as f_tar:
        streams = [(len(hdr), hdr), (n_upd, f_upd), (n_tar, f_tar)]
        for ln, src in streams:
            remain = ln
            while remain > 0:
                n = min(CHUNK, remain)
                if isinstance(src, (bytes, bytearray)):
                    exp = bytes(src[len(src) - remain:len(src) - remain + n])
                else:
                    exp = src.read(n)
                got = f_fdat.read(n)
                if got != exp:
                    eq = False
                    for i in range(min(len(got), len(exp))):
                        if got[i] != exp[i]:
                            diff_at = pos + i
                            break
                    break
                pos += n
                remain -= n
            if not eq:
                break
    w("    逐字节相等：%s%s" % (eq, "" if eq else "（首处差异 0x%X）" % (diff_at or 0)))
    w("    说明：只比对，不写出 900MB 文件")
    w()

    # ---- 3) sha256 对照（原 fdat vs 概念流）
    w("[3] sha256")
    w("    原 fdat        = %s" % sha256_file(FDAT))
    h = hashlib.sha256()
    h.update(bytes(hdr))
    with open(UPD, "rb") as fh:
        for b in iter(lambda: fh.read(CHUNK), b""):
            h.update(b)
    with open(TAR, "rb") as fh:
        for b in iter(lambda: fh.read(CHUNK), b""):
            h.update(b)
    w("    header+upd+tar = %s" % h.hexdigest())
    w()

    # ---- 4) tar 里的 *_sum 条目
    w("[4] firmware.tar 内的 *_sum 条目（确认 sum 文本在 tar 中同源）")
    entries = []
    with open(TAR, "rb") as fh:
        while True:
            blk = fh.read(512)
            if len(blk) < 512 or blk == b"\x00" * 512:
                break
            name = blk[:100].split(b"\x00")[0].decode("latin-1")
            size_s = blk[124:136].split(b"\x00")[0].strip()
            try:
                size = int(size_s, 8) if size_s else 0
            except ValueError:
                size = 0
            if "_sum" in name:
                entries.append((name, size))
            fh.seek((size + 511) // 512 * 512, 1)
    for nm, sz in entries[:20]:
        w("    %-46s %d B" % (nm, sz))
    w("    合计 *_sum 条目 %d 个" % len(entries))
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
