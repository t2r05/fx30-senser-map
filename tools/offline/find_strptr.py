#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找指向目标字符串的 8 字节指针，并 dump 周边结构（疑似 name->id 映射表）。"""
import sys, struct
from elftools.elf.elffile import ELFFile

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
name, target = sys.argv[1], sys.argv[2].encode()
path = FILES[name]

with open(path, 'rb') as f:
    elf = ELFFile(f)
    addr = None; strsec = None
    for s in elf.iter_sections():
        if s['sh_type'] != 'SHT_PROGBITS': continue
        i = s.data().find(target)
        if i >= 0:
            addr = s['sh_addr'] + i; strsec = s.name; break
    print('# target va=0x%X in %s' % (addr, strsec))
    pat = struct.pack('<Q', addr)
    for s in elf.iter_sections():
        if s['sh_type'] != 'SHT_PROGBITS': continue
        d = s.data(); start = 0
        while True:
            i = d.find(pat, start)
            if i < 0: break
            va = s['sh_addr'] + i
            lo = max(0, i-48); hi = min(len(d), i+80)
            print('\n## 指针在 %s va=0x%X' % (s.name, va))
            for o in range(lo, hi, 8):
                v = struct.unpack_from('<Q', d, o)[0]
                mark = '  <== target' if s['sh_addr']+o == va else ''
                print('   0x%08X  %016X%s' % (s['sh_addr']+o, v, mark))
            start = i + 1
