#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T20_encrypt_fdat.py · 第十期 T1：把明文 fdat 加密回官方 FirmwareData.dat 格式

结构（来自 fwtool/sony/fdat.py 的 AesCbcCrypter + BlockCrypter，已按 decrypt 反写）：
  读入明文每 1020 字节 -> 打包成 1024 字节块：
      [0:2]   checksum(u16le) = sum(u16le of block[2:]) & 0xffff
      [2:4]   sizeAndEndFlag(u16le)：bit15=末块，bit0-14=有效长度
      [4:4+n] 数据，其余 0xFF 填充
  第 1 块：前 512 AES-ECB(key_aes) + 后 512 AES-CBC(key2, IV)
  第 2..N 块：全部 AES-CBC(key2)，状态跨块连续
  文件尾：IV(16) + 0x100（默认 0x00；可用 --tail 从真实加密件复制）

用法：
  python T20_encrypt_fdat.py --src <明文 fdat> --out <加密 dat>
        [--iv hex32] [--tail <0x100 字节文件>] [--crypter CXD90057_k8]
"""
import argparse
import os
import struct
import sys
import time

import numpy as np
from Cryptodome.Cipher import AES

FW = r"F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack\fw"
sys.path.insert(0, os.path.join(FW, "fwtool"))
from fwtool.sony import constants  # noqa: E402
from fwtool.sony import fdat as FDAT  # noqa: E402

BLK = 1024
PAY = 1020
BATCH = 4096          # 每批 4096 块 = 4 MB
TAIL = 0x110


def build_blocks(payload, last_flag):
    """payload: bytes（长度任意）-> (n,1024) uint8；最后一段带 bit15"""
    L = len(payload)
    nfull, rem = divmod(L, PAY)
    cnt = nfull + (1 if rem else 0)
    if cnt == 0:
        return np.zeros((0, BLK), dtype=np.uint8), 0
    arr = np.full((cnt, BLK), 0xFF, dtype=np.uint8)
    if nfull:
        body = np.frombuffer(payload[:nfull * PAY], dtype=np.uint8).reshape(nfull, PAY)
        arr[:nfull, 4:] = body
    if rem:
        arr[nfull, 4:4 + rem] = np.frombuffer(payload[nfull * PAY:], dtype=np.uint8)
    u2 = arr.view("<u2")
    sizes = np.full(cnt, PAY, dtype=np.uint32)
    if rem:
        sizes[-1] = rem
    if last_flag:
        sizes[-1] |= 0x8000
    u2[:, 1] = sizes.astype("<u2")
    cks = (u2[:, 1:].sum(axis=1, dtype=np.uint32) & 0xFFFF).astype("<u2")
    u2[:, 0] = cks
    return arr, cnt


def encrypt(src, dst, iv, tail100, crypter_name="CXD90057_k8"):
    cry = FDAT._crypters[crypter_name]()
    key_ecb = constants.key_aes
    key_cbc = cry._key
    ecb = AES.new(key_ecb, AES.MODE_ECB)
    cbc = AES.new(key_cbc, AES.MODE_CBC, iv)

    size = os.path.getsize(src)
    total_blocks = (size + PAY - 1) // PAY
    out_size = total_blocks * BLK + TAIL
    print("明文 %d B -> %d 块 -> 加密件 %d B（尾 %d）" % (size, total_blocks, out_size, TAIL))

    t0 = time.time()
    done = 0
    first = True
    with open(src, "rb") as f, open(dst, "wb") as o:
        while done < total_blocks:
            nb = min(BATCH, total_blocks - done)
            payload = f.read(nb * PAY)
            is_last_batch = (done + nb) >= total_blocks
            arr, cnt = build_blocks(payload, is_last_batch)
            if cnt == 0:
                break
            raw = arr.tobytes()
            if first:
                out = ecb.encrypt(raw[:512]) + cbc.encrypt(raw[512:BLK])
                if cnt > 1:
                    out += cbc.encrypt(raw[BLK:])
                first = False
            else:
                out = cbc.encrypt(raw)
            o.write(out)
            done += cnt
            el = time.time() - t0
            mb = done * BLK / 1048576.0
            print("  %5.1f%%  %7.1f MB  %5.1f MB/s"
                  % (done * 100.0 / total_blocks, mb, mb / el if el else 0),
                  end="\r", flush=True)
        o.write(iv)
        o.write(tail100)
    print("\n  输出 %s  (%d B)" % (dst, os.path.getsize(dst)))
    return out_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--iv", default=None, help="16 字节 hex（默认全 0，固定 -> 可复现）")
    ap.add_argument("--tail", default=None, help="0x100 字节文件（真实加密件的尾部剩余字段）")
    ap.add_argument("--crypter", default="CXD90057_k8")
    a = ap.parse_args()

    iv = bytes.fromhex(a.iv) if a.iv else b"\x00" * 16
    if len(iv) != 16:
        sys.exit("IV 必须 16 字节")
    if a.tail:
        tb = open(a.tail, "rb").read()
        if len(tb) != 0x100:
            sys.exit("--tail 必须正好 0x100 字节，实际 %d" % len(tb))
    else:
        tb = b"\x00" * 0x100
    print("IV = %s   tail[16:32] = %s" % (iv.hex(), tb[:16].hex()))
    encrypt(a.src, a.out, iv, tb, a.crypter)


if __name__ == "__main__":
    main()
