#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""desc_lookup.py —— 按功能 id 取 80 字节描述符并列出非零字段。
用法: desc_lookup.py FX30 0x272,0x273,0x278,0x1A3
"""
import sys, struct
from elftools.elf.elffile import ELFFile

FILES = {
    'FX30': 'fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'FX3': 'fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so',
}
# 三张表：上界 + 全局指针 va（来自描述符访问器 0x1DBCEE0 反汇编）
# 注意：访问器是【升序】判断，0x1A3(419) < 0x4B7(1207) < 0x1045(4165)
TABLES = [(0x1A3, 0x477B5A0), (0x04B7, 0x4783120), (0x1045, 0x46FAB70)]
FALLBACK = [0x4771710, 0x4709E0, 0x4706B58]

name = sys.argv[1]
ids = [int(x, 0) for x in sys.argv[2].split(',')]
with open(FILES[name], 'rb') as f:
    e = ELFFile(f)
    secs = []
    for s in e.iter_sections():
        if s['sh_type'] == 'SHT_PROGBITS' and s['sh_size']:
            secs.append((s.name, s['sh_addr'], s.data()))


def rd(va, n):
    for nm, b, d in secs:
        if b <= va < b + len(d):
            o = va - b
            return d[o:o + n]
    return None


def q(va):
    b = rd(va, 8)
    return struct.unpack('<Q', b)[0] if b else None


print('# %s' % name)
for i, (lim, gptr) in enumerate(TABLES):
    base = q(gptr)
    print('#   表%d 上界 0x%X  全局 0x%X -> base %s' %
          (i + 1, lim, gptr, 'None' if base is None else '0x%X' % base))
print()
for want in ids:
    ti = 0
    for k, (lim, gptr) in enumerate(TABLES):
        if want <= lim:
            ti = k
            break
    base = q(TABLES[ti][1])
    if base is None:
        print('## id 0x%04X  表%d base 缺失' % (want, ti + 1)); continue
    dp = q(base + want * 8)
    if not dp:
        dp = q(FALLBACK[ti])
        src = 'fallback'
    else:
        src = 'table'
    if not dp:
        print('## id 0x%04X  无描述符' % want); continue
    blob = rd(dp, 80)
    if blob is None:
        print('## id 0x%04X  描述符 0x%X 不可读' % (want, dp)); continue
    w = struct.unpack('<20I', blob)
    print('## id 0x%04X  表%d  描述符 0x%08X (%s)' % (want, ti + 1, dp, src))
    print('   u32[0..19]: ' + ' '.join('%X' % x for x in w))
    print('   flags 0x0C-0x17: ' + ' '.join('%02X' % b for b in blob[0x0C:0x18]))
    nz = [(i, struct.unpack_from('<I', blob, i)[0]) for i in range(0, 80, 4)]
    print('   非零字段: ' + ', '.join('+0x%02X=%X' % (o, v) for o, v in nz if v))
