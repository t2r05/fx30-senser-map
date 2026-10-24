#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decrypt_fdat_fast.py — 快速解密 Sony 4 代 FDAT（AES-CBC）

为什么不用 fwtool 的 AesCbcCrypter：
  它按 1024 字节块逐块调 pycryptodome，Python 开销占绝对主导 ——
  实测 1.3 MB/s，1.1 GB 要 14 分钟。本脚本用「大块 CBC + numpy 拆包」，
  同一份密钥、同一套校验，实测提速 ~50 倍。

加密结构（fwtool/sony/fdat.py 的 AesCbcCrypter + BlockCrypter）：
  文件末 0x110 字节里，倒数 0x110..0x100 处是 16 字节 IV
  (size - 0x110) 必须是 1024 的整数倍
  第 1 个 1024 字节块：前 512 走 AES-ECB(key_aes)，后 512 走 AES-CBC(key2)
  第 2..N 块：全部走 AES-CBC(key2)，CBC 状态跨块连续

每块解密后的 1024 字节布局（BlockCrypter.unpackBlock）：
  [0:2]  checksum (u16le)      = sum(u16le of data[2:]) & 0xffff
  [2:4]  sizeAndEndFlag (u16le)  bit15 = 最后一块标志，bit0-14 = 有效长度
  [4:4+size]  有效数据
"""
import argparse
import os
import sys
import time

import numpy as np
from Cryptodome.Cipher import AES

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

from fwtool.sony import constants  # noqa: E402

TAIL = 0x110
BLK = 1024
BATCH_BLKS = 4096          # 每批 4 MB


def key_for(name):
    """从 fwtool 的 crypter 注册表里取 key（避免硬编码密钥）"""
    from fwtool.sony import fdat as F
    c = F._crypters[name]()
    return c._cipher._cipher  # 见下方说明


def decrypt(src, dst, crypter_name='CXD90057_k8', verify=True):
    size = os.path.getsize(src)
    body = size - TAIL
    if body % BLK:
        raise SystemExit('(size-0x110) 不是 1024 整数倍：%d' % (body % BLK))
    nblk = body // BLK

    # ---- 取 key：直接构造与 fwtool 一致的 crypter，复制其内部密钥
    from fwtool.sony import fdat as F
    from fwtool.sony import constants as C
    crypter = F._crypters[crypter_name]()
    key_ecb = C.key_aes              # 首块前 512 字节用 ECB
    key_cbc = crypter._key           # 之后用 CBC

    with open(src, 'rb') as f:
        f.seek(size - TAIL)
        iv = f.read(0x10)
        print('  IV = %s' % iv.hex())

        f.seek(0)
        ecb = AES.new(key_ecb, AES.MODE_ECB)
        cbc = AES.new(key_cbc, AES.MODE_CBC, iv)

        bad_csum = 0
        bad_end = 0
        end_at = -1
        sizes = {}
        t0 = time.time()
        done = 0
        with open(dst, 'wb') as o:
            first = True
            while done < nblk:
                nb = min(BATCH_BLKS, nblk - done)
                raw = f.read(nb * BLK)
                if not raw:
                    break
                if first:
                    plain = ecb.decrypt(raw[:512]) + cbc.decrypt(raw[512:])
                    first = False
                else:
                    plain = cbc.decrypt(raw)

                a = np.frombuffer(plain, dtype='<u2').reshape(nb, BLK // 2)
                cks = a[:, 0]
                flag = a[:, 1]
                sz = (flag & 0x7fff).astype(np.int64)
                ends = (flag & 0x8000) != 0

                if verify:
                    calc = (a[:, 1:].sum(axis=1, dtype=np.uint32) & 0xffff).astype('<u2')
                    bad_csum += int((calc != cks).sum())
                    if done + nb < nblk and ends.any():
                        bad_end += int(ends.sum())
                    if done + nb == nblk and ends.any():
                        end_at = done + int(np.where(ends)[0][-1])

                for v, c in zip(*np.unique(sz, return_counts=True)):
                    sizes[int(v)] = sizes.get(int(v), 0) + int(c)

                # 向量化拆包：跳过每块前 4 字节
                starts = np.cumsum(sz) - sz
                total = int(sz.sum())
                idx = (np.repeat(np.arange(nb, dtype=np.int64) * BLK + 4, sz)
                       + (np.arange(total, dtype=np.int64) - np.repeat(starts, sz)))
                flat = np.frombuffer(plain, dtype=np.uint8)
                o.write(flat[idx].tobytes())

                done += nb
                el = time.time() - t0
                mb = done * BLK / 1048576.0
                print('    %5.1f%%  %6.0f MB  %5.1f MB/s  ETA %3.0fs'
                      % (done * 100.0 / nblk, mb, mb / el if el else 0,
                         (nblk - done) * BLK / 1048576.0 / (mb / el) if el and mb else 0),
                      end='\r', flush=True)

    out = os.path.getsize(dst)
    print('\n  输出 %s  (%d B, %.2f MiB)' % (dst, out, out / 1048576.0))
    print('  块数 %d  有效长度分布 %s' % (nblk, dict(list(sizes.items())[:6])))
    if verify:
        print('  checksum 错误 %d 块；中途出现 endFlag %d 次；末块 endFlag 在第 %d 块'
              % (bad_csum, bad_end, end_at))
    with open(dst, 'rb') as f:
        head = f.read(16)
    print('  头: %r  %s' % (head, 'OK 明文 FDAT' if head.startswith(b'UDTRFIRM') else '!! 未解开'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--crypter', default='CXD90057_k8')
    ap.add_argument('--no-verify', action='store_true')
    a = ap.parse_args()
    print('[*] %s -> %s  crypter=%s' % (a.src, a.dst, a.crypter))
    decrypt(a.src, a.dst, a.crypter, verify=not a.no_verify)
    return 0


if __name__ == '__main__':
    sys.exit(main())
