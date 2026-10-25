#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
T20_ext4_replace.py · 第十期 T2：在 ext2/3/4（无 extents）镜像里替换文件内容

支持：
  --image <in> --path /lib/appFw.so --new <file> --out <image>
  不给 --new 时：原样复制（零改动验收 A）
行为：
  - 等长替换：只改数据块，不碰任何元数据
  - 变短替换：改 i_size，不回收块（安全，块残留为已分配）
  - 变长替换：直接拒绝（本工具只做 shrink）
只读 src 镜像，只写 --out。
"""
import argparse
import os
import struct
import sys

BLK = None


class Ext:
    def __init__(self, data):
        self.data = data
        sb = data[1024:2048]
        if struct.unpack("<H", sb[0x38:0x3a])[0] != 0xEF53:
            raise SystemExit("不是 ext 镜像")
        self.bs = 1024 << struct.unpack("<I", sb[0x18:0x1c])[0]
        self.inodes_count = struct.unpack("<I", sb[0x00:0x04])[0]
        self.blocks = struct.unpack("<I", sb[0x04:0x08])[0]
        self.inodes_per_group = struct.unpack("<I", sb[0x28:0x2c])[0]
        self.inode_size = struct.unpack("<H", sb[0x58:0x5a])[0]
        self.rev = struct.unpack("<I", sb[0x4c:0x50])[0]
        self.incompat = struct.unpack("<I", sb[0x60:0x64])[0]
        self.desc_size = struct.unpack("<H", sb[0xfe:0x100])[0] or 32
        self.first_data_block = struct.unpack("<I", sb[0x14:0x18])[0]
        self.gd_off = (self.first_data_block + 1) * self.bs
        self.ngroups = (self.blocks + 8191) // 8192

    def gd(self, g):
        o = self.gd_off + g * self.desc_size
        return struct.unpack("<III", self.data[o:o + 12])  # block_bitmap, inode_bitmap, inode_table

    def inode_off(self, ino):
        g = (ino - 1) // self.inodes_per_group
        idx = (ino - 1) % self.inodes_per_group
        _, _, it = self.gd(g)
        return it * self.bs + idx * self.inode_size

    def ino_size(self, ino):
        o = self.inode_off(ino)
        lo = struct.unpack("<I", self.data[o + 4:o + 8])[0]
        hi = struct.unpack("<I", self.data[o + 108:o + 112])[0] if self.rev else 0
        return lo | (hi << 32)

    def ino_blocks(self, ino):
        o = self.inode_off(ino)
        return list(struct.unpack("<15I", self.data[o + 40:o + 100]))

    def blk(self, n):
        return self.data[n * self.bs:(n + 1) * self.bs]

    def map_blk(self, ptrs, n):
        if n < 12:
            return ptrs[n]
        n -= 12
        per = self.bs // 4
        if n < per:
            ind = ptrs[12]
            if not ind:
                return 0
            return struct.unpack("<I", self.blk(ind)[n * 4:n * 4 + 4])[0]
        n -= per
        if n < per * per:
            dind = ptrs[13]
            if not dind:
                return 0
            i1, i2 = divmod(n, per)
            p1 = struct.unpack("<I", self.blk(dind)[i1 * 4:i1 * 4 + 4])[0]
            if not p1:
                return 0
            return struct.unpack("<I", self.blk(p1)[i2 * 4:i2 * 4 + 4])[0]
        n -= per * per
        tind = ptrs[14]
        if not tind:
            return 0
        i1, r = divmod(n, per * per)
        i2, i3 = divmod(r, per)
        p1 = struct.unpack("<I", self.blk(tind)[i1 * 4:i1 * 4 + 4])[0]
        if not p1:
            return 0
        p2 = struct.unpack("<I", self.blk(p1)[i2 * 4:i2 * 4 + 4])[0]
        if not p2:
            return 0
        return struct.unpack("<I", self.blk(p2)[i3 * 4:i3 * 4 + 4])[0]

    def read_file(self, ino):
        """流式读：按块拼接"""
        size = self.ino_size(ino)
        ptrs = self.ino_blocks(ino)
        out = bytearray()
        n = 0
        while len(out) < size:
            pb = self.map_blk(ptrs, n)
            if pb == 0:
                out.extend(b"\x00" * self.bs)
            else:
                out.extend(self.blk(pb))
            n += 1
        return bytes(out[:size])

    def listdir(self, ino):
        size = self.ino_size(ino)
        ptrs = self.ino_blocks(ino)
        ents = {}
        n = 0
        blob = bytearray()
        while len(blob) < size:
            pb = self.map_blk(ptrs, n)
            blob.extend(self.blk(pb) if pb else b"\x00" * self.bs)
            n += 1
        o = 0
        while o + 8 <= size:
            i, rec, nlen = struct.unpack("<IHB", blob[o:o + 7])
            if rec < 8:
                break
            nm = blob[o + 8:o + 8 + nlen].decode("latin-1")
            if nm not in (".", ".."):
                ents[nm] = i
            o += rec
        return ents

    def resolve(self, path):
        cur = 2
        for part in [p for p in path.split("/") if p]:
            ents = self.listdir(cur)
            if part not in ents:
                raise SystemExit("路径不存在：%s（卡在 %s）" % (path, part))
            cur = ents[part]
        return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--path")
    ap.add_argument("--new")
    ap.add_argument("--dump", action="store_true", help="把 --path 的内容导出到 --out")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    data = bytearray(open(a.image, "rb").read())
    fs = Ext(data)
    print("镜像 %s  bs=%d blocks=%d inodes=%d inode_size=%d incompat=0x%X"
          % (a.image, fs.bs, fs.blocks, fs.inodes_count, fs.inode_size, fs.incompat))

    if a.dump:
        ino = fs.resolve(a.path)
        blob = fs.read_file(ino)
        open(a.out, "wb").write(blob)
        print("导出 %s (inode %d) -> %s (%d B)" % (a.path, ino, a.out, len(blob)))
        return

    if not a.new:
        open(a.out, "wb").write(data)
        print("零改动：已复制 -> %s" % a.out)
        return

    ino = fs.resolve(a.path)
    old_size = fs.ino_size(ino)
    newdata = open(a.new, "rb").read()
    print("目标 inode=%d  原大小=%d  新大小=%d" % (ino, old_size, len(newdata)))

    if len(newdata) > old_size:
        sys.exit("新文件更长（%d > %d），本工具只做等长或变短" % (len(newdata), old_size))

    ptrs = fs.ino_blocks(ino)
    nblk = (len(newdata) + fs.bs - 1) // fs.bs
    for k in range(nblk):
        pb = fs.map_blk(ptrs, k)
        if pb == 0:
            sys.exit("逻辑块 %d 未分配（稀疏文件？），停止" % k)
        chunk = newdata[k * fs.bs:(k + 1) * fs.bs]
        o = pb * fs.bs
        data[o:o + len(chunk)] = chunk
        print("  写块 %d -> 物理 %d (%d B)" % (k, pb, len(chunk)), end="\r" if k % 200 else "\n")

    if len(newdata) != old_size:
        io = fs.inode_off(ino)
        struct.pack_into("<I", data, io + 4, len(newdata) & 0xFFFFFFFF)
        if fs.rev:
            struct.pack_into("<I", data, io + 108, len(newdata) >> 32)
        print("\n  i_size: %d -> %d（块未回收）" % (old_size, len(newdata)))

    open(a.out, "wb").write(data)
    print("已写出 %s (%d B)" % (a.out, len(data)))

    # 自校验：从输出镜像读回
    chk = Ext(bytearray(open(a.out, "rb").read()))
    got = chk.read_file(chk.resolve(a.path))
    print("读回大小 %d，与新文件一致：%s" % (len(got), got == newdata))


if __name__ == "__main__":
    main()
