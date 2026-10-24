#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 .data.rel.ro 里的 {char* name, u32 id, u32 meta} 表，输出 drive_mode 相关项。"""
import sys, struct
from elftools.elf.elffile import ELFFile

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
name = sys.argv[1]
path = FILES[name]
kw = sys.argv[2].encode() if len(sys.argv) > 2 else b'drive_mode'

with open(path, 'rb') as f:
    elf = ELFFile(f)
    secs = {s.name: s for s in elf.iter_sections() if s['sh_type'] == 'SHT_PROGBITS'}
    ro = secs['.rodata']; ro_d = ro.data(); ro_a = ro['sh_addr']; ro_end = ro_a + len(ro_d)
    dr = secs['.data.rel.ro']; d = dr.data(); base = dr['sh_addr']

    rows = []
    for i in range(0, len(d) - 16, 8):
        ptr = struct.unpack_from('<Q', d, i)[0]
        if not (ro_a <= ptr < ro_end):
            continue
        idv = struct.unpack_from('<I', d, i+8)[0]
        meta = struct.unpack_from('<I', d, i+12)[0]
        if not (0 < idv < 0x10000):
            continue
        off = ptr - ro_a
        s = ro_d[off:off+200].split(b'\x00')[0]
        if not s or len(s) < 3:
            continue
        try:
            txt = s.decode('latin1')
        except Exception:
            continue
        if not all(32 <= ord(c) < 127 for c in txt):
            continue
        rows.append((base+i, idv, meta, txt))

print('# 候选表项 %d 条 (%s)' % (len(rows), name))
sel = [r for r in rows if kw in r[3].encode()]
print('# 含 %r 的 %d 条:' % (kw.decode(), len(sel)))
print('%-12s %-6s %-6s %s' % ('va', 'id', 'meta', 'name'))
for va, idv, meta, txt in sel:
    print('0x%08X  0x%04X %-6d %s' % (va, idv, meta, txt))
