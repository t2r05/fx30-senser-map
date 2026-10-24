#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prop_lookup.py —— 按 id 精确查 appFw.so 属性访问器记录并解出 .bss 地址。
用法: prop_lookup.py FX30 0x4B8,0x4BA,0x2B1,0x2AF,0xC2C
"""
import sys, struct
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
STRIDE, NSTUB = 0x58, 8

name = sys.argv[1]
ids = [int(x, 0) for x in sys.argv[2].split(',')]
with open(FILES[name], 'rb') as f:
    e = ELFFile(f)
    secs = {s.name: s for s in e.iter_sections() if s['sh_size']}
    t0, tsz = secs['.text']['sh_addr'], secs['.text']['sh_size']
    t1 = t0 + tsz
    dr = secs['.data.rel.ro']; d = dr.data(); drb = dr['sh_addr']
    bss = secs['.bss']; blo = bss['sh_addr']; bhi = blo + bss['sh_size']
    code = secs['.text'].data()

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM); md.detail = True

# 建 id -> 记录地址索引（全候选，不要求连续）
idx = {}
for i in range(0, len(d) - STRIDE, 8):
    idv = struct.unpack_from('<Q', d, i)[0]
    if idv > 0x2000:
        continue
    stubs = [struct.unpack_from('<Q', d, i + 0x10 + k * 8)[0] for k in range(NSTUB)]
    if all(t0 <= s < t1 for s in stubs):
        idx.setdefault(idv, []).append((drb + i, stubs,
                                        struct.unpack_from('<Q', d, i)[0],
                                        struct.unpack_from('<Q', d, i + 0x50)[0]))


def dec(va):
    page = None; out = []
    for ins in md.disasm(code[va - t0:va - t0 + 32], va):
        if ins.mnemonic == 'adrp':
            page = ins.operands[1].imm
        elif ins.mnemonic in ('ldr', 'str', 'ldrb', 'strb', 'ldrh', 'strh'):
            m = ins.operands[1].mem
            a = (page or 0) + m.disp
            if blo <= a < bhi:
                out.append((a, ins.mnemonic))
        elif ins.mnemonic in ('ret', 'b'):
            break
    return out


print('# %s  索引 id 数 %d' % (name, len(idx)))
for want in ids:
    hits = idx.get(want, [])
    if not hits:
        print('\n## id 0x%04X  —— 无记录' % want)
        continue
    if len(hits) > 1:
        print('\n## id 0x%04X  —— %d 条候选（取首条）' % (want, len(hits)))
    a, stubs, idv, tail = hits[0]
    print('\n## id 0x%04X  记录 0x%08X  tail=0x%08X' % (want, a, tail))
    for k, s in enumerate(stubs):
        tg = dec(s)
        print('   stub[%d] 0x%08X  %s' % (k, s, ', '.join('%s@0x%X' % (m, x) for x, m in tg) or '-'))
