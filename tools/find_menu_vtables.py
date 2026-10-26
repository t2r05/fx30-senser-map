#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_menu_vtables.py — 用 RTTI 名字定位 vtable，并打印各槽内容

用法:
    python find_menu_vtables.py dump/appFw.so.orig rep_menu_controller
    python find_menu_vtables.py fw/fx3out/.../appFw.so rep_menu_controller
    python find_menu_vtables.py <appFw> menu --max 40

原理（Itanium C++ ABI）:
    typeinfo+0x08 -> name 字符串
    vtable-0x08   -> typeinfo
    vtable+0x00   -> slot0
.appFw 是 ET_DYN，RELATIVE 重定位的 addend 就是链接期 vaddr，直接可读。
"""
import struct
import sys

from elftools.elf.elffile import ELFFile

MOV0 = 0x52800000
MOV1 = 0x52800020
RET = 0xD65F03C0


class Img:
    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        f = open(path, "rb")
        e = ELFFile(f)
        self.segs = []
        execr = []
        for s in e.iter_segments():
            if s["p_type"] == "PT_LOAD":
                self.segs.append((s["p_vaddr"], s["p_vaddr"] + s["p_memsz"],
                                  s["p_offset"], s["p_filesz"]))
                if s["p_flags"] & 1:
                    execr.append((s["p_vaddr"], s["p_vaddr"] + s["p_memsz"]))
        self.execr = execr
        self.rel = {}
        rela = e.get_section_by_name(".rela.dyn")
        if rela:
            for r in rela.iter_relocations():
                if r["r_info_type"] == 1027:
                    self.rel[r["r_offset"]] = r["r_addend"]

    def foff(self, v):
        for va, ve, off, fsz in self.segs:
            if va <= v < ve:
                d = v - va
                return off + d if d < fsz else None
        return None

    def u64(self, v):
        o = self.foff(v)
        if o is None or o + 8 > len(self.data):
            return None
        return struct.unpack_from("<Q", self.data, o)[0]

    def u32(self, v):
        o = self.foff(v)
        if o is None or o + 4 > len(self.data):
            return None
        return struct.unpack_from("<I", self.data, o)[0]

    def cstr(self, v):
        o = self.foff(v)
        if o is None:
            return b""
        z = self.data.find(b"\0", o)
        return self.data[o:z if z >= 0 else len(self.data)]

    def in_exec(self, v):
        return any(a <= v < b for a, b in self.execr)

    def kind(self, fn):
        if fn is None or not self.in_exec(fn):
            return "?"
        c0, c1 = self.u32(fn), self.u32(fn + 4)
        if c0 == MOV0 and c1 == RET:
            return "0"
        if c0 == MOV1 and c1 == RET:
            return "1"
        return "F"


def find(img, needle, maxn):
    raw = needle.encode()
    out = []
    start = 0
    while True:
        p = img.data.find(raw, start)
        if p < 0:
            break
        start = p + 1
        # 回退十进制长度前缀（Itanium name 指针指向 "19rep_..." 的 '1'）
        q = p
        while q > 0 and img.data[q-1:q].isdigit():
            q -= 1
        p = q
        # 该字符串的 vaddr（需要在某个 LOAD 的文件区内）
        sv = None
        for va, ve, off, fsz in img.segs:
            if off <= p < off + fsz:
                sv = va + (p - off)
                break
        if sv is None:
            continue
        # name 字段的 r_offset = typeinfo+8，addend = sv
        for off2, add in img.rel.items():
            if add != sv:
                continue
            ti = off2 - 8
            # 指向 typeinfo 的 vtable-8 槽
            for off3, add2 in img.rel.items():
                if add2 != ti:
                    continue
                vt = off3 + 8
                out.append((sv, ti, vt))
                if len(out) >= maxn:
                    return out
    return out


def show(img, name, sv, ti, vt):
    print("\n== %r" % name)
    print("   name=0x%X  typeinfo=0x%X  vtable=0x%X" % (sv, ti, vt))
    sig = ""
    for i in range(19):
        fn = img.u64(vt + 8 * i)
        k = img.kind(fn)
        sig += k
        print("   slot%02d  %s  0x%08X" % (i, k, fn or 0))
    print("   signature: %s" % sig)


def main(path, needle, maxn):
    img = Img(path)
    print("文件: %s (%d B, RELATIVE=%d)" % (path, len(img.data), len(img.rel)))
    hits = find(img, needle, maxn)
    print("命中 vtable: %d" % len(hits))
    for sv, ti, vt in hits:
        name = img.cstr(sv)
        show(img, name, sv, ti, vt)
    return 0 if hits else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    mx = 8
    if "--max" in sys.argv:
        mx = int(sys.argv[sys.argv.index("--max") + 1])
    sys.exit(main(sys.argv[1], sys.argv[2], mx))
