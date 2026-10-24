#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给定目标字符串，换算 va 并在 .text 里找 adrp+add 引用。"""
import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
name = sys.argv[1]
target = sys.argv[2].encode()
path = FILES[name]

with open(path, 'rb') as f:
    elf = ELFFile(f)
    # 1) 定位字符串 va
    addr = None
    for s in elf.iter_sections():
        if s['sh_type'] != 'SHT_PROGBITS':
            continue
        d = s.data()
        i = d.find(target)
        if i >= 0:
            addr = s['sh_addr'] + i
            print('# 字符串在 %s  va=0x%X (off 0x%X)' % (s.name, addr, i))
            break
    if addr is None:
        print('字符串未找到'); sys.exit(1)
    # 2) .text 反汇编，找 adrp+add
    tsec = None
    for s in elf.iter_sections():
        if s.name == '.text':
            tsec = s; break
    base = tsec['sh_addr']; code = tsec.data()

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True
page = addr & ~0xFFF
hits = []
prev = None
for ins in md.disasm(code, base):
    if prev is not None and prev.mnemonic == 'adrp' and ins.mnemonic == 'add':
        # adrp xN, #page ; add xN, xN, #off
        try:
            prd = prev.operands[0].reg
            if ins.operands[0].reg == prd and ins.operands[1].reg == prd:
                pi = prev.operands[1].imm
                oi = ins.operands[2].imm
                if pi + oi == addr:
                    hits.append(prev.address)
        except Exception:
            pass
    prev = ins
print('# adrp+add 引用命中 %d 处' % len(hits))
for h in hits[:20]:
    print('   0x%08X' % h)
