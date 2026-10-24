# 16 · 官方固件包（BODYDATA.DAT）解包

> 本仓库其他文档默认「固件已经解开了」。这一页补上前置步骤。
> **不同代机型封装方式不同** —— 直接把 FX30 的流程套到 A7C2 会失败，这里把差异写清楚。

核验日期：2026-10-24。样本：ILCE-7CM2（A7C II）Ver 2.01，`BODYDATA.DAT` 1,139,929,560 B。

---

## 一、两代封装：明文 vs 加密

| 机型 | 包内 FDAT 段 | 处理方式 |
|---|---|---|
| ILME-FX30 6.00 | **明文** `UDTRFIRM` | `fwtool unpack` 直接可解 |
| ILME-FX3 3.00 | **明文** | 同上 |
| ILCE-6700 2.00 | **明文** | 同上 |
| **ILCE-7CM2 2.01** | **密文**（高熵） | 需先按 4 代 crypter 解密 |

判据：`head -c 8` 看是否 `UDTRFIRM`。不是就是加密的。

---

## 二、外层：UFU 容器

```
magic(8) = 89 55 46 55 0d 0a 1a 0a          "\x89UFU\r\n\x1a\n"
重复: len(u32be) + tag(4 ASCII) + payload(len 字节)
```

A7C2 2.01 实测块序列：

| # | 偏移 | 长度 | tag | 内容 |
|---|---|---|---|---|
| 0 | `0x008` | 4 | `DATV` | 容器版本 1 |
| 1 | `0x014` | 4 | `PROV` | 1 |
| 2 | `0x020` | 140 | `UDID` | USB 描述符表 |
| 3 | `0x0b4` | 1,139,929,360 | `FDAT` | 固件主体（加密） |
| 4 | `0x43f1f1cc` | 4 | `DEND` | 结束标记 |

`UDID` 块结构：`count(u32be)` + `count × {pid:u16le, vid:u16le, kind:u32le}`，`kind=2` 表示 updater。
A7C2 是 16 组普通 + 1 组 updater（`054C:03E2`）；A6700 是 12+1；FX30 是 10+1。

---

## 三、内层：加密 FDAT

### 3.1 结构（fwtool 的 `AesCbcCrypter` 语义）

```
文件末 0x110 字节：倒数 0x110..0x100 处是 16 字节 IV
(size - 0x110) 必须是 1024 的整数倍
第 1 块 : 前 512 B 用 AES-ECB(key_aes)，后 512 B 用 AES-CBC(key2)
第 2..N : 全部 AES-CBC(key2)，状态跨块连续
```

### 3.2 每块解密后的布局（`BlockCrypter.unpackBlock`）

```
[0:2]  checksum (u16le)         = sum(u16le of data[2:]) & 0xffff
[2:4]  sizeAndEndFlag (u16le)   bit15 = 最后一块；bit0-14 = 有效长度
[4:4+size]  有效数据
```

A7C2 实测：1,113,212 块，其中 1,113,211 块满长 1020 B、末块 492 B。
末块 endFlag 落在第 1,113,211 块（0-based）。解密后 1,135,475,712 B。

### 3.3 找 crypter

密钥不在这里公开，直接用 [fwtool](https://github.com/ma1co/fwtool.py) 的注册表。
**逐个试，看哪个能解出 `UDTRFIRM`**：

```python
import sys; sys.path.insert(0, 'fwtool')
from fwtool.sony import fdat
for name, factory in fdat._crypters.items():
    d = factory().decrypt(open(path, 'rb'))
    if d.read(8) == b'UDTRFIRM':
        print('命中:', name)
```

A7C2 2.01 命中的是注册表里**最后一个**。所以别提前退出的循环。

---

## 四、性能：别用逐块实现

fwtool 的 `AesCbcCrypter` 每 1024 字节调一次 pycryptodome，Python 开销占绝对主导。

| 方案 | 速度 | 1.06 GiB |
|---|---|---|
| fwtool 原实现 | 1.3 MB/s | ~14 分钟 |
| `decrypt_fdat_fast.py` | **48.4 MB/s** | **41 秒** |

两个改动点：

1. **大块 CBC**：CBC 状态天然连续，一次喂 4 MB 与逐块调用等价（已逐字节验证）。
2. **numpy 拆包**：用 `np.repeat` + 累加和构造索引，一次性跳过所有块的 4 字节头，
   同时用 `a[:, 1:].sum(axis=1, dtype=np.uint32) & 0xffff` 批量算 checksum。

等价性用「同一段 64 KiB 分别由两种实现解密后比对」验证，逐字节一致。

---

## 五、解出分区

FDAT 解开后仍是一层容器（`firmware.tar` + `updater.img`），交给 fwtool：

```bash
python fwtool.py unpack -f firmware.fdat -o outdir
```

产出：

```
outdir/
├── config.yaml               ← model / version / crypter / USB 描述符
├── firmware.tar_unpacked/
│   ├── 0100_config  0110_backup  0300_partconf  0700_part_image …
│   └── 0700_part_image/dev/
│       ├── nflasha15      /usr          → nflasha15_unpacked/lib/appFw.so
│       ├── nflasha3       /system
│       ├── nflasha5       暖启动镜像
│       ├── nflasha7       rootfs
│       └── nflasha8       CP Data
└── updater.img
```

`config.yaml` 里的 `fdat.model` 是机型码，`fdat.version` 是固件版本 —— 后续所有对比都以这两个为准。

---

## 六、四机型镜像规模（同一版本族）

| 分区 | FX30 6.00 | FX3 3.00 | A6700 2.00 | A7C2 2.01 |
|---|---|---|---|---|
| `nflasha15` (/usr) | 571.9 MB | 457.6 MB | 642.5 MB | **734.4 MB** |
| `nflasha3` (/system) | 30.2 MB | 30.2 MB | 31.2 MB | 31.2 MB |
| `nflasha5` (WBI) | 200.8 MB | 199.5 MB | 237.1 MB | 254.8 MB |
| `nflasha7` (rootfs) | 5.0 MB | 5.0 MB | 5.0 MB | 5.0 MB |
| `nflasha8` (CP) | 22.9 MB | 21.4 MB | 23.8 MB | 23.9 MB |

四机型**全部带 `nflasha5` 暖启动镜像**（200~255 MB）。这是「关机再开机 ≠ 冷启动」的量化依据：
开机走的是镜像恢复路径，不是重新初始化。见 `docs/04` §二十一。

---

## 七、`libJiritsu.so` 的一个陷阱

| 机型 | 大小 | `.text` | SHA-256 |
|---|---|---|---|
| FX30 | **233,416** | 46,712 | `563573d0…` |
| FX3 | 225,200 | 45,352 | `bdef58b2…` |
| A6700 | **233,416** | 46,744 | `f515adb3…` |
| A7C2 | **233,416** | 46,656 | `87dc2491…` |

FX30 / A6700 / A7C2 **大小完全相同**，但 SHA 全不同，`.text` 字节级同率仅 **9.6%~9.8%**
（长度差 <0.2%）。

**这是同一份源码的不同链接实例** —— 地址常量全变，逻辑没变。

⇒ **不要用「N 字节块全同率」判断相似性**。本项目在 appFw.so 上已经踩过一次
（块全同率 0.00% vs 字节同率 79.48%，见 `docs/05`），这次在 `libJiritsu.so` 上再次复现：
块同率 0.28%~0.96%，字节同率 9.6%~9.8%，而两份代码长度几乎一样。
