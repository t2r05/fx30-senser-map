#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T18_pack_fdat.py · 第八期 T1：fdat 重打包器（零改动必须 sha256 一致）

用法：
  python T18_pack_fdat.py --src <fdat> --out <fdat> [--replace <tar内路径>=<本地文件> ...] [--list]
  python T18_pack_fdat.py --verify <fdat>

自动流程：
  1) 读 src 的 512B 头，校验 magic / 0x008 CRC / 0x030 / 0x034 / 0x048
  2) 取出 tar 段，逐条目解析（512B 头原样保留，不重写）
  3) 对每个 --replace：读本地文件 -> crc32 -> 改写对应 .sum 行的第 2 字段
  4) 重打 tar（原顺序、原 header 块；仅尺寸变化的条目改 size 字段并重算 header checksum）
  5) header：0x034 = 新 tar 大小；0x008 = crc32(header[0x00C:0x200])
  6) 拼：header + updater 段（原样）+ new tar -> out
  7) 自校验：重读 out，验 header CRC / 尺寸 / tar 内每个文件 CRC 与 .sum 一致

红线：只读 src；只写 --out（建议放在 tmp01/fdat_rebuild/）；不碰 fw/。
"""
import argparse
import hashlib
import os
import struct
import sys
import zlib

BLK = 512
lines = []


def log(s=""):
    lines.append(s)
    print(s)


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def parse_tar(buf, base=0):
    """返回 (entries, trailer_off)。entry: dict(name,typeflag,size,hdr_off,data_off,raw_hdr)"""
    ents = []
    off = base
    n = len(buf)
    while off + BLK <= n:
        hdr = buf[off:off + BLK]
        if hdr == b"\x00" * BLK:
            # 结束块；把它及之后的内容都当 trailer
            return ents, off
        name = hdr[:100].split(b"\x00")[0].decode("latin-1")
        prefix = hdr[345:500].split(b"\x00")[0].decode("latin-1")
        if prefix:
            name = prefix + "/" + name
        size_s = hdr[124:136].split(b"\x00")[0].strip()
        try:
            size = int(size_s, 8) if size_s else 0
        except ValueError:
            size = 0
        tf = hdr[156:157]
        ents.append({"name": name, "typeflag": tf, "size": size,
                     "hdr_off": off, "data_off": off + BLK, "raw_hdr": bytes(hdr)})
        off = off + BLK + ((size + BLK - 1) // BLK) * BLK
    return ents, off


def patch_size(hdr, new_size):
    h = bytearray(hdr)
    chk_style = h[148:156]
    h[148:156] = b" " * 8
    h[124:136] = ("%011o" % new_size).encode()[:11] + b"\x00"
    s = sum(h)
    if chk_style.endswith(b"\x00 "):
        h[148:156] = ("%06o" % s).encode().rjust(6, b"0") + b"\x00 "
    elif chk_style.endswith(b"\x00\x00"):
        h[148:156] = ("%07o" % s).encode().rjust(7, b"0") + b"\x00"
    else:
        h[148:156] = ("%07o" % s).encode().rjust(7, b"0") + b"\x00"
    return bytes(h)


def parse_sum(text):
    """返回 [(line_no, parts)]"""
    out = []
    for i, ln in enumerate(text.split("\n")):
        if not ln.strip():
            continue
        out.append((i, ln.split(",")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src")
    ap.add_argument("--out")
    ap.add_argument("--replace", action="append", default=[])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verify")
    a = ap.parse_args()

    if a.verify:
        verify(a.verify)
        return
    if not a.src:
        sys.exit("需要 --src")
    if not a.out and not a.list:
        sys.exit("需要 --out（或只用 --list）")

    src = open(a.src, "rb").read()
    hdr = bytearray(src[:BLK])
    magic = bytes(hdr[:8]).decode("latin-1")
    crc_field = struct.unpack("<I", hdr[8:12])[0]
    tar_off = struct.unpack("<I", hdr[0x30:0x34])[0]
    tar_size = struct.unpack("<I", hdr[0x34:0x38])[0]
    upd_size = struct.unpack("<I", hdr[0x48:0x4C])[0]

    log("=" * 78)
    log("T18 · pack_fdat · %s -> %s" % (a.src, a.out))
    log("=" * 78)
    log("[0] src header: magic=%r crc=0x%08X tar_off=0x%X tar_size=0x%X upd=0x%X"
        % (magic, crc_field, tar_off, tar_size, upd_size))
    calc = crc32(bytes(hdr[0x00C:0x200]))
    log("    header CRC 实测 0x%08X / 重算 0x%08X / 一致 %s"
        % (crc_field, calc, crc_field == calc))
    log("    tar 段长度校验: %d == %d ? %s"
        % (len(src) - tar_off, tar_size, len(src) - tar_off == tar_size))
    log("    tar_off == 512 + upd ? %s" % (tar_off == 512 + upd_size))

    tar = src[tar_off:tar_off + tar_size]
    ents, trailer_off = parse_tar(tar)
    log("[1] tar 条目 %d 个，trailer 从 tar+0x%X 起（长度 %d）"
        % (len(ents), trailer_off, len(tar) - trailer_off))
    if a.list:
        for e in ents:
            log("    %s %s %d" % (e["typeflag"].decode("latin-1"), e["name"], e["size"]))
        return

    # ---- 替换
    repl = {}
    def canon(tp):
        for e in ents:
            if e["name"] == tp or e["name"].endswith("/" + tp):
                return e["name"]
        return tp

    for spec in a.replace:
        if "=" not in spec:
            sys.exit("--replace 格式应为 <tar内路径>=<本地文件>：%s" % spec)
        tp, lp = spec.split("=", 1)
        tp = canon(tp.lstrip("./"))
        if not os.path.isfile(lp):
            sys.exit("本地文件不存在：%s" % lp)
        data = open(lp, "rb").read()
        repl[tp] = data
        log("[2] 替换 %s <- %s (%d B, crc32=0x%08X)" % (tp, lp, len(data), crc32(data)))

    if not repl:
        log("[2] 无替换（零改动重打包）")

    # ---- 改写 .sum
    sum_changes = {}
    for tp, data in repl.items():
        new_crc = crc32(data)
        hit = 0
        for e in ents:
            if not e["name"].endswith(".sum") or e["typeflag"] != b"0":
                continue
            body = tar[e["data_off"]:e["data_off"] + e["size"]]
            txt = body.decode("latin-1")
            rows = parse_sum(txt)
            changed = False
            out_lines = txt.split("\n")
            for idx, parts in rows:
                hit_row = any(p and (tp == p or tp.endswith("/" + p)) for p in parts)
                if hit_row:
                    parts = list(parts)
                    parts[1] = "%08x" % new_crc
                    out_lines[idx] = ",".join(parts)
                    changed = True
                    hit += 1
            if changed:
                nb = "\n".join(out_lines).encode("latin-1")
                sum_changes[e["name"]] = nb
                log("    .sum 命中：%s（%d 行改动，%d B -> %d B）"
                    % (e["name"], hit, e["size"], len(nb)))
        if hit == 0:
            log("    !! 未在任何 .sum 中找到路径 %s" % tp)
        else:
            log("    路径 %s -> crc32 0x%08X 已写入 .sum" % (tp, new_crc))

    # ---- 重打 tar
    out_parts = []
    new_tar_size = 0
    for e in ents:
        data = repl.get(e["name"])
        if data is None and e["name"] in sum_changes:
            data = sum_changes[e["name"]]
        if data is None:
            if e["typeflag"] == b"5" or e["size"] == 0:
                out_parts.append(e["raw_hdr"])
                new_tar_size += BLK
            else:
                body = tar[e["data_off"]:e["data_off"] + e["size"]]
                pad = (-len(body)) % BLK
                out_parts.append(e["raw_hdr"])
                out_parts.append(body)
                out_parts.append(b"\x00" * pad)
                new_tar_size += BLK + len(body) + pad
        else:
            pad = (-len(data)) % BLK
            h = e["raw_hdr"] if len(data) == e["size"] else patch_size(e["raw_hdr"], len(data))
            out_parts.append(h)
            out_parts.append(data)
            out_parts.append(b"\x00" * pad)
            new_tar_size += BLK + len(data) + pad
    trailer = tar[trailer_off:]
    out_parts.append(trailer)
    new_tar_size += len(trailer)
    log("[3] 新 tar 大小 = %d（原 %d，差 %+d）" % (new_tar_size, tar_size, new_tar_size - tar_size))

    # ---- 新 header
    hdr[0x034:0x038] = struct.pack("<I", new_tar_size)
    hdr[0x008:0x00C] = struct.pack("<I", crc32(bytes(hdr[0x00C:0x200])))
    log("[4] 新 header: 0x034=0x%X 0x008=0x%08X"
        % (new_tar_size, struct.unpack("<I", hdr[8:12])[0]))

    # ---- 写出
    d = os.path.dirname(os.path.abspath(a.out))
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(a.out, "wb") as fh:
        fh.write(bytes(hdr))
        fh.write(src[BLK:tar_off])          # updater 段原样
        for p in out_parts:
            fh.write(p)
    log("[5] 已写出 %s（%d B）" % (a.out, os.path.getsize(a.out)))

    verify(a.out)


def verify(path):
    data = open(path, "rb").read()
    hdr = data[:BLK]
    crc_field = struct.unpack("<I", hdr[8:12])[0]
    tar_off = struct.unpack("<I", hdr[0x30:0x34])[0]
    tar_size = struct.unpack("<I", hdr[0x34:0x38])[0]
    upd_size = struct.unpack("<I", hdr[0x48:0x4C])[0]
    calc = crc32(hdr[0x00C:0x200])
    log("")
    log("-" * 78)
    log("[V] 自校验 %s" % path)
    log("    size            = %d" % len(data))
    log("    magic           = %r" % hdr[:8].decode("latin-1"))
    log("    header CRC      0x%08X == 0x%08X ? %s" % (crc_field, calc, crc_field == calc))
    log("    0x030 tar_off   0x%X == 512+upd(0x%X) ? %s"
        % (tar_off, 512 + upd_size, tar_off == 512 + upd_size))
    log("    0x034 tar_size  0x%X == 实际 %d ? %s"
        % (tar_size, len(data) - tar_off, tar_size == len(data) - tar_off))
    tar = data[tar_off:tar_off + tar_size]
    ents, trailer_off = parse_tar(tar)
    log("    tar 条目 %d，trailer %d B" % (len(ents), len(tar) - trailer_off))

    # .sum 内容与文件 CRC 对照
    sums = {}
    for e in ents:
        if e["name"].endswith(".sum") and e["typeflag"] == b"0":
            sums[e["name"]] = tar[e["data_off"]:e["data_off"] + e["size"]].decode("latin-1")
    checked = mismatch = missing = 0
    for e in ents:
        if e["typeflag"] != b"0" or e["size"] == 0 or e["name"].endswith(".sum"):
            continue
        body = tar[e["data_off"]:e["data_off"] + e["size"]]
        c = crc32(body)
        found = None
        for sn, txt in sums.items():
            for _, parts in parse_sum(txt):
                for p in parts:
                    if p and (e["name"] == p or e["name"].endswith("/" + p)):
                        found = (sn, parts[1])
        if found:
            checked += 1
            if found[1].lower() != "%08x" % c:
                mismatch += 1
                log("    !! CRC 不一致 %s：.sum=%s 实测=%08x" % (e["name"], found[1], c))
        else:
            missing += 1
    log("    .sum 对照：已核对 %d 个文件，一致 %d，不一致 %d，.sum 无记录 %d"
        % (checked, checked - mismatch, mismatch, missing))
    log("-" * 78)


if __name__ == "__main__":
    main()
