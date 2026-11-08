# ILME-FX30 Service Mode Research

**索尼 FX30（Ver.6.00 / 6.01）服务模式的通道边界测绘**

> 本仓库记录在 ILME-FX30 固件 6.00 与 6.01 上对 USB 服务会话（Senser / Jiritsu）的实测探索：哪些通道可达、哪些被裁剪、数据长什么样。
> **不含固件二进制、不含备份数据、不含机身唯一信息。**

[English summary](#english-summary)

---

## 30 秒速览

**这是什么**：ILME-FX30（6.00 / 6.01）USB 服务模式（Senser / Jiritsu）的通道测绘记录，含一个已复现的连拍开启方法。

**能做什么**

| 能力 | 版本 | 状态 |
|---|---|---|
| 服务会话 + 认证 | 6.00 / 6.01 | ✅ 可复现 |
| 隐藏连拍（PDT 直写） | 6.00 | ✅ 实机 3 次复现 |
| 隐藏连拍（固件等长补丁） | 6.01 | ✅ 实机生效，7 字节可回滚 |
| 读真实根文件系统（`0x1001`） | 6.00 / 6.01 | ✅ |
| 设置区全量写 | 6.01 | ❌ 内容校验（`129`） |

**先读哪两篇**

- 想开连拍 → [`docs/18-开启隐藏连拍-最简步骤.md`](docs/18-开启隐藏连拍-最简步骤.md)
- 想了解边界 → [`docs/17-disclaimer-and-boundaries.md`](docs/17-disclaimer-and-boundaries.md)

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

> ⚠️ **注意：上面这条「PDT 设置区直写」路径仅 Ver.6.00 有效，6.01 已封堵。**
> Sony 在 6.01 固件里给 PDT 写入加了**内容校验**：写入必须与固件内部状态一致，
> 任何字段改动（含连拍字段）都返回 `129`，只有**原样写回**才 `res=0`（他人 6.01 实机
> 三组对照确认：RAW 原样写回 ✅ / 改连拍字段 ❌ / 改无关空白区也 ❌）。
>
> **但这不等于 6.01 无解——换通道即可，见下方「两条通道」。**
> `appFw.so` 的等长产品标志补丁在 **6.01 上已实测生效**，且可反向回滚。
> **PDT 封堵 ≠ 功能封堵。**
>
> **开启成功后切勿升级固件，否则立即失效且无法再写回。** 详见
> [§版本兼容性](#版本兼容性)。

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

## 两条通道：PDT 直写 vs appFw 补丁

这两个通道**互不影响**，6.01 的封堵只针对前者。

| 通道 | 作用层 | 6.00 | 6.01 | 回滚方式 | 影响面 |
|---|---|---|---|---|---|
| **PDT 设置区直写** | 机身设置数据 | ✅ | ❌ 内容校验（`129`） | 写回原值 | 单机设置 |
| **`appFw.so` 等长补丁** | 固件数据段 | 未测 | ✅ **已实测** | 逐字节反向 | 整包重打包 |

### 6.01 的等长补丁（2026-11 补充）

对 `appFw.so` 的**产品标志字节**做等长修改（`00 → 01`），不触碰代码段：

| 项 | 值 |
|---|---|
| 原库大小 / sha256 | 79,032,104 B / `72d9136f…b24883` |
| 派生库 sha256 | `ab0333be…b79886` |
| 差异 | **恰好 7 字节**，`.text` 段零改动 |
| 位置 | 连拍主记录 1 处 + 速度子记录 4 处（间距 `0x50`）+ 关联记录 2 处 |

性质说明：

- 这是**重打包路线**，需要重新封装固件后再刷入，不是运行时写入。
- 本仓库**不提供**打包脚本与偏移清单的可执行版本；偏移属于研究数据，见 `docs/08-appfw-capability-table.md` 的结构说明。
- 与 PDT 直写相比，它绕开了 6.01 的内容校验，因为改的是固件镜像而非机身设置区。

> 结论：**6.01 上仍然有可行路径**，只是要换到固件层而不是设置层。

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

## 进展时间线（2026-10-23 ~ 10-30）

逐期过程记录已移至 [`docs/20-进展时间线.md`](docs/20-进展时间线.md)（489 行）。
该文件保留当时的原始判断；与最新结论冲突时，以「两条通道」一节为准。

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
| 2 | **为什么菜单不显示该选项** | 隐藏 ⇒ 菜单项的可用性判定读的是别的状态。**2026-10-26 进展**：已排除 8 个地址假设与 6 个取证方向；19 槽谓词假设已证伪（FX3/FX30 逐槽相同）。当前收敛到唯一判据——运行时 `+0x5B0` 数组是 **5 项还是 23 项**（见上文 §4）。详见 `45-连拍菜单攻关-证伪台账.md`、`46-19槽谓词假设的静态证伪.md` |
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
FX30-连拍-复现实操手册.md  一键开启隐藏连拍（面向人，含原理与全部环境坑）⭐ 先看这个
FX30-连拍-Agent执行卡.md   一键开启隐藏连拍（面向执行型 Agent，步骤化无歧义）
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

<a name="版本兼容性"></a>
## 版本兼容性（⚠️ 必读）

| 固件版本 | PDT 直写（本方法） | 说明 |
|---|---|---|
| **Ver.6.00** | ✅ **有效** | 本仓库所有实机结论的基础版本 |
| **Ver.6.01** | ❌ **已封堵** | 对 PDT 写入做内容校验，任何字段改动返回 `129`，原样写回才 `res=0` |

- **依据**：他人 ILME-FX30 Ver.6.01 实机三组对照实验（2026-10-25）——RAW 原样写回 `res=0` ✅；
  改 `0x8EF80/0x91690` ❌；改无关空白区 1 字节 ❌。结论：6.01 不是「特定字段保护」，
  而是**整个 PDT 写入内容必须与固件内部状态一致**。
- **本仓库机器版本判定**：本机 `GET_VERSION` 报 6.00、`config.yaml` 报 6.01，历史上记为悬案；
  现据他人真 6.01 的对照，判断本机为**真 6.00**（故直写一直成功）。
- 🔴 **开启成功后切勿升级固件**——升级到 6.01 会立即封死直写，已开启的隐藏连拍
  「手动改设置掉回」后将**无法再写回**。
- 本仓库后续「替换菜单 UI」路线（改 `appFw.so` + 重打包官方更新包刷入）**不依赖 PDT 直写**，
  理论上可覆盖 6.01，但截至本版仍在推进中，未发布。

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
