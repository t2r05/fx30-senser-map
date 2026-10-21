# ILME-FX30 Service Mode Research

**索尼 FX30（Ver.6.00）服务模式的通道边界测绘**

> 本仓库记录在 ILME-FX30 固件 6.00 上对 USB 服务会话（Senser / Jiritsu）的实测探索：哪些通道可达、哪些被裁剪、数据长什么样。
> **不含固件二进制、不含备份数据、不含机身唯一信息。**

[English summary](#english-summary)

---

## 一句话结论

FX30 的服务模式**纯软件可达**（一根 Type-C + libusbK 双设备驱动），但它的会话层只开放了 **2 个 pFunc**，**文件通道与内存通道均不响应**——这与同平台的 A6700 存在实质差异。

---

## 环境

| 项 | 值 |
|---|---|
| 机身 | ILME-FX30 |
| 固件 | Ver.6.00 |
| 主机 | Windows 11 |
| 驱动 | **Zadig + libusbK**（MSC 与 0336 两个设备**都要换**） |
| Python | 3.11 + pyusb 1.3.1 |
| 参考实现 | [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)（认证帧格式） |

---

## 核心发现

### 1. 会话可达（已复现多次）

```
USB 枚举（MSC，054C:0E0E）
  → Senser 启动 + 三轮 challenge-response 认证
  → 相机重新枚举为 054C:0336（服务身份）
  → 对该身份再次认证
  → 进入命令循环（pFunc=0x10 ProductInfo / 0x40 AdjustControl）
```

认证流程与 PMCA 的 `SonySenserAuthDevice` 一致：`0x37FF/0xD7AA` 启动、三轮 challenge、命令 5 完成、516 字节大端帧、`((~cmd)&0xFFFF)-salt` 解码。**FX30 6.00 接受 PMCA 内置的密钥表。**

### 2. 通道边界（本次测绘的核心结论）

| pFunc | 名称 | FX30 6.00 |
|---|---|---|
| `0x10` | ProductInfo | ✅ 可用（88 字节机型信息） |
| `0x40` | AdjustControl | ✅ 可用（见下方命令图谱） |
| `0xff01` | FileControl | ❌ **全部返回 128** |
| `0xff03` | MemoryDump | ❌ **全部返回 128**（含 `0xFFFF0000` BootROM） |

**含义**：无法按路径读文件、也无法按地址读内存。要接触固件内容，本仓库范围内没有可用通道。

### 3. 命令空间图谱（`pFunc=0x40`）

详见 [`docs/02-command-map.md`](docs/02-command-map.md)。

响应码语义（实测归纳）：

| res | 含义 |
|---|---|
| `0` | 成功 |
| `128` | 命令不存在 / 不支持 |
| `129` | 命令存在，但参数缺失或格式不符 |
| `130` / `192` | 命令存在，但被拒绝（状态或权限） |

命中摘要：

| cat | cmd | 返回大小 | 说明 |
|---|---|---|---|
| `0x603` | `0x01/0x02` | 129 | 需参数（备份读写） |
| `0x603` | `0x03` | 0 | 备份保存 |
| `0x603` | **`0x05`** | **2,253,564** | **完整备份数据（PDT_READ）** |
| `0x603` | `0x06` | 52 | 备份状态（含区域代号） |
| `0x603` | `0x0F` / `0x10` | 1 / 12 | — |
| `0x604` | `0x01/0x02/0x03` | 1 / 4 / 2 | 常量（疑似版本/状态） |
| `0x604` | `0x06`–`0x09`, `0x10` | 3/1/4/4/6 | — |
| `0x608` | `0x01` | 1 | — |
| `0x610` | `0x01/0x02` | 1 / 4 | 常量 |
| `0x611` | **`0x01`** | **2,097,220** | 事件日志（16 字节/条，含空槽） |

### 4. 备份数据可用（只读已验证）

`0x603 / cmd 0x05` 可直接读出 2,253,564 字节完整备份，PMCA 的 `print_backup` 可解析出 **25,737 个属性**。

**属性 ID 布局与 PMCA 定义同构**（锚点验证）：

| ID | PMCA 名称 | FX30 实测 |
|---|---|---|
| `0x003e0005` | modelName | `ILME-FX30` |
| `0x00e70000` | modelCode | 与 `info` 一致 |
| `0x00e70003` | serialNumber | 与 `info` 一致 |
| `0x003c0373` | recLimit | `0x0d`（电影机无时长限制） |
| `0x01660024` | androidPlatformVersion | **不存在**（纯 Linux） |
| `0x01070148` | palNtscSelector | **不存在** |
| `0x01640001` | usbAppInstaller | **不存在** |

写入命令已知（`0x603 / cmd 0x02` 或 `0x04`），**本仓库未使用**。

---

## 未能解决的问题（欢迎协作）

**目标**：为 FX30 启用电子快门连拍（参考 FX3 的四档连拍、A6700 的电子快门 11fps）。

**卡点**：25,737 个属性中无名称映射，**「驱动模式」对应的属性 ID 未知**。盲改其中任意一个都是赌博。

**需要的对比基准**（任一即可）：

1. **一台 FX3 的同格式备份**（最好只要 `0x003c` 功能限制段，约 827 个枚举属性，不涉及机身隐私）→ 与 FX30 备份 diff，差异项中应含机型功能差异
2. **A6700 上「驱动模式」的属性 ID**（若有研究者已知）

**背景证据**：FX3 与 A6700 均有连拍，FX30 与二者同 BIONZ XR 平台；A6700 用与 FX30 **相同的 26MP 传感器**实现了电子快门 11fps——硬件层面不存在阻碍。

---

## 与其他机型研究的差异

同代机型上已有公开工作，但结论不同，值得对照：

| | A6700 | A7C II | **FX30** |
|---|---|---|---|
| 文件读取 | ✅ 可读 `/usr/lib/appFw.so` | ✅ 有文件命令 | ❌ **128** |
| 内存通道 | — | — | ❌ **128** |
| 路径穿越 | 有记录 | 有记录（`/tmp/jiritsu/../..`） | 未验证（缺文件通道） |

推测差异来源：**固件分支**——FX30 属 Cinema Line，A6700/A7C2 属 Alpha。

---

## 仓库内容

```
docs/01-session.md       会话建立、驱动选择、会话语义陷阱
docs/02-command-map.md   命令空间完整图谱（本次测绘核心产出）
docs/03-backup.md        备份数据结构与 ID 布局验证
docs/04-dead-ends.md     此路不通的记录（避免重复踩坑）
tools/                   只读探测脚本（Python / PowerShell）
NOTICE                   来源与致谢
```

**不包含**：固件二进制、备份文件、机身序列号、任何写入型脚本。

---

## 安全边界

- 本仓库的工具**只发送读请求**，不写任何数据。
- 会话**不可复用**：每次操作应「相机 MSC → 一次运行内完成 → 干净退出 → 断电/拔插」，否则残留状态会让后续认证失败。
- `0x60F` 区间会使端点进入异常状态，应回避。
- 若要写备份（`cmd 0x02`），务必先留完整原始备份；**备份区写坏可能影响相机启动，该层风险未评估**。

---

## 致谢

- [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) — 认证帧、Senser 协议与 `print_backup` 的公开实现
- [YuuLuo/a7c2-service-preload](https://github.com/YuuLuo/a7c2-service-preload) — Jiritsu 通道与协议细节（A7C II 2.01）
- [Himpq/FireHydrant](https://github.com/Himpq/FireHydrant) — A6700 的内存访问方法与移植方法论
- [xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) — A6700 服务通道与 Pico 路线

非官方项目，与 Sony 无关。固件研究存在风险，后果自负。

---

<a name="english-summary"></a>
## English summary

Research on the USB service session (Senser / Jiritsu) of the Sony **ILME-FX30, firmware 6.00**.

**Findings:** the service session is reachable over pure USB (Type-C + libusbK on both `054C:0E0E` and `054C:0336`), and authentication succeeds with PMCA's built-in key tables. However, **only two pFunc values respond**: `0x10` (ProductInfo) and `0x40` (AdjustControl). Both `0xff01` (FileControl) and `0xff03` (MemoryDump) return `128` — no file channel, no memory channel.

A full command map of `pFunc=0x40` is documented, including a 2.25 MB backup blob readable via `0x603/0x05`, parsed into 25,737 properties whose ID layout matches PMCA's definitions (verified via model name / model code / serial number / recording-limit anchors).

**Open problem:** locating the drive-mode (continuous shooting) property ID requires a comparison baseline from a body that has burst shooting (FX3 preferred). No firmware binaries or device-unique data are included.
