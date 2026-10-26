#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_predicates.py — 核对 rep_menu_controller 的 19 槽谓词表

用法:
    python verify_predicates.py dump/appFw.so.orig
    python verify_predicates.py fw/fx3out/.../appFw.so --vtable 0x...

默认基类 vtable = 0x4535168（FX30 6.00 实证；SHA-256 72d9136f...）。
判定:
    slot0..3  真函数
    slot4..18 8 字节桩: mov w0,#0 ; ret (0x52800000/0xD65F03C0)
    slot6     唯一 mov w0,#1 ; ret (0x52800020)
退出码 0 = 全部符合；1 = 有偏差（打印每个槽）。
"""
import hashlib
import struct
import sys

from elftools.elf.elffile import ELFFile

MOV0 = 0x52800000
MOV1 = 0x52800020
RET = 0xD65F03C0
BASE_VTABLE = 0x4535168


def main(path, vtable):
    data = open(path, "rb").read()
    e = ELFFile(open(path, "rb"))
    segs = []
    for s in e.iter_segments():
        if s["p_type"] == "PT_LOAD":
            segs.append((s["p_vaddr"], s["p_vaddr"] + s["p_memsz"],
                         s["p_offset"], s["p_filesz"]))

    def foff(v):
        for va, ve, off, fsz in segs:
            if va <= v < ve:
                d = v - va
                return off + d if d < fsz else None
        return None

    def u64(v):
        o = foff(v)
        if o is None or o + 8 > len(data):
            return None
        return struct.unpack_from("<Q", data, o)[0]

    def u32(v):
        o = foff(v)
        if o is None or o + 4 > len(data):
            return None
        return struct.unpack_from("<I", data, o)[0]

    print("文件 : %s" % path)
    print("大小 : %d" % len(data))
    print("SHA256: %s" % hashlib.sha256(data).hexdigest())
    print("vtable: 0x%X  (typeinfo @ -8 = 0x%X)" % (vtable, u64(vtable - 8) or 0))
    print()
    bad = 0
    zeros = 0
    for i in range(19):
        fn = u64(vtable + 8 * i)
        if fn is None:
            print("slot%02d  UNMAPPED" % i)
            bad += 1
            continue
        c0, c1 = u32(fn), u32(fn + 4)
        kind = "真函数"
        ok = (i <= 3)
        if c0 == MOV0 and c1 == RET:
            kind = "mov w0,#0 ; ret"
            zeros += 1
            ok = (i != 6)
        elif c0 == MOV1 and c1 == RET:
            kind = "mov w0,#1 ; ret"
            ok = (i == 6)
        if not ok:
            bad += 1
        print("slot%02d  @0x%08X  %-18s %s" % (i, fn, kind, "OK" if ok else "偏差"))
    print()
    print("返回 0 的桩: %d / 14" % zeros)
    if bad or zeros != 14:
        print("结论: 不符合基线（偏差 %d 项）" % bad)
        return 1
    print("结论: 与 FX30 6.00 基线一致")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    vt = BASE_VTABLE
    for a in sys.argv[2:]:
        if a.startswith("--vtable="):
            vt = int(a.split("=", 1)[1], 0)
        elif a.startswith("--vtable"):
            vt = int(sys.argv[sys.argv.index(a) + 1], 0)
    sys.exit(main(sys.argv[1], vt))
