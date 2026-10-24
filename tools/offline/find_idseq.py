#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 appFw.so 的数据段里找驱动模式 id 的连续序列（u32le）。"""
import sys, struct
from elftools.elf.elffile import ELFFile

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
SECS = ['.rodata', '.data', '.data.rel.ro']

def load(path):
    out = []
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        for s in elf.iter_sections():
            if s.name in SECS and s['sh_type'] == 'SHT_PROGBITS':
                out.append((s.name, s['sh_addr'], s.data()))
    return out

def scan(name, path):
    print('===', name)
    for sec, base, d in load(path):
        n = len(d) // 4
        words = struct.unpack_from('<%dI' % n, d)
        found = []
        for i, w in enumerate(words):
            if w != 0x1A2:
                continue
            nxt = words[i+1] if i+1 < n else None
            if nxt in (0x1A3, 0x1A4, 0x1AB):
                found.append((base + i*4, w, nxt))
        print('  %-14s size=%9d  A2-> 命中 %d' % (sec, len(d), len(found)))
        for a, w, nx in found[:12]:
            print('     0x%08X : 0x%03X -> 0x%03X  %s' % (a, w, nx,
                  '★完整(a3)' if nx == 0x1A3 else '缺 a3'))

for k, p in FILES.items():
    scan(k, p)
    print()
