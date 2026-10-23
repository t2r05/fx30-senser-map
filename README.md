# ILME-FX30 Service Mode Research

**索尼 FX30（Ver.6.00）服务模式的通道边界测绘**

> 本仓库记录在 ILME-FX30 固件 6.00 上对 USB 服务会话（Senser / Jiritsu）的实测探索：哪些通道可达、哪些被裁剪、数据长什么样。
> **不含固件二进制、不含备份数据、不含机身唯一信息。**

[English summary](#english-summary)

---

## 一句话结论

FX30 的服务模式**纯软件可达**（一根 Type-C + libusbK 双设备驱动），认证可过 PMCA 内置密钥表；会话层中 `0x10` / `0x40` 可用。

**写通道尚未验证。** 早期「文件通道与内存通道均不存在」的判断已撤回——`0xff01` FileControl 的测试方式有误（把路径当作 AdjustControl 载荷发送，且 `0x80` 是它的错误码），`0x40/0x1001` Jiritsu 则从未探测。详见下方更正。

---

## 核验状态（2026-10-23）

| 结论 | 状态 | 依据 |
|---|---|---|
| 服务会话可达、认证成功 | ✅ 已实测 | 多次复现 |
| `pFunc=0x40` 命令面（`0x603/604/608/610/611`） | ✅ 已实测 | `docs/02-command-map.md` |
| 完整备份 2.25 MB、25,737 属性可解析 | ✅ 已实测 | `docs/03-backup.md` |
| 固件可解密、`appFw.so` 可解包 | ✅ 已实测 | `docs/05-firmware-analysis.md` |
| `feature_id=419` = `DRIVE_MODE_CONT_SHOOTING` | ✅ 已定位 | `docs/08-appfw-capability-table.md` |
| `id=419` 在 FX30 / FX3 中取值相同 | ✅ 已比对 | 同上 |
| **`0xff01` FileControl 是否存在** | ⬜ **待实机复测** | 早期测试方式有误 |
| **`category=0x1001` Jiritsu 是否存在** | ⬜ **待实机探测** | 从未测试 |
| **机型 → 能力表行号映射** | ⬜ **待定位** | 08 §5 |
| 连拍补丁（16 处 `00→01`） | ⬜ **待实机验证** | 08 §6 |

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
| `0xff01` | FileControl | ⚠️ **待复测**（早期测试方式有误，见下） |
| `0xff03` | MemoryDump | ⚠️ 未通（`0xFFFF0000` 等地址均 128） |

> **⚠️ 2026-10-23 更正**：早期把「文件路径字符串」当作 `0x603`（AdjustControl）的 payload 发送，据此得出「FileControl 全 128」——**这个结论是错的**。FileControl 的正确载荷是 `cmd(int16) + filenameSize(int16) + 文件名（补 \\0 到 4 字节）`，成功时 `response == 1`；而 **`0x80`（=128）是它的错误码**，不等于「接口不存在」。因此 `0xff01` **尚未被有效测试**。详见 [`docs/07-jiritsu-breakthrough.md`](docs/07-jiritsu-breakthrough.md)。
>
> `0xff03` 用的是正确载荷（`{base, size}`），但同样需留意 128 可能是错误码而非「不支持」。

### 3. 命令空间图谱（`pFunc=0x40`）

详见 [`docs/02-command-map.md`](docs/02-command-map.md)。

响应码语义（实测归纳）：

| res | 含义 |
|---|---|
| `0` | 成功 |
| `128` | 命令不存在 / 不支持（**仅限 `pFunc=0x40`**；FileControl 的 128 是错误码） |
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

## 最新进展（2026-10-21）：固件已解开，BKID 已定位

> 早期版本的 README 判断「官方固件解不开」——**这个判断是错的，现已修正。**

**官方 `BODYDATA.DAT` 可以解密。** 社区研究者已提取全部 CXD90057（BIONZ XR）设备的密钥，见 `ma1co/fwtool.py` **PR #52**。FX30 Ver.6.01 实测解包成功（81 秒），提取出 `appFw.so`（75.4 MB）。

**从固件里定位到了连拍：**

| 项 | 结果 |
|---|---|
| `BKID_APP_setting_drive_mode_cont_shooting` | **BKID = 1208** |
| `..._cont_shooting_limited`（限制版） | **BKID = 1210** |
| 连拍四档枚举 | `DRIVE_MODE_CONT_SHOOTING_OPTION_{HI_PLUS,HI,MID,LOW}` **全在** |
| `customFps_Elec_*`（四档速度参数） | FX30 固件 **0 命中**（无速度调节项） |

共提取 **768 条 BKID 映射**（覆盖所有 `BKID_APP_setting_*`）。

**读写链路的反汇编结果：**

```
libbackup.so: Backup_read_setting_attr / Backup_write_setting_attr
  → IPC { 模块 0x3E014D, 操作码 0x1B(读) / 0x1D(写) }
  → osal_snd_msg（PLT 第5项，0x1530）
  → bkdmn 守护进程
  → ??? 这一段在 FX30 上未开放
```

完整方法见 [`docs/05-firmware-analysis.md`](docs/05-firmware-analysis.md)。

**关键结论需要更新**：驱动模式确实是**纯运行时状态**——不在备份里（4 轮 dump 实证）、状态命令读不出（22 行零差异）、`0x603/1` 任何参数格式都返回 129。这与「改动需冷重载从 NV 加载」的模型一致，而不是「没有通道」。

**「FX30 没有能改状态的通道」这一判断已撤回。** 它建立在「`0xff01` 全 128」之上，而该测试方式有误（见 §2 更正）。目前有两条**尚未验证**的软件通道：`0xff01` FileControl、`0x40/0x1001` Jiritsu；硬件路线（Pico）保留为兜底。

---

## 进展补充（2026-10-23）：写通道结论修正
对照同代机型的公开工作后，早期「FX30 没有写通道」的判断需要修正。

Jiritsu 文件服务并不走 `0xff01`，也不在 `category 0x600–0x62F`，而是：

```
pFunc = 0x40, category = 0x1001
command = 0x4007 (SET_FILE) / 0x4010 (SET_FILE2)
payload = [area, file_id, transfer_mode, data]
```

`category 0x1001` 在 FX30 上**从未被探测过**。因此正确表述是：**写通道尚未验证**，而非不存在。

配套只读探测脚本 `probe_jiritsu_1001.py`（只发空 payload，物理上无法写文件）。完整说明见 [`docs/07-jiritsu-breakthrough.md`](docs/07-jiritsu-breakthrough.md)。

同日离线分析：重新解包官方固件得到 `appFw.so`（79,032,104 字节），定位 BKID 注册表（4,355 条，vaddr `0x414A940..0x415B970`）与连拍项 `1208` 的记录位置，并整理了 9 处以 BKID 为键的平行表。**未找到单字节「支持开关」**，需与有连拍的机型差分定位。

---

## 进展补充（2026-10-23 · 二）：能力表三机型差分

引入 A6700 2.00（有连拍、解锁偏移已公开）与 FX3（同产品线、有连拍）做对照，解出 `appFw.so` 中的**机型能力表**：

- 结构 `{ u32 supported, u32 feature_id }`，8 字节/项，位于 `.rodata`；
- FX30 表 `0x37C2C8C`，15,466 项，行宽 **220**（行=变体，列=功能）；
- 功能名表（FX30 `0x4120288`）下标即 feature_id：**419 = `DRIVE_MODE_CONT_SHOOTING`（连拍）**。

**关键结果（负结果）**：`id=419` 的取值在 FX30 与 FX3 中**完全相同**（16 个 0、62 个 1，0 所在行也一致）。因此该能力表**不是直接开关**，真正机制应是**运行时选中哪一行变体**。

按「全部 16 个 0 → 1」可得到一份待验证补丁清单（16 处、列号 183、均在 `.rodata`），见 [`docs/08-appfw-capability-table.md`](docs/08-appfw-capability-table.md)。

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
| 文件读取 | ✅ 可读 `/usr/lib/appFw.so` | ✅ 有文件命令 | ⚠️ **待复测**（早期测试方式有误） |
| 内存通道 | — | — | ⚠️ 未通（128 语义待区分） |
| 路径穿越 | 有记录 | 有记录（`/tmp/jiritsu/../..`） | 未验证 |

> 早期「FX30 的 Cinema Line 分支裁掉了文件通道」的推测**尚未证实**——它源于一次格式错误的 FileControl 调用（见 §2 更正）。

差异来源（**待验证**）：固件分支——FX30 属 Cinema Line，A6700/A7C2 属 Alpha。

---

## 仓库内容

```
docs/01-session.md       会话建立、驱动选择、会话语义陷阱
docs/02-command-map.md   命令空间完整图谱（本次测绘核心产出）
docs/03-backup.md        备份数据结构与 ID 布局验证
docs/04-dead-ends.md     此路不通的记录（避免重复踩坑）
docs/05-firmware-analysis.md  固件解密与 BKID 定位方法
docs/06-related-projects.md   相关开源项目目录（其他作者，7 项）
docs/07-jiritsu-breakthrough.md  Jiritsu 写通道（结论修正）与固件结构分析
docs/08-appfw-capability-table.md  三机型能力表结构与差分结果
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

完整相关开源项目目录（含 A7C2-FL23、ILCE-7M4-RE、Recipe Lab 等共 7 项）见 [`docs/06-related-projects.md`](docs/06-related-projects.md)。

非官方项目，与 Sony 无关。固件研究存在风险，后果自负。

---

<a name="english-summary"></a>
## English summary

Research on the USB service session (Senser / Jiritsu) of the Sony **ILME-FX30, firmware 6.00**.

**Findings:** the service session is reachable over pure USB (Type-C + libusbK on both `054C:0E0E` and `054C:0336`), and authentication succeeds with PMCA's built-in key tables. Only two pFunc values respond: `0x10` (ProductInfo) and `0x40` (AdjustControl).

**Correction (2026-10-23):** `0xff01` (FileControl) was **not validly tested** — an earlier probe sent a path string as an `0x603` AdjustControl payload, and `0x80` (=128) is FileControl's own error code, not "unsupported". `0xff03` (MemoryDump) did not respond with the correct `{base,size}` payload. See `docs/07-jiritsu-breakthrough.md`.

A full command map of `pFunc=0x40` is documented, including a 2.25 MB backup blob readable via `0x603/0x05`, parsed into 25,737 properties whose ID layout matches PMCA's definitions (verified via model name / model code / serial number / recording-limit anchors).

**Current state:** the `appFw.so` capability table (`{u32 supported, u32 feature_id}`, 220-wide rows) has been decoded through a three-model diff; `feature_id = 419` is `DRIVE_MODE_CONT_SHOOTING`. Its flags are **identical on FX30 and FX3**, so the remaining questions are the **model→row mapping** and a usable **write channel** — both pending hardware verification. See `docs/08-appfw-capability-table.md`. No firmware binaries or device-unique data are included.
