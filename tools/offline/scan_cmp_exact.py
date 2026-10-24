#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确统计 cmp <wreg>, #imm（驱动模式 id 段）在三机型 .text 的命中分布。"""
import os
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
TARGETS = [0x1a0, 0x1a1, 0x1a2, 0x1a3, 0x1a4, 0x1a5, 0x1ab]

def text_of(path):
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        for s in elf.iter_sections():
            if s.name == '.text':
                return s['sh_addr'], s.data()
    return None, None

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

for name, p in FILES.items():
    base, code = text_of(p)
    hits = {t: [] for t in TARGETS}
    for ins in md.disasm(code, base):
        if ins.mnemonic != 'cmp':
            continue
        o = ins.op_str
        if ', #' not in o:
            continue
        try:
            imm = int(o.split('#')[1], 0)
        except Exception:
            continue
        if imm in hits:
            hits[imm].append(ins.address)
    print('===', name, '  .text=%.1f MB' % (len(code)/1048576))
    for t in TARGETS:
        h = hits[t]
        print('   cmp #0x%03x : %-4d %s' % (t, len(h), ['0x%X'%a for a in h[:8]]))
    print()
