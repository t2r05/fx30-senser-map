#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反汇编 appFw.so 指定 va 区间。用法: dis_range.py FX30 0x23CA180 0x23CA400"""
import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
name, lo, hi = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
with open(FILES[name], 'rb') as f:
    elf = ELFFile(f)
    sec = None
    for s in elf.iter_sections():
        a = s['sh_addr']; sz = s['sh_size']
        if a <= lo < a + sz:
            sec = s; break
    if sec is None:
        print('va not in any section'); sys.exit(1)
    off = lo - sec['sh_addr']
    data = sec.data()[off:off + (hi - lo)]
    print('# section %s  va 0x%X  size %d' % (sec.name, lo, len(data)))
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for ins in md.disasm(data, lo):
        note = ''
        o = ins.op_str
        if 'bl' == ins.mnemonic or ins.mnemonic.startswith('b.') or ins.mnemonic == 'b':
            note = '   <<<'
        print('0x%08X  %-8s %s%s' % (ins.address, ins.mnemonic, o, note))
