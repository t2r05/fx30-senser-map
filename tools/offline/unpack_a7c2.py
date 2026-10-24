#!/usr/bin/env python3
"""unpack_a7c2.py — 解开 Sony UFU 格式的 BODYDATA.DAT（4 代加密 FDAT）

背景：
  2020 年后的机身（A7C2 / A7M4 / A6700 / FX30 ...）官方固件包 `BODYDATA.DAT`
  外层是 **UFU 容器**，内部 FDAT 段是 **加密** 的（AES-CBC，4 代 crypter）。

  对比：
    - FX30 6.00 / A6700 2.00 / FX3 3.00 的 FDAT 段是 **明文**（直接 `UDTRFIRM` 开头）
    - A7C2 2.01 的 FDAT 段是 **密文**，需要 CXD90057_k8 解密

UFU 结构（实测）：
  magic(8) = 89 55 46 55 0d 0a 1a 0a          "\\x89UFU\\r\\n\\x1a\\n"
  然后重复：len(u32be) + tag(4 ASCII) + payload(len)
  实测 A7C2 2.01 的块序列：
    DATV(4)=1  PROV(4)=1  UDID(140)  FDAT(1,139,929,360)  DEND(4)

加密 FDAT 的尾部（由 fwtool 的 AesCbcCrypter 定义）：
  文件末 0x110 字节里，倒数第 0x110..0x100 处是 16 字节 IV；
  (size - 0x110) 必须是 1024 的整数倍。
  前 512 字节走 AES-ECB(key1)，之后走 AES-CBC(key2, IV)。

用法：
  python unpack_a7c2.py "F:/下载/BODYDATA (2).DAT" ./fw/a7c2out
"""
import io
import os
import struct
import sys

# fwtool 位置：优先 $FWTOOL_ROOT，其次同级 ./fwtool，再次 $PMCA_ROOT/fwtool
_here = os.path.dirname(os.path.abspath(__file__))
for _cand in [os.environ.get('FWTOOL_ROOT'),
              os.path.join(_here, 'fwtool'),
              os.path.join(_here, '..', '..', 'fwtool'),
              os.path.join(os.environ.get('PMCA_ROOT', ''), 'fwtool')]:
    if _cand and os.path.isdir(_cand):
        sys.path.insert(0, _cand)
        break
else:
    sys.exit('找不到 fwtool。请 git clone https://github.com/ma1co/fwtool.py 并设置 FWTOOL_ROOT')

from fwtool.sony import fdat  # noqa: E402

UFU_MAGIC = b'\x89UFU\r\n\x1a\n'
CRYPTER = 'CXD90057_k8'


def parse_ufu(path):
    """返回 [(tag, offset, length), ...] 与 udid 原始字节"""
    blocks = []
    udid = None
    total = os.path.getsize(path)
    with open(path, 'rb') as f:
        magic = f.read(8)
        if magic != UFU_MAGIC:
            raise SystemExit('不是 UFU 容器，magic=%r' % magic)
        off = 8
        while off + 8 <= total:
            f.seek(off)
            hdr = f.read(8)
            ln, tag = struct.unpack('>I4s', hdr)
            name = tag.decode('ascii', 'replace')
            if off + 8 + ln > total:
                print('  [!] 块越界，停止：off=%#x len=%d tag=%s' % (off, ln, name))
                break
            blocks.append((name, off + 8, ln))
            if name == 'UDID':
                f.seek(off + 8)
                udid = f.read(ln)
            print('  [%d] off=%#010x len=%12d tag=%s' % (len(blocks) - 1, off, ln, name))
            off += 8 + ln
    return blocks, udid


def describe_udid(udid):
    """UDID 块 = count(u32be) + count 组 (pid:u16le, vid:u16le)"""
    if not udid or len(udid) < 4:
        return
    cnt = struct.unpack('>I', udid[:4])[0]
    print('  UDID: %d 组 USB 描述符' % cnt)
    for i in range(cnt):
        o = 4 + i * 8
        pid, vid = struct.unpack('<HH', udid[o:o + 4])
        flag = struct.unpack('<I', udid[o + 4:o + 8])[0]
        kind = 'updater' if flag == 2 else 'normal'
        print('    %2d  VID=%04X PID=%04X  (%s)' % (i + 1, vid, pid, kind))


def extract_block(path, off, ln, dst):
    with open(path, 'rb') as f, open(dst, 'wb') as o:
        f.seek(off)
        left = ln
        while left > 0:
            b = f.read(min(1 << 24, left))
            if not b:
                break
            o.write(b)
            left -= len(b)
    print('  -> %s  (%d B)' % (dst, os.path.getsize(dst)))


def decrypt_fdat(src, dst, crypter_name=CRYPTER):
    size = os.path.getsize(src)
    if (size - 0x110) % 1024 != 0:
        print('  [!] (size-0x110) 不是 1024 整数倍：%d' % ((size - 0x110) % 1024))
    crypter = fdat._crypters[crypter_name]()
    with open(src, 'rb') as f:
        dec = crypter.decrypt(f)
        with open(dst, 'wb') as o:
            done = 0
            while True:
                b = dec.read(1 << 22)
                if not b:
                    break
                o.write(b)
                done += len(b)
                if done % (128 << 20) < (4 << 20):
                    print('    %5.1f%%  (%d / %d MB)' % (done * 100.0 / (size - 0x110),
                                                         done >> 20, (size - 0x110) >> 20))
    out = os.path.getsize(dst)
    print('  -> %s  (%d B)  crypter=%s' % (dst, out, crypter_name))
    with open(dst, 'rb') as f:
        head = f.read(16)
    print('     头: %r  %s' % (head, 'OK 明文 FDAT' if head.startswith(b'UDTRFIRM') else '!! 未解开'))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'fw', 'a7c2out')
    os.makedirs(outdir, exist_ok=True)

    print('[1] 解析 UFU 容器')
    blocks, udid = parse_ufu(src)
    describe_udid(udid)

    fdat_blocks = [b for b in blocks if b[0] == 'FDAT']
    if not fdat_blocks:
        raise SystemExit('没找到 FDAT 块')
    _, off, ln = fdat_blocks[0]

    enc = os.path.join(outdir, 'firmware_enc.fdat')
    print('\n[2] 提取 FDAT 密文段 -> %s' % enc)
    if not (os.path.exists(enc) and os.path.getsize(enc) == ln):
        extract_block(src, off, ln, enc)
    else:
        print('  (已存在且大小一致，跳过)')

    plain = os.path.join(outdir, 'firmware.fdat')
    print('\n[3] 用 %s 解密 -> %s' % (CRYPTER, plain))
    decrypt_fdat(enc, plain)

    print('\n[4] 后续：')
    print('  cd fwtool && python fwtool.py unpack -f ../a7c2out/firmware.fdat -o ../a7c2out')
    return 0


if __name__ == '__main__':
    sys.exit(main())
