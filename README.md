# ILME-FX30 Service Mode Research

**索尼 FX30（Ver.6.00）服务模式的通道边界测绘**

> 本仓库记录在 ILME-FX30 固件 6.00 上对 USB 服务会话（Senser / Jiritsu）的实测探索：哪些通道可达、哪些被裁剪、数据长什么样。
> **不含固件二进制、不含备份数据、不含机身唯一信息。**

[English summary](#english-summary)

---

## ⚠️ 重要声明（请先读）

- 本项目**仅供学术研究与技术学习**，**不用于任何商业行为**，禁止用于盈利、侵权或非法用途。
- 本项目与 Sony Corporation **无任何关联**，不代表 Sony 立场。
- **固件逆向与设备修改存在变砖风险，可能使设备失去保修。只在自有设备上操作，出错先停止，不要盲目重试写入。**
- 本仓库**不含**固件二进制、备份数据、机身唯一信息、加密密钥，也不含把载荷下发到相机的脚本。
- 本文所有地址、命令号、结构偏移均为**逆向分析结果，非 Sony 官方文档**，可能存在误判，请以实机验证为准。
- 如 Sony 或其授权方提出异议，相关内容将立即下架。

> 📄 完整版：**[`docs/17-disclaimer-and-boundaries.md`](docs/17-disclaimer-and-boundaries.md)**
> （含脚本风险分级、危险命令清单、责任限制、已知踩坑）

---

## 一句话结论

FX30 的服务模式**纯软件可达**（一根 Type-C + libusbK 双设备驱动），认证可过 PMCA 内置密钥表；`0x10` / `0x40` 两个 pFunc 可用，`0x1001` Jiritsu 可读**真实根文件系统**，设置区**可读且可全量写**。

**✅ 已可开启隐藏连拍模式**（2026-10-24 实机验证，**已独立复现 3 次**）：
成对写入设置区两个字节，再**拔电池 ≥30 秒冷启动**，相机进入连拍且能正常连拍
（菜单不显示该选项，手动切换即掉回）。

```bash
python tools/probe_drive_write.py --burst     # 开启连拍
python tools/probe_drive_write.py --single    # 回滚单张
python tools/probe_drive_write.py --probe     # 只看状态，不写
```

> 📄 **上手请看 [`docs/18-开启隐藏连拍-最简步骤.md`](docs/18-开启隐藏连拍-最简步骤.md)**
> （4 步流程 + 预设一览 + FAQ）。等价的原始写法是
> `python tools/probe_drive_write.py 0x8EF80=0x01 0x91690=0x01`。

**同时推翻了此前「三条路都封死」的判断**：驱动模式**不在** `0x603/1` 属性表里
（那 1,024 条与模式零差异是对的，但不是「读不到真值」，而是「那里根本没有这个字段」），
而在 PDT 设置区的**两张枚举表位置索引**上。详见「进展补充（2026-10-24 · 四）」。

**目前最硬的离线成果**：连拍 `id = 0x04B8` 已定位，`id → 运行时 .bss 地址` 的映射表已解出（2,692 条），
且已证明 FX30 固件里连拍**一样都不缺**。
⇒ **连拍不是功能缺失，是被「模式设置」门控** —— 而那个开关，现在已经能扳动。

---

## 核验状态（2026-10-24）

| 结论 | 状态 | 依据 |
|---|---|---|
| 服务会话可达、认证成功 | ✅ 已实测 | 多次复现 |
| `pFunc=0x40` 命令面（`0x603/604/608/610/611`） | ✅ 已实测 | `docs/02-command-map.md` |
| 完整备份 2.25 MB、25,737 属性可解析 | ✅ 已实测 | `docs/03-backup.md` |
| 固件可解密、`appFw.so` 可解包 | ✅ 已实测 | `docs/05-firmware-analysis.md` |
| `feature_id=419` = `DRIVE_MODE_CONT_SHOOTING` | ✅ 已定位 | `docs/08-appfw-capability-table.md` |
| `id=419` 在 FX30 / FX3 中取值相同 | ✅ 已比对 | 同上 |
| **`0xff01` FileControl 是否存在** | ❌ **实测未通**（很可能未实现） | 21 组路径 + 空文件名均 128；[09 §2](docs/09-realtime-results.md) |
| **`category=0x1001` Jiritsu 是否存在** | ✅ **存在（实机确认）** | `res=0` 命令集；[09 §4](docs/09-realtime-results.md) |
| Jiritsu 命令号 → 语义（GET/SET_FILE…） | ✅ 已定位（18 条） | 07 |
| **`0x4007` SET_FILE 写入 + `dlopen`** | ✅ **实机（代码已执行）** | [07 §3.1](docs/07-jiritsu-breakthrough.md) |
| **`file_id` 槽位表（0=配置 / 2=载荷 / 3=日志）** | ✅ **反汇编解出** | [07 §3.2](docs/07-jiritsu-breakthrough.md) |
| `0x4010` SET_FILE2 语义 | ⬜ 未实测（判定为按路径写） | 07 §3 |
| **真实根文件系统任意读** | ✅ **实机（SHA-256 验证）** | [10 §1](docs/10-setting-channel.md) |
| **设置区任意读（含实时值）** | ✅ 实机 | [10 §4](docs/10-setting-channel.md) |
| **设置区任意写（2.25 MB 全量）** | ✅ 实机 | [10 §6](docs/10-setting-channel.md) |
| **按住 ID 读写单条属性（裸 4 字节 id）** | ✅ **实机**（此前漏测） | [10 §7](docs/10-setting-channel.md) |
| **PDT 的真实身份 = CP/MP 芯片参数备份** | ✅ **已查明** | [13 §3](docs/13-flash-layout.md) |
| Flash 分区表与挂载点 | ✅ **官方 conf 直读** | [13](docs/13-flash-layout.md) |
| **BKID 名称 → 数字 id 映射** | ✅ **已解出**（25,167 条） | [11](docs/11-drive-mode-ids.md) |
| 连拍 id = `0x04B8`（= 1208） | ✅ 已定位 | [11 §1](docs/11-drive-mode-ids.md) |
| **id → 运行时 `.bss` 地址** | ✅ **已解出**（2,692 条） | [12](docs/12-property-accessor-table.md) |
| 三机型驱动模式 id 对照 | ✅ 已比对（FX30 ≡ FX3 逐位相同） | [11 §2](docs/11-drive-mode-ids.md) |
| **`0x8EF80` 是否模式真值源** | ✅ **是**（2026-10-24 实机，成对写入后冷启动生效） | [进展补充 · 六](README.md#进展补充2026-10-24--六连拍写入成功--隐藏连拍模式开启) |
| **`0x8EF80` / `0x91690` 的存储语义** | ✅ **枚举表 0-based 位置索引**（12 份带标签快照 100% 自洽） | 同上 |
| **连拍对应的模式值** | ✅ **已确定**：`0x8EF80=0x01` + `0x91690=0x01`（成对） | 同上 |
| **开启隐藏连拍模式** | ✅ **实机验证**（冷启动后进连拍、能正常连拍，菜单不显示该选项） | 同上 |
| **`0x603/1` 属性表是否反映模式** | ❌ 实测零差异（1,024 条全扫）—— 但结论方向已修正：**该表不是驱动模式的载体** | [04 §14](docs/04-dead-ends.md) |
| 三处 `.bss` 副本的同步写顺序 | ⬜ 待验证（**已可绕过**：直接写 PDT） | 12 §4 |
| 连拍补丁（16 处 `00→01`） | ❌ 已撤回（假阳性） | 08 顶部警告 |
| **dlopen 载荷的最小合法 ELF 结构** | ✅ **五条铁律 + 2,064 B 参考产物** | [15](docs/15-payload-elf-rules.md) |
| **`file_id` 槽位表（第三方独立印证）** | ✅ 已互证（0/3 号槽确认） | [15](docs/15-payload-elf-rules.md)、06 §3.3 |
| `PT_GNU_RELRO` 是否应存在 | ✅ **应去掉**（会 mprotect 掉 `.dynamic` 同页） | [15 §一](docs/15-payload-elf-rules.md) |
| `0xff01` 三机型行为不一致 | ⬜ **未解**（FX30 = 128，ZV-E10 可用） | [04 §20](docs/04-dead-ends.md) |
| **id 位移规律** | ✅ **分段**：`0x02B1`族 +5 / `0x04B8`族 +1（早期「整体 +5」已修正） | [11 §二](docs/11-drive-mode-ids.md) |
| **FX30 缺 `dial_hi_plus_in_electric_shutter`** | ✅ **四机型确认**（A6700=0x12D5 / A7C2=0x12D1） | [11 §3.1](docs/11-drive-mode-ids.md) |
| **驱动模式建模代数** | ✅ **三代**（A7C2 独有 `EXPANDED_OPTIONS` 26 条 + `NON_LIMITED`） | [11 §三](docs/11-drive-mode-ids.md) |
| 官方固件包解包（含加密层） | ✅ **全链路**（UFU → `CXD90057_k8` → fwtool） | [16](docs/16-firmware-unpack.md) |
| A6700 / A7C2 属性访问器表 stride | ✅ **已定位**（A6700 `0x50`/10 槽，A7C2 `0x68`/13 槽，**无 id 字段**，以下标寻址） | [12](docs/12-property-accessor-table.md) |

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
| `0x10` | ProductInfo | ✅ 可用 —— item `0x001f` = **HASP 服务令牌（88 B）**（`readHasp()`） |
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

## 进展补充（2026-10-24）：真实文件系统读写 + 设置区读写

在 `category=0x1001` 的 18 条命令全部定位之后，打通了两条此前缺失的通道：

**1) 真实根文件系统任意读**（实机 + SHA-256 验证）

```
SET_FILE_PATH(0x400F)  [0x00] + "/../../etc/hostname\0"
GET_FILE2   (0x4011)  [0x00, 0xFF, 0x00]
```

读出 `/usr/lib/libJiritsu.so` 233,416 字节，SHA-256 与固件解包版**逐字节相同**。
关键：必须走 `arg0=0` 分支（base 为真实挂载点）；`arg0=1` 的 `/mnt` 是 media 沙箱，`..` 无法越界。
另：`GET_FILE2` 是**一次性**的，调用后路径即被 `free` 并置空，每次读都要重新 `SET_FILE_PATH`。

**2) 设置区任意读写**

`0x603` 的正确载荷格式此前被漏测（试过 5/8/12 字节，**唯独没试裸的 4 字节 id**）：
`0x603/1` = `u32le id` 单条读、`0x603/2` = `id + data` 单条写、
`0x603/4` = `u32le protect + 全量` 写、`0x603/3` = `u16le` 保存。

更重要的是 `0x603/5` 的 **fromMemory 标志**：空 payload 等价于 `fromMemory=0`（闪存预设），
`b"\x01"` 才是**内存实时值**。此前所有快照都用空 payload，因此一直看不到实时状态。

用 `mem1` 重做模式差分后，定位到驱动模式相关字节 `0x8EF80`：

| 模式 | `0x8EF80` |
|---|---|
| 单张拍摄 | `00` |
| 单拍阶段曝光 | `02` |
| 自拍定时 | `08` |

**写入通路已验证**：2,253,568 字节全量原样写回 → `res=0`，再读仅计数器变化。

**负结果**：把 `0x8EF80` 改成 `0x01` 后，固件在启动时把它**归一到 `0x00`**——
该字节受校验，不是可以随意强制的裸状态。连拍对应的值因此仍未确定。

详见 [`docs/10-setting-channel.md`](docs/10-setting-channel.md)。

---

## 进展补充（2026-10-24 · 二）：PDT 身份查明 + 三条路封死

上一节说「`0x8EF80` 受校验」，方向错了。真实原因更彻底：**我们改的从来不是用户设置文件。**

### 1. PDT = CP/MP 芯片参数备份

| 证据 | 内容 |
|---|---|
| 固件包出厂备份 | `0110_backup/SYSIPSX-DSLR/LAX/CX96701_CN2.bin` = **2,253,564 字节**，与 `0x603/5` 读回的 PDT **分毫不差** |
| 文件头 | magic `BK4\0`（offset `0x0C`），`0x40` 处 ASCII `31182_15.2025122501` |
| 生产者 | `bin/bk.elf`（18,952 B）：`bk g[ChipID] BackupID`、`ChipID: c:CP / m:MP`、错误串 `inter chip read error:%d` |
| 路径 | `bk.elf` 引用 `/setting/Backup.bin` 与 `/setting/Backup.bak` |
| 挂载 | `mount.conf`：`nflasha2 → /setting`（20 MB vfat） |

⇒ ~~**固件启动时不从这个文件恢复任何用户设置**，所以改它必然无效。~~ ❌ **已被推翻，见下节「进展补充（2026-10-24 · 三）」。**

### 2. ~~控制实验：`0x8EF80` 是「记录」不是「真值源」~~ ❌ **已被推翻**

~~写 `0x08`（自拍定时）→ 全量写回 `res=0`、save `res=0`、读回 `0x08` 已生效 → **断电重启后相机仍是单张**，而字节仍为 `0x08`。~~
~~⇒ 可写、可持久化，但**不是运行时真值源**。~~

**错在**：只写了 `0x8EF80`，配套的 `0x91690` 没写 ⇒ 状态不完整 ⇒ 固件回退。

> ⚠️ 初版这里还列了第 ② 点「用热重启验证、暖启动把状态刷掉了」—— **该点不成立，已撤回**。
> 用户实测：**关机再开机后连拍依然保持**，热重启**不会**清除设置区改动。
> 写入一旦落盘就是真正持久化的。那次失败的真因**只有**「单写」这一条。
> ⇒ **多因素并存时，必须单因子对照才能定因果**（教训 #43）。

### 3. `0x603/1` 的 1,024 条属性表与模式零差异

裸 4 字节 id 扫 `0x50000`–`0x503FF`：`res=0` **825 条**、129 的 199 条、非零 116 条。
`--tag=single` vs `--tag=timer` 全扫差分：**值不同 0 条**。

### 4. ~~结论：进服务模式后 appFw 已不在「正常拍摄状态」~~ ❌ **已被推翻**

~~两条 USB 可达通道读的都是**静态/持久化副本**。这同时解释了三个此前互看似矛盾的现象：
PDT 里有字节随模式变却改了不生效、属性表零差异、`0x8EF80` 保住了但相机不理它。~~

**这条「三条路都封死」的结论是错的** —— 真相是：**属性表（`0x603/1`）根本不是驱动模式的载体，
而 PDT 是真值源，只是当时写漏了配套字段。** 见下节。

详见 [`docs/04-dead-ends.md`](docs/04-dead-ends.md) §13–§18、[`docs/13-flash-layout.md`](docs/13-flash-layout.md)。

---

## 进展补充（2026-10-24 · 三）：名称 → id → `.bss` 地址 全链路打通

既然「找开关」三次扫描都是零（FX30 独有常量 0 条、独有符号 0 个、列表无缺项），
方向改为「**找运行时那个值的存放地址**」，不再找能力位。

### 1. BKID 名称 → 数字 id

`BKID_*` 字符串在 `.text` 里 `adrp+add` 引用 **0 处**——它们通过指针表索引。
在 `.data.rel.ro` 找到 **16 字节/项** 的表（约 25,167 条）：

```c
struct bkid_entry { const char *name; uint32_t id; uint32_t meta; };
```

**连拍 `BKID_APP_setting_drive_mode_cont_shooting` → `0x04B8`（= 1208）**，
与本仓库 10-21 记录的「BKID = 1208」一致；受限版 `0x04BA`（= 1210）同样吻合。
两条独立路径算出同一个数。

三机型 id 逐项对照（FX30 与 FX3 **逐位相同**；A6700/A7C2 为**分段位移**并多出 `HI_PLUS`，详见 `docs/11` §二）：

| 用途 | FX30 | FX3 | A6700 |
|---|---|---|---|
| `menu_drive_mode` | `0x02AF` | `0x02AF` | `0x02B4` |
| `dial_hi_plus_in_electric_shutter` | **无** | **无** | **`0x12D5`** |
| `dial_hi_in_electric_shutter` | `0x02B1` | `0x02B1` | `0x02B6` |
| `cont_shooting` | **`0x04B8`** | **`0x04B8`** | `0x04B9` |
| `cont_shooting_limited` | `0x04BA` | `0x04BA` | `0x04BB` |
| `registration_drive_mode_available0..3` | `0x0C2C`/`2D`/`2E`/`33` | 同左 | `0x0BE4`/`E5`/`E6`/`EB` |

### 2. 两代「隐藏」的建模方式不同（这是「找不到开关」的根本原因）

| | FX30 / FX3 | A6700 / A7C2 一代 |
|---|---|---|
| 机制 | **枚举 + 受限降级** | **限制原因枚举** |
| 常量 | `DRIVE_MODE_CONT_SHOOTING_`**`LIMITED`**`_HI/MID/LOW`（后缀 = 模式值） | `DRIVE_MODE_`**`LIMIT_`**`CONTINUOUS_SHOOTING_HI/HI_PLUS/MID/LO`（前缀 = 限制原因） |
| 表现 | 菜单始终可选，系统运行时自动降级 | 弹 `CAUTION_ID_FACTOR_CAM_SET_DRIVE_MODE_*_MSG` 说明为何不可用 |

`cmp #imm` 分布也印证：FX30/FX3 对单张（`0x1A2`）与自拍定时（`0x1A4`）**零特判**，唯独连拍（`0x1A3`）6 处；A6700 四模式对称。

### 3. 属性访问器表：id → `.bss` 地址

`.data.rel.ro` 里另有 **0x58 字节/条** 的记录表：

```c
struct prop_record { uint64_t id; void *attach; void *stub[8]; uint64_t meta; };
```

每个桩只有 3–5 条指令（`adrp + ldr/str`），**桩体直接编码了目标 `.bss` 地址**，不需执行。

解出 **2,692 条**连续 id（`0x0000`–`0x151E`）。BKID 的 id 与这张表**同一套编号**。

**连拍族地址（全部在 `.bss` = RAM-only）**：

| 用途 | id | 主槽 | 处理副本 | 镜像 |
|---|---|---|---|---|
| `menu_drive_mode`（**字节** `ldrb/strb`） | `0x02AF` | `0x8230D84` `0x8230D86` | `0x8220844` `0x8220845` | `0x8836A2C` |
| `dial_hi_in_electric_shutter` | `0x02B1` | `0x8230D98` `0x9C` `0xA0` | `0x8220858` `0x5C` | `0x8836A44` |
| **`cont_shooting`** | **`0x04B8`** | **`0x831F844` `0x48` `0x4C`** | **`0x8220304` `0x08`** | **`0x89254F0`** |
| `cont_shooting_limited` | `0x04BA` | `0x831F868` `0x6C` `0x70` | `0x8220328` `0x2C` | `0x8925514` |

每条属性实为**三存储簇**（原始对 / 处理三连 / 镜像）⇒ **写入必须三处同步**，否则被镜像回滚。
这也解释了早前反复出现的「写进去又被归一化」。

⚠️ 该解析器**只适用 FX30**：A6700 的 `.data.rel.ro` 不是 0x58 结构（只索引到 2 条）。

### 4. 顺带纠正社区的 Flash 布局表

官方 `partinf.conf` 注释直接写明用途，社区流传版本有 3 处标签错、1 处漏项：

| 节点 | 流传说法 | 官方注释 |
|---|---|---|
| `nflasha3` | 数据 | **SYSTEM (Main)** 75 MB |
| `nflasha8` | 频闪 | **CP Data** 64 MB |
| `nflasha23` | 空 FAT32 | **PMBP**（`prfile`）64 MB |
| `nflasha6` | （漏项） | **Jiritsu 25 MB** ← 解释了 `SET_FILE_PATH` 的 `/tmp/jiritsu` base |

详见 [`docs/11-drive-mode-ids.md`](docs/11-drive-mode-ids.md)、[`docs/12-property-accessor-table.md`](docs/12-property-accessor-table.md)、[`docs/13-flash-layout.md`](docs/13-flash-layout.md)。

---

## 进展补充（2026-10-24 · 六）：✅ 连拍写入成功 —— 隐藏连拍模式开启

> **本节是当前仓库最有价值的实机结论，且推翻了前面三节的多条结论。**

### 1. 一行命令

```bash
python tools/probe_drive_write.py --burst
# → 拔电池 ≥30 秒冷启动 → 相机进入连拍，能正常连拍
```

（等价原始写法：`probe_drive_write.py 0x8EF80=0x01 0x91690=0x01`）

**这是隐藏模式**：驱动模式菜单里**不显示**该选项。
只有**手动修改驱动模式设置**才会掉回单张 —— 固件会把 `0x8EF80` 和 `0x91690`
都写回 `0x00`（已由 `--probe` 快照确认）。掉了重新跑一次 `--burst` 即可。
但按住快门确实连拍。

**持久性（用户实测）—— 两个不同阶段：**

| 阶段 | 操作 | 结果 |
|---|---|---|
| **首次生效** | 关机再开机（热重启） | ❌ **不生效** |
| **首次生效** | **拔电池 ≥30 秒冷启动** | ✅ **生效** |
| 已生效后 | 关机再开机（热重启） | ✅ **保持** |
| 已生效后 | **拔电池冷启动** | ✅ **保持** |
| 已生效后 | 进菜单浏览 / 切视频模式录视频 | ✅ **保持** |
| 已生效后 | **手动修改驱动模式设置** | ❌ 掉回单张 |

⇒ **写入后需要一次冷启动让固件加载；加载之后热重启不会清除。**
只要不去手动改驱动模式，方案无损且近乎永久。

唯一痛点：**没法更换拍照模式**（菜单里选不到连拍，一选别的就掉回，回不去）。

**已独立复现 3 次**（10-24 晚三次完整流程均成功）—— 方法可靠。

👉 **完整上手流程见 [`docs/18-开启隐藏连拍-最简步骤.md`](docs/18-开启隐藏连拍-最简步骤.md)**

### 2. `0x8EF80` / `0x91690` 存的是**枚举表位置索引**，不是属性 id

这是此前最大的误判。固件里 `.data.rel.ro` 有两张 16 字节/项的枚举值表
（`{char* name; u32 id; u16 code}`）：

| 偏移 | 枚举表 | 表基 vaddr | `0x00` | `0x01` | `0x02` | `0x05` | `0x08` | `0x09` | `0x0C` |
|---|---|---|---|---|---|---|---|---|---|
| `0x8EF80` | `EXTERN_VAL_DRIVE_MODE_*` | `0x41A0550` | SINGLE | **BURST** | BRACKET | RAW_BURST | SINGLE_SELF_2S | BURST_SELF_10S | SINGLE_SELF_5S |
| `0x91690` | `DRIVE_MODE_*` | `0x41A28F0` | 1_IMAGE_SHOOTING | **CONT_SHOOTING** | CONT_SHOOTING_LIMITED | SELF_TIMER | CONT_BRACKET | BRACKET_SINGLE | DRO_ADV_BRACKET |

12 份带标签快照 100% 自洽；27 份全量快照在这两个偏移上的取值集合
（`0x8EF80` ∈ {0,1,2,8,12}，`0x91690` ∈ {0,5,9}）**全部落在表索引范围内**。

⇒ 此前「连拍候选是 `0x01`/`0x04`/`0x10`」是按 `id` 猜的；按**索引**只需 `0x01`。

### 3. 两个字段必须**成对写**

它们是同一设置的两层表示。只写一个 ⇒ 固件发现不一致 ⇒ **回退**。

这正是 10-24 那次「写了没生效」的真正原因 —— 当时只写了 `0x8EF80=0x08`，
`0x91690` 仍是 `0x00`，两个字段不一致。

**证据**：唯一的变量就是第二个字段有没有跟上 ——

| 实验 | 写入 | 结果 |
|---|---|---|
| 单写 | `0x8EF80=0x08`，`0x91690` 留 `0x00`（不一致） | ❌ 相机仍单张 |
| 成对 | `0x8EF80=0x01` + `0x91690=0x01` | ✅ 冷启动后进连拍，能正常连拍 |
| 二次复现 | 从 `0x00/0x00` 重新成对写 `0x01/0x01` | ✅ 两字段读回均生效 |

> ⚠️ **不要引用「固件联动改写 `0x8DC14`」这条说法** —— 该证据已撤回。
> `0x8DC14` 与 `0x7A640` 在同一模式下取值可变（单张时实测 9 个不同值），
> 是运行时噪声，不是模式的函数。

### 4. 两个必须记住的坑

| 坑 | 说明 |
|---|---|
| **首次生效必须冷启动** | 写入后**关机再开机不生效**，必须**拔电池 ≥30 秒**冷启动一次。但**生效之后**热重启能保持（用户实测）—— 这是两个不同阶段，别混为一谈 |
| **会话结束相机会重枚举** | 跑完脚本后相机回到 PTP（PID `096F`），下次要重新切「海量存储器」并插拔 |

### 5. 顺带排除：`0x603` 的两套命令面

历史文档把 `0x603` 当成唯一命令面，实测是**两套**：

| 命令面 | 语义 | 实测 |
|---|---|---|
| `cat=0x1001, cmd=0x603` | 设置区备份 / 写回 | **对任何 id 都返回固定 `01 02 00 10`**（连边界 id 也一样）⇒ 是 ack，**不是属性值** |
| `cat=0x0603, cmd=0x0001` | 属性单条读 | BKID 族全部 `res=129`；`0x5000C` 返回 `f1 5d 00 00`（有数据） |

⇒ 历史文档里「payload 首字节是 namespace」那条推理线**建立在固定 ack 上，是伪命题**。
⇒ **BKID 注册表 id 在这条通道上不通**，读取路线走不通。

详见 [`tools/README.md`](tools/README.md) 的「驱动模式写入」一节、
[`docs/04-dead-ends.md`](docs/04-dead-ends.md) §十三更正块、
[`docs/13-flash-layout.md`](docs/13-flash-layout.md) §三更正块。

---

## 进展补充（2026-10-24 · 四）：与上游研究者的通道互证

[`xyzhangxin/sony-a6700-powerful`](https://github.com/xyzhangxin/sony-a6700-powerful) 的作者在 Issue #2 中
公开了 A6700 的完整三步骤。与 FX30 Ver.6.00 逐条对照后：**骨干逐字节吻合**。

| 对方说法 | FX30 实测 | 判定 |
|---|---|---|
| 不走 `0xff03`/`0xff01`，走 Jiritsu | 两者全 128 | ✅ 边界相同 |
| `pFunc=0x40` / `category=0x1001` | 相同 | ✅ |
| 载荷 `{area, file_id, transfer_mode}` | `[0, 2, 0] + data` | ✅ **逐字节一致** |
| `0x4007 / file_id=2` 加载 `libJit.so` | `res=0`，读回自写副作用 | ✅ **已实证执行** |
| 「固定范围」不是 `0x603/5` 的 BK4 区 | 本仓库独立查明该块是 CP/MP 备份副本 | ✅ 同向 |

### 对方留的空白，本仓库已补上

对方明确提醒：「加载路径仅在 A6700 2.00 验证，FX30 6.00 仍需单独确认，**不能直接套用 A6700 载荷**」。

- 前半句 → **已确认：FX30 6.00 与 A6700 在同一条链路上同构、可用**；
- 后半句 → **是对的**：本仓库没有套用其载荷，而是借壳本机 `libssp.so`，
  后改为用 zig 独立构造合法 `.so`（2,192 B，`PT_LOAD` 3 段无 W+X，`DT_INIT_ARRAY → R_AARCH64_RELATIVE`）。

### 两处编号语义仍待实测

| | 对方 | 本仓库（反汇编） |
|---|---|---|
| `0x4010` | `file_id=0` = 发送「读取器配置」 | 配合 `0x400F` 的按路径写 |
| `0x4008 file_id=0` | 取回「执行结果」 | 是 `tmmc.jit`；用 `file_id=3`（`jit.log`）闭环 |

两者**可能不冲突**：若「读取器配置」写在 0 号槽，落点正是 `tmmc.jit` —— 同一件东西两种叫法。
详见 [`docs/14-peer-crosscheck.md`](docs/14-peer-crosscheck.md)。

### 「260 扇区」说明双方在不同层

对方预检范围是 260 扇区（`260 × 512 = 133,120` 字节）⇒ **块设备扇区层**。

| 层次 | Powerful6700 | 本仓库 |
|---|---|---|
| 块设备扇区 | ✅ 260 扇区固定范围 | ❌ |
| 文件系统（路径） | 未知 | ✅ SHA-256 级验证 |
| 属性语义（BKID） | ❌ 无 ID | ✅ 25,167 条 BKID + 2,692 条访问器 |

旁证：`0x603/6` 报 PDT size 2,253,052，`0x603/5` 实读 2,253,564，**差 512** —— 正好一个扇区。

⇒ 这是**层次差异，不是对错**。对方说「没有已验证的驱动模式 ID」，是其路线的边界，
不改变本仓库已解出 `0x04B8`（= 1208）与 104 字节目标区域的事实。

---

## 进展补充（2026-10-24 · 五）：载荷 ELF 结构规则，靠第三方机型补齐

盘点了全生态 16 个核心相关项目后，找到一份比 A6700 那条线更有价值的技术参照：
[`nolan2628/Sony-ZVE-10-Camtool`](https://github.com/nolan2628/Sony-ZVE-10-Camtool)（ZV-E10，11★）。

它证明 **Jiritsu dlopen 不是 A6700/A7C2 独有** —— 入门机型同样能跑通，而且拿到了完整 shell
（440 B 载荷 `fork` → `execve("/bin/sh", run.sh)`）与 root 全权限（`Uid: 0 0 0 0`、`CapEff: ffffffffffffffff`）。

### 对本案产物的直接影响

对方公布的载荷 ELF 铁律里有一条命中本仓库产物：**不要带 `PT_GNU_RELRO`**。

默认链接会给 RW 段加 `PT_GNU_RELRO`，而 `_dl_protect_relro` 是按页 `mprotect` 的 ——
`.dynamic` 与 `.bss` 同一页，整页变只读。纯函数载荷（全栈变量）不踩；**一旦用任何全局缓冲区就必崩**。

| 指标 | 修正前 | 修正后 |
|---|---|---|
| 大小 | 2,192 B | **2,064 B** |
| `PT_GNU_RELRO` | 有（`memsz=0xcd8`，含 0xbe0 bss） | **无** |
| RW 段 | `filesz=0xf8 / memsz=0xcd8` | `filesz=0xf8 / memsz=0xf8` |
| 段清单 | PHDR/LOAD×3/DYNAMIC/**RELRO**/GNU_PROP/STACK | PHDR/LOAD×3/DYNAMIC/GNU_PROP/STACK |

修正命令只加一个参数：`-Wl,-z,norelro`。修正后的段结构与对方验证可用的载荷**同构**。

### 同时修正的两处认知

1. **`file_id` 槽位表得到第三方独立印证** —— 对方的清理脚本把 `tmmc.jit` / `jit.log` / `DIAC.csv` /
   `history.txt` / `ver.txt` 硬编码进「永不删除」名单。这正好对上本仓库从 `libJiritsu.so 0x1236C`
   跳转表解出的索引（0 = `tmmc.jit`、3 = `jit.log`），并补全了我们不知道的槽位。
2. **返回码 130 不是「文件不存在」，是「nflasha6 已卸载」** —— 删掉 `libJit.so` 会让 Jiritsu
   卸载整个分区，要发 `0x4002`(MOUNT) 重挂。本项目早期判断错了方向。

### 另外记下两条安全红线

- `0x4003`(FORMAT) / `0x4006`(FIRMUP) 会卡死服务，**不要发**；
- `0xff01` 在 ZV-E10 上可用于往任意路径 `put`，在 FX30 上全部返回 128 —— **最明确的机型差异，尚未解释**。
  本项目涉及写文件一律走 Jiritsu，不依赖 `0xff01`。

详见 [`docs/15-payload-elf-rules.md`](docs/15-payload-elf-rules.md) 与
[`docs/04-dead-ends.md`](docs/04-dead-ends.md) §十九～§二十一。

---

## 未能解决的问题（欢迎协作）

**目标**：为 FX30 启用电子快门连拍（参考 FX3 的四档连拍、A6700 的电子快门 11fps）。

> **2026-10-24 更新：主目标已达成。** 写入 `0x8EF80=0x01` + `0x91690=0x01`
> 并冷启动后，相机进入连拍且能正常连拍（**隐藏模式**，菜单不显示该选项）。
> 见「进展补充（2026-10-24 · 六）」。以下是**尚未解决**的部分。

**已确定的事实**：

1. FX30 固件里**连拍相关的每一个名字都在**——`BKID_APP_setting_drive_mode_cont_shooting`（`0x04B8`）、
   `dial_hi/mid/lo_in_electric_shutter`（`0x02B1`/`0x02B3`/`0x02B5`）、
   四档 `DRIVE_MODE_CONT_SHOOTING_OPTION_*`、`.rodata` 里 `0x1A2 → 0x1A3` 的菜单序列（3 处）全都有。
2. FX30 与 FX3 设置项注册表 **843 条零差异**；`.dynsym` FX3 **独有 0 个**；FX30 的 `.text` 反而**大** 11,128 字节。
3. 指令级对称差分：A 独有 19.41% / B 独有 19.38%，净差 10,848 ≈ `.text` 尺寸差 ⇒ **函数级重排**，不是逐函数改写。
4. 连拍值在 **`.bss`（RAM-only）**，地址已解出（`0x831F844` 一族 + 两处副本）。
5. **门控开关就是设置区里的驱动模式字段**，已可从 USB 侧直接改。

⇒ **连拍不是功能缺失，是被「模式设置」门控。** 那个开关已经能扳动了。

**仍未解决**：

| # | 问题 | 说明 |
|---|---|---|
| 1 | **连拍速度档位** | 隐藏连拍目前是什么速度？`DRIVE_MODE_CONT_SHOOTING_OPTION_{HI_PLUS,HI,MID,LOW}`（表基 `0x41B4FB0`）如何与设置区字段联动？**注意 FX30 固件里 `customFps_Elec_*` 零命中**（无速度调节项），可能是机型裁剪 |
| 2 | **为什么菜单不显示该选项** | 隐藏 ⇒ 菜单项的可用性判定读的是别的状态（`.bss` 镜像？），需要弄清才能让它「正常显示」 |
| 3 | **电子快门 11fps** | A6700 用同传感器实现了 11fps，FX30 硬件无阻碍，但 `dial_hi_plus_in_electric_shutter` 在 FX30 **根本不存在**（不是 id 找不到，是消费方不存在）⇒ 可能需要更深的固件改动 |
| 4 | **其余隐藏模式枚举** | `EXTERN_VAL_DRIVE_MODE_*` 表共 17 项，只验证了 BURST。候选：`SPEED_PRIOR_BURST` / `RAW_BURST` / `BOL_BURST` 等（索引对应关系需逐个实测） |
| 5 | ~~`0x08DC14` 语义~~ | ~~第三派生字段，固件自动联动改写~~ ❌ **已撤回**：实测同一模式下 9 个不同取值，是运行时噪声（计数器/校验/时间类），**不是模式的函数，也不存在「固件联动」**。连带 `0x7A640` 同样 |

**需要的对比基准**（任一即可，仍然有效）：

1. **A7C2（ILCE-7CM2）Ver.2.01 固件包** — 与 A6700 同代但机型不同，可用于确认「限制原因枚举」是否为新代通用架构
2. **一台 FX3 的同格式 `/setting` 目录清单**（只要文件名与大小，不含内容）

**背景证据**：FX3 与 A6700 均有连拍，FX30 与二者同 BIONZ XR 平台；A6700 用与 FX30 **相同的 26MP 传感器**实现了电子快门 11fps——硬件层面不存在阻碍。

---

## 与其他机型研究的差异

同代机型上已有公开工作，但结论不同，值得对照：

| | A6700 | A7C II | **FX30** |
|---|---|---|---|
| 文件读取 | ✅ 可读 `/usr/lib/appFw.so` | ✅ 有文件命令 | ✅ **已实测**（`libJiritsu.so` 233,416 B，SHA-256 一致） |
| Jiritsu 写入 + `dlopen` | ✅ A6700 2.00 | ✅ 有记录 | ✅ **已实测**（`res=0`，代码已执行） |
| 内存通道 | 走 Jiritsu（`0xff03` 不用） | — | ⚠️ 未通（128 语义待区分） |
| 路径穿越 | 有记录 | 有记录（`/tmp/jiritsu/../..`） | ✅ **`/../../` 可越出**，`arg0=0` 分支 |
| 驱动模式属性 ID | — | — | ✅ **`0x04B8`** + `.bss` 地址已解出 |

> 早期「FX30 的 Cinema Line 分支裁掉了文件通道」的推测**已被实测否定**。
> 跨机型互证细节见 [`docs/14-peer-crosscheck.md`](docs/14-peer-crosscheck.md)。

---

## 仓库内容

```
docs/01-session.md       会话建立、驱动选择、会话语义陷阱
docs/02-command-map.md   命令空间完整图谱（本次测绘核心产出）
docs/03-backup.md        备份数据结构与 ID 布局验证
docs/04-dead-ends.md     此路不通的记录（避免重复踩坑，含 6 条实机负结果）
docs/05-firmware-analysis.md  固件解密与 BKID 定位方法
docs/06-related-projects.md   相关开源项目目录（其他作者，17 项）
docs/07-jiritsu-breakthrough.md  Jiritsu 写通道（结论修正）与固件结构分析
docs/08-appfw-capability-table.md  三机型能力表结构与差分结果
docs/09-realtime-results.md  实机测试结果（0x1001 存在 / 0xff01 未通）
docs/10-setting-channel.md   真实文件系统读写 + 设置区读写（实机验证）
docs/11-drive-mode-ids.md    BKID 名称→数字 id、三机型对照、两代建模差异 ⭐
docs/12-property-accessor-table.md  属性访问器表：id → .bss 地址 ⭐
docs/13-flash-layout.md      官方 partinf.conf / mount.conf 分区与挂载
docs/14-peer-crosscheck.md   与上游研究者的通道互证（跨机型逐条对照）⭐
docs/15-payload-elf-rules.md dlopen 载荷的 ELF 结构规则（五条铁律 + 症状对照）⭐
docs/16-firmware-unpack.md   官方固件包解包（UFU 容器 + 加密 FDAT + 四机型镜像规模）
docs/17-disclaimer-and-boundaries.md  免责声明 · 脚本风险分级 · 危险命令清单 · 责任限制 ⭐
docs/18-开启隐藏连拍-最简步骤.md  一键开启隐藏连拍的 4 步流程 + FAQ ⭐ 先看这个上手
tools/                   探测脚本（Python / PowerShell），按风险分级见 docs/17
tools/offline/           纯静态分析（名称→id→.bss 地址链），不接触相机
tools/payload/           载荷构建与结构校验（zig + ELF 自检，不含下发脚本）
NOTICE                   来源、致谢与重要声明
```

**不包含**：固件二进制、备份文件、机身序列号、加密密钥、把载荷下发到相机的脚本。

---

## 安全边界

- **大部分工具只发送读请求**；但 `tools/probe_fileid_map.py` 在传入 `--delete <file_id>` 或 `--mount` 时**会写相机**（删除 `/tmp/jiritsu` 文件 + `0x4002` 重挂），`tools/probe_drive_write.py` **每次运行都会写设置区**（驱动模式）。完整分级见 [`docs/17 §三`](docs/17-disclaimer-and-boundaries.md)。
- 会话**不可复用**：每次操作应「相机 MSC → 一次运行内完成 → 干净退出 → 断电/拔插」，否则残留状态会让后续认证失败。
- **首次生效必须冷启动**：写入后**拔电池 ≥30 秒**才能让固件加载新值（关机再开机不生效）。
  但**生效之后**就不需要再拔电池了 —— 关机再开机、进菜单、切视频模式都保持。
  只有**手动修改驱动模式设置**才会掉回单张。
- **会话结束后相机会重枚举回 PTP**（PID `096F`）；下一次跑脚本要重新把 USB 模式切回「海量存储器」并插拔。
- `0x60F` 区间会使端点进入异常状态，应回避。
- **`0x4003`(FORMAT) / `0x4006`(FIRMUP) 不要发** —— 同族平台实测会卡死服务。
- 若要写备份（`cmd 0x02`），务必先留完整原始备份；**备份区写坏可能影响相机启动，该层风险未评估**。
- **出错先停止，不要盲目重试写入** —— 重复写入会把「一次可恢复的错误」变成「不可恢复的错误」。
- 所有探针在 `readHasp()` 后会校验长度是否为 **88 字节**；不等于 88 说明本次会话未完全建立，**后续结果一律不可信**。

---

## 致谢

- [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) — 认证帧、Senser 协议与 `print_backup` 的公开实现
- [YuuLuo/a7c2-service-preload](https://github.com/YuuLuo/a7c2-service-preload) — Jiritsu 通道与协议细节（A7C II 2.01）
- [Himpq/FireHydrant](https://github.com/Himpq/FireHydrant) — A6700 的内存访问方法与移植方法论
- [xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) — A6700 服务通道与 Pico 路线
- [nolan2628/Sony-ZVE-10-Camtool](https://github.com/nolan2628/Sony-ZVE-10-Camtool) — dlopen 载荷的 ELF 结构规则、`file_id` 槽位互证、`0x4002` 重挂语义
- [Lincan19540/fx30-firmware-research](https://github.com/Lincan19540/fx30-firmware-research) — FX30 服务模式连接链路、**HASP 88 B 的正确术语**、双句柄隔离坑

完整相关开源项目目录（核心 16 项，含 A7C2 生态 8 个衍生仓库）见 [`docs/06-related-projects.md`](docs/06-related-projects.md)。

非官方项目，与 Sony 无关。固件研究存在风险，后果自负。完整免责声明见 [`docs/17`](docs/17-disclaimer-and-boundaries.md)。

---

<a name="english-summary"></a>
## English summary

Research on the USB service session (Senser / Jiritsu) of the Sony **ILME-FX30, firmware 6.00**.

**Findings:** the service session is reachable over pure USB (Type-C + libusbK on both `054C:0E0E` and `054C:0336`), and authentication succeeds with PMCA's built-in key tables. Only two pFunc values respond: `0x10` (ProductInfo) and `0x40` (AdjustControl).

**Correction (2026-10-23):** `0xff01` (FileControl) was **not validly tested** — an earlier probe sent a path string as an `0x603` AdjustControl payload, and `0x80` (=128) is FileControl's own error code, not "unsupported". `0xff03` (MemoryDump) did not respond with the correct `{base,size}` payload. See `docs/07-jiritsu-breakthrough.md`.

A full command map of `pFunc=0x40` is documented, including a 2.25 MB backup blob readable via `0x603/0x05`, parsed into 25,737 properties whose ID layout matches PMCA's definitions (verified via model name / model code / serial number / recording-limit anchors).

**Update (2026-10-24):** `0x603/0x05` takes a `fromMemory` byte — an empty payload is equivalent to `0` (flash presets), while `\x01` returns the **live in-memory values**. All earlier snapshots used the empty payload, which is why they showed no runtime state. With live snapshots, a per-id read (`0x603/1` + `u32le id`, payload format previously missed) and a full-blob write (`0x603/4` + `u32le protect` + data, then `0x603/3` to commit) were both verified on-device, including a 2,253,568-byte write-back. Arbitrary reads of the **real root filesystem** are also possible via `SET_FILE_PATH` (`0x400F`) with an `/../../` path plus `GET_FILE2` (`0x4011`, `arg0=0`), proven by reading a system library whose SHA-256 matches the unpacked firmware byte-for-byte. See `docs/10-setting-channel.md`.

**Current state:** `feature_id = 419` is `DRIVE_MODE_CONT_SHOOTING`, and its flags are **identical on FX30 and FX3**, so the capability table is not the switch. Three later findings closed the remaining USB-side possibilities:

1. **The 2.25 MB "PDT" blob is not user settings.** It is `/setting/Backup.bin`, a dump that `bk.elf` (`bk g[ChipID] BackupID`, `c:CP / m:MP`) reads out of the CP/MP chip; the factory copy shipped in the firmware package is byte-identical in size (2,253,564).
2. **A control experiment appeared to rule out the single byte.** Writing `0x08` (self-timer) persisted across a power cycle but the camera still booted in single-shot mode.
3. **The per-id table (`0x603/1`) is mode-independent.** A full 1,024-entry scan in single-shot vs self-timer mode showed **zero** differing values.

**Update (2026-10-24, later the same day) — items 1 and 2 above are now corrected, and the burst mode has been enabled on-device.** The apparent dead end was a methodology error, and it is worth recording precisely:

* The 2.25 MB blob **is** the boot-time truth source after all. What was missing was the *second* field: `0x8EF80` and `0x91690` are **two layers of the same setting**, and writing only one of them makes the firmware fall back to single-shot. Verification also has to be a **cold boot** (battery out for ≥30 s) — powering off and on again is a *warm* restart that restores the `nflasha5` image and wipes the change.
* The two offsets do **not** store property ids; they store **0-based positions in two enumeration tables** in `.data.rel.ro` (16-byte records `{char* name; u32 id; u16 code}`): `0x8EF80` → `EXTERN_VAL_DRIVE_MODE_*` (table base `0x41A0550`), `0x91690` → `DRIVE_MODE_*` (table base `0x41A28F0`). All 12 labelled snapshots map consistently, and the value sets observed across 27 snapshots (`0x8EF80` ∈ {0,1,2,8,12}, `0x91690` ∈ {0,5,9}) fall entirely inside the table index ranges. This is why earlier "candidate burst values `0x01`/`0x04`/`0x10`" guesses — derived by treating them as ids — were wrong.
* Writing `0x8EF80=0x01` **and** `0x91690=0x01` together, then cold-booting, puts the camera into **burst shooting** — verified on-device: it actually bursts. It is a **hidden mode**: the drive-mode menu does not show the entry, and touching the menu drops it back.
* The requirement is confirmed by direct A/B: writing `0x8EF80` alone (leaving `0x91690` at `0x00`) does nothing, while writing both together works. (An earlier version of this text cited the firmware rewriting `0x8DC14` as corroboration; **that claim has been retracted** — `0x8DC14` takes nine different values while the mode stays the same, so it is runtime noise, not a mode-derived field. The same applies to `0x7A640`.)

```bash
python tools/probe_drive_write.py 0x8EF80=0x01 0x91690=0x01
```

* A related correction: `0x603` has **two distinct command faces** that earlier documents conflated. `category=0x1001, command=0x603` returns the **same fixed `01 02 00 10` for every id** (including boundary ids) — it is an ack, not a property value — while `category=0x0603, command=0x0001` is the per-id read, and the BKID registry ids are not reachable there (all `res=129`). The historical "the first payload byte is a namespace" line of reasoning therefore rested on a fixed ack and is a false premise.

**New on the offline side:** the name→id mapping table (16-byte records, ~25,167 entries) gives `BKID_APP_setting_drive_mode_cont_shooting = 0x04B8` (= 1208), matching an independent earlier result. A second table (0x58-byte records, 2,692 ids) holds eight tiny accessor stubs per property whose `adrp + ldr/str` bodies encode the target `.bss` address directly — so every setting id can be mapped to its RAM location **without executing anything**. The burst family lives at `0x831F844`/`0x48`/`0x4C` with copies at `0x8220304`/`0x08` and a mirror at `0x89254F0`; all three clusters must be written together or the mirror rolls it back. FX30 and FX3 share the id space digit for digit; A6700 uses a shifted numbering and a different record layout (the parser does not carry over).

**Conclusion so far:** the burst feature is not missing from FX30 — its firmware contains every related name, list entry and constant, its `.text` is actually 11,128 bytes *larger* than FX3's, and a symmetric instruction-level diff shows 19.41% vs 19.38% unique code (net 10,848 ≈ the size delta), i.e. a **function-level reshuffle**, not per-function rewrites. The gate is the drive-mode setting, and it can now be flipped from the USB side — no in-camera code execution needed. See `docs/11`, `docs/12`, `docs/13`. No firmware binaries or device-unique data are included.

**Cross-check with upstream (2026-10-24):** the author of `xyzhangxin/sony-a6700-powerful` published their A6700 three-step sequence in Issue #2. Compared against FX30 6.00, the backbone matches **byte for byte** — same `pFunc=0x40` / `category=0x1001`, same `{area, file_id, transfer_mode}` payload prefix (`[0, 2, 0] + data`), and `0x4007 / file_id=2` writing `/tmp/jiritsu/libJit.so`. They cautioned that their loader path was only verified on A6700 2.00 and that FX30 needs separate confirmation, and that A6700 payloads must not be reused directly. Both points are now settled on our side: FX30 6.00 is **verified on-device** (`res=0`, and a self-written side-effect file read back proves the code ran), and we did not reuse their payload — we wrapped the stock `libssp.so` and later built a standalone 2,064-byte `.so` with zig. Two numbering details remain open: they describe `0x4010 / file_id=0` as a "reader configuration" and `0x4008 / file_id=0` as retrieving the result, whereas our disassembly of `get_jiritsu_area_filename()` maps slot 0 to `tmmc.jit` and we close the loop on slot 3 (`jit.log`); both may be the same thing under different names. Finally, their "260 sectors" (~133 KB) indicates access at the **block-device sector layer**, whereas this repository works at the filesystem and property-semantics layers — a difference in level, not a contradiction. See `docs/14-peer-crosscheck.md`.

**dlopen payload ELF rules (2026-10-24, learned from a third body):** an ecosystem sweep turned up `nolan2628/Sony-ZVE-10-Camtool` for the ZV-E10, which independently proves that Jiritsu-based `dlopen` is **not** an A6700/A7C2 exclusive — an entry-level body runs it too, and it gets a full shell (440-byte payload doing `fork` → `execve("/bin/sh")`) with `Uid: 0 0 0 0` and `CapEff: ffffffffffffffff`. Their five hard-won rules for a loadable payload: (1) `.dynamic` must sit in a **writable** `PT_LOAD` — glibc writes `l_info`/`DT_DEBUG` back into it and SIGSEGVs otherwise, taking `im.elf` and the USB connection with it; (2) `PT_GNU_STACK` must be present; (3) `vaddr ≡ off (mod p_align)`; (4) the constructor entry's instruction-set bit must match the code mode (ARM32 Thumb `|1` / ARM `|0`); (5) **do not carry `PT_GNU_RELRO`** — `_dl_protect_relro` mprotects whole pages, so it silently freezes `.dynamic` and any `.bss` sharing that page. Rule 5 hit our own artifact: the default link added RELRO over `0x20000..0x21000`, harmless for the current all-stack stage-1 but fatal for any stage-2 global buffer. Adding `-Wl,-z,norelro` dropped the file from 2,192 to **2,064 bytes** and made its segment layout isomorphic to their proven 440-byte payload. Two by-products: their cleanup whitelist independently confirms our `file_id` slot table (0 = `tmmc.jit`, 3 = `jit.log`), and return code **130 means nflasha6 was unmounted**, not "file missing" — deleting `libJit.so` requires a `0x4002` (MOUNT) re-mount. Their docs also flag `0x4003` (FORMAT) and `0x4006` (FIRMUP) as service-freezing, and use `0xff01` to `put` files at arbitrary paths — something FX30 answers with 128 for every attempt, the clearest unresolved body-to-body divergence so far. See `docs/15-payload-elf-rules.md`.

**A7C II 2.01 unpacked, four-body comparison (2026-10-24):** the official `BODYDATA.DAT` for the ILCE-7CM2 turned out to be wrapped differently from every body we had handled before — an **UFU container** (`\x89UFU` + `len(u32be) + tag + payload` chunks: `DATV / PROV / UDID / FDAT / DEND`) whose FDAT section is **encrypted**, whereas FX30 6.00, FX3 3.00 and A6700 2.00 all ship that section in plain `UDTRFIRM` form. It decrypts with fwtool's 4th-gen `CXD90057_k8` crypter (AES-CBC; the IV sits in the last `0x110` bytes, the first 512 bytes use ECB, and `(size-0x110)` must be a multiple of 1024). All **1,113,212 blocks pass checksum with zero errors**. A rewritten bulk decryptor runs at **48.4 MB/s vs fwtool's 1.3 MB/s** (41 s instead of 14 min) and is byte-identical to the reference implementation.

The comparison produced three corrections. First, **id shifts are not uniform**: the `0x02B1` family (electronic-shutter dial positions) moves **+5** in the second generation, while the `0x04B8` family (drive-mode settings) moves only **+1** — so the earlier "A6700 is uniformly +5" note is wrong and no single offset can be used for cross-body conversion. Second, the gap in FX30 is now pinned to a single item: `DRIVE_MODE_CONT_SHOOTING_OPTION_HI_PLUS` **exists** in FX30 (`0x0001`), but `dial_hi_plus_in_electric_shutter` **does not exist at all** (A6700 has `0x12D5`, A7C2 has `0x12D1`) — so writing A6700's id into an FX30 PDT cannot work, because FX30 has no consumer for it. Third, drive-mode modelling has **three** generations, not two: A7C2 2.01 is the only body carrying `DRIVE_MODE_EXPANDED_OPTIONS_*` (26 entries) and `DRIVE_MODE_NON_LIMITED`, and it also has the four `LIMIT_CONT_SHOOTING_HI_PLUS/HI/MID/LO` speed tiers (0x13FB/0x13FD/0x13FF/0x1401) that A6700 2.00 lacks. FX30 and FX3 remain **zero-unique** against each other for the third independent time.

One more trap worth recording: `libJiritsu.so` is **exactly the same size** (233,416 B) on FX30 / A6700 / A7C2, yet SHA-256 differs on all four bodies and `.text` byte-level identity is only **9.6%–9.8%** despite lengths differing by <0.2% — these are different *link instances* of the same source, so block-level identity metrics are useless for similarity here (the same lesson as `docs/05`). All four bodies also carry an `nflasha5` warm-boot image (200–255 MB), which is the quantitative confirmation that "power off then on" is an image restore, not a cold boot. See `docs/16-firmware-unpack.md`.

**Property-accessor table, three generations (2026-10-24, corrected):** the accessor table in `.data.rel.ro` stores its function pointers as zeros in the file — they are restored at load time by `R_AARCH64_RELATIVE` relocations, so the raw file must be walked through `.rela.dyn` and the `r_addend` used to recover each target. The earlier heuristic ("find a strictly increasing id column") does not work for A6700 / A7C2 because neither generation has an id field; the working heuristic is "a record contains several consecutive `.text` function pointers". Measured layouts:

| Body | Table base | Stride | Slots | id field |
|---|---:|---:|---:|---|
| FX30 | `0x0402EB20` | `0x58` | 11 | `+0x28` |
| FX3 | `0x0402ADE8` | `0x58` | 11 | `+0x28` |
| A6700 | `0x04818040` | `0x50` | 10 | none — index is the id |
| A7C2 | `0x0571A578` | `0x68` | 13 | none — index is the id |

The FX30 record is **5 accessors + id(+0x28) + 5 accessors**; an earlier document mistook the address of the first id field (`0x0402EB48`) for the record start, which shifted the base and the field offsets by the *same* `0x28` and therefore cancelled out — "look the record up by id" kept working while every pointer read was off by one slot. Such errors can only be exposed by disassembling what was actually read. Also note that four distinct coordinate systems must never be mixed: PDT file offset (`0x8EF80`), the `0x50000`-family property id used by `0x603/1`, the BKID registry id (`0x04B8`), and the `.bss` virtual address (`0x831F82C`).

**A caution worth repeating:** this repository documents a service session, not a way to enable features. Almost every endpoint here is a *read* path, and the few write paths carry real risk of bricking the unit. See `docs/17-disclaimer-and-boundaries.md` for the per-script risk classification, the list of commands that are known to freeze the service, and the liability limits.
