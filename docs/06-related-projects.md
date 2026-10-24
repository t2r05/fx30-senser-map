# 06 · 相关开源项目目录

> 本项目研究过程中**参考 / 对照 / 邻近的其他作者开源项目**汇总。仅列项目名、仓库与一句话定位，便于溯源与逐个学习。
> **不含任何固件内容、备份数据或机身唯一信息。**

核验日期：2026-10-24。

## 目录

| # | 项目名 | 仓库 | 类别 | 一句话定位 |
|---|--------|------|------|-----------|
| 1 | **ZVE-10-Camtool** ⭐ | [nolan2628/Sony-ZVE-10-Camtool](https://github.com/nolan2628/Sony-ZVE-10-Camtool) | 方法 · 第三方机型 | ZV-E10 服务模式工具箱：Jiritsu dlopen 载荷 + 远程 shell + 整分区备份（**载荷 ELF 铁律出处**） |
| 2 | **Powerful6700** | [xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) | 主线 · A6700 | A6700 功能解锁（USB 直连 + Pico 双路线），v0.2.0 |
| 3 | **Powerful6700-Windows** | [wanghm105/Powerful6700-Windows](https://github.com/wanghm105/Powerful6700-Windows) | 主线 · 移植 | 上述项目的 Windows 版（GPL-3.0，PySide6） |
| 4 | **A7C2-FL23 / A7C2 Tools** | [QAQLeonard/a7c2-fl23-research](https://github.com/QAQLeonard/a7c2-fl23-research) | 主线 · A7C II | 创意外观 / 快门声 / 竖屏工具（v3.0.3） |
| 5 | **a7c2-service-preload** | [YuuLuo/a7c2-service-preload](https://github.com/YuuLuo/a7c2-service-preload) | 上游 · 机理 | A7C II 服务模式预加载与代码执行链路 |
| 6 | **a7c2-camera-tools** | [YuuLuo/a7c2-camera-tools](https://github.com/YuuLuo/a7c2-camera-tools) | 上游 · 工具 | 同作者第二仓库：2.00 包构建器 + CP 色表校验 |
| 7 | **a7c2-qemu** | [chocotan/a7c2-qemu](https://github.com/chocotan/a7c2-qemu) | 上游 · 模拟 | **QEMU 跑原厂固件**，已进拍摄主界面与菜单 |
| 8 | **PMCA-RE RELOADED** | [masterflai/pmca-re-reloaded](https://github.com/masterflai/pmca-re-reloaded) | 上游 · 重写 | PMCA-RE 的 Rust 重写，含相机设置内存模块 |
| 9 | **ILCE-7M4-RE** | [DavidBuchanan314/ILCE-7M4-RE](https://github.com/DavidBuchanan314/ILCE-7M4-RE) | 上游 · 逆向 | A7M4 逆向笔记（bootrom / serial boot） |
| 10 | **Sony-PMCA-RE** | [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) | 上游 · 基础库 | Sony 服务协议基础实现（Senser / print_backup / fwtool） |
| 11 | **FireHydrant** | [Himpq/FireHydrant](https://github.com/Himpq/FireHydrant) | 相关 · 方法论 | A6700 内存访问方法 + 改动分层验证框架（纯文档，无地址/代码） |
| 12 | **A7C2 深挖笔记** | [wu-hongjun/A7C2](https://github.com/wu-hongjun/A7C2) | 相关 · 笔记 | AP 选择器 / CP 校正表 / 6 个 ST 自定义槽 |
| 13 | **a7c2-lut-photo-research** | [taoking/a7c2-lut-photo-research](https://github.com/taoking/a7c2-lut-photo-research) | 相关 · 研究 | 机外 LUT 工具 + 只读固件研究 |
| 14 | **sony-a7c2-fl23-linux** | [nimrc/sony-a7c2-fl23-linux](https://github.com/nimrc/sony-a7c2-fl23-linux) | 相关 · 移植 | A7C2 工具的 Linux 一键脚本 |
| 15 | **a7c2-fuji-ai-skill** | [FlyMercurian/a7c2-fuji-ai-skill](https://github.com/FlyMercurian/a7c2-fuji-ai-skill) | 相关 · 包装 | 把 A7C2 工具包装成 AI skill |
| 16 | **Recipe Lab** | [voxivoid/recipe-lab-sony-pmca](https://github.com/voxivoid/recipe-lab-sony-pmca) | 相关 · 生态 | 基于 PMCA 的创意外观 App |
| 17 | **fx30-firmware-research** | [Lincan19540/fx30-firmware-research](https://github.com/Lincan19540/fx30-firmware-research) | 相关 · FX30 | 只公开「服务模式连接 + HASP 88 B」（2026-10-24 建仓），其余「暂不公开」 |

> 盘点口径：**核心相关 16 个**（服务模式 / 固件逆向 / 功能解锁）。PMCA App 生态与 PTP 控制类项目不入表。
> A7C2 生态已分裂出 8 个衍生仓库（#4 #5 #6 #7 #12 #13 #14 #15），多为 FL2/FL3 移植与再包装，**对驱动模式无新增信息**。

## 说明

### 与本仓库的重叠度（2026-10-24 新增一项）

**`Lincan19540/fx30-firmware-research`**（FX30，建仓 2026-10-24）目前只公开
「MSC `0E0E` → 服务模式 `0336` + Senser 认证 + 读 HASP 88 字节」——正是本仓库
10 天前走完的第一步。它完全架在 `pmca`/`transport` 上做调用层封装，没有独立协议实现。

两处可借鉴：

1. **术语**：它把 `readHasp()` 的返回值叫「HASP 服务令牌」，比本仓库早期文档的
   「88 字节机型信息」准确。pmca 源码 `SONY_PRODUCT_INFO_READ_HASP = (0, 0x001f)`
   可证：`0x10` 是 ProductInfo **通道**，`0x001f` 只是其中一个 **item**。
2. **双句柄坑**：同一 USB 句柄先做 `getDeviceInfo()`/`getCameraInfo()` 再发认证，
   bulk 端点状态会被污染 —— 查询必须用独立句柄、用完 `dispose_resources`。
   本仓库的 `enter_service()` 只做轻量枚举，不触发该问题；但将来若要「先读型号再决定探针行为」，
   必须改成双句柄。

> ⚠️ 该仓库 `assets/` 内有微信/支付宝收款码，README 同时声明 CC BY-NC-SA 4.0 与「不用于商业行为」。
> 打赏本身不违规，但结合「其余研究阶段暂不公开」，不要把「暂不公开」理解为「以后一定公开」。

### 主线（同代机型的可用成品）

- **Powerful6700**（A6700 2.00，v0.2.0）：当前版本**普通 USB 直连、无需 Pico**，勾选解锁 + **冷重载**（关机 → 拔电池 → 等 10s → 插电池 → 开机）生效；开放 FTP / 关机快门帘 / 灵活曝光 / 电子快门声。仓库另保留 **Pico 路线**（冷启动引导 → Fastboot → 读已知范围备份）。v0.2.0 修 USB 连接，Windows 版另有「稀疏功能状态备份与恢复」。
- **A7C2-FL23 / A7C2 Tools**（A7C II 2.01，v3.0.3）：经 USB 服务模式写入固件程序与设置，同样需**冷重载**；基于 Sony-PMCA-RE + `fwtool.py` + a7c2-service-preload。

### ZVE-10-Camtool（跨机型方法参照，2026-10-18）

第三方机型的完整服务模式工具箱，证明了 **Jiritsu dlopen 不是 A6700/A7C2 独有**。它给出的载荷 ELF 铁律是本项目 10-24 修正构建参数的直接依据，详见 `docs/15-payload-elf-rules.md`。


### 上游（上述项目所依赖 / 借鉴）

- **a7c2-service-preload**：记录从 USB 服务会话到**一次性 root 代码执行**的完整链路（Jiritsu 文件命令 + 路径穿越 + `/etc/ld.so.preload`）。理解「写通道」的关键文档；**注意其为临时 RCE，不永久关闭签名校验**。
- **ILCE-7M4-RE**：A7M4 逆向笔记（含 bootrom / serial boot 思路），Powerful6700 明确参考。
- **Sony-PMCA-RE**：本项目与上述项目共同的基础——认证帧、Senser 协议、`print_backup`、`fwtool.py`。

### FireHydrant（A6700，纯方法论，2026-10-22 更新）

四篇文档，**刻意不含地址、偏移、哈希与脚本**（作者说明：给出「位置 + 前后字节」等于给出可照抄的补丁，会让人跳过版本校验与回滚设计）。因此它的价值全在方法与判断框架：

| 文档 | 可迁移内容 |
|---|---|
| `DEVICE_CHANNEL.md` | `/proc/self/maps` 取 base；两段 LOAD 与三套地址基准不可混用；改代码段须 `dc civac` + `ic ivau`；私有映射 + COW ⇒ 运行时改动断电即恢复 |
| `fl2_fl3/README.md` | 三条独立证据（符号/参数 · **参数链** · 准入层）；三层改动分开验证；「只切电源开关不够，必须拔电池」；「运行时补丁会掩盖文件改动」 |
| `cine_ei/README.md` | **菜单准入 / 支持层 / 计算基准** 三层模型；「菜单可见 ≠ 可用」「可选 ≠ 链路打通」；运行期改准入 → **原厂 setter 自己持久化** |

**本项目已独立核对的两处数据**（对方只给了两个精确字节数，均可验证）：

| 对方说法 | 实测 | 结果 |
|---|---|---|
| 应用主程序载体 89,027,992 B | A6700 `lib/appFw.so` = 89,027,992 B | ✅ 精确吻合 |
| CP 模式数据文件 17,892,024 B | A6700 `nflasha8_unpacked/cpapp-b.bin` = 17,892,024 B | ✅ 精确吻合，且与官方 `partinf.conf` 的 `nflasha8 = CP Data` 互证 |

**两处我方对其结论的限定**：

1. 「`libJit.so` 放模块会遮蔽原库」——**对 A6700 成立；FX30 上该槽初始为空**（`GET_FILE` 返回 `0x10000006` file non-existent），但**可以写入并会被 dlopen**，见下方 2026-10-24 更新。
2. 「」中提到的「约 114 对禁止计数/限制字节」属 **Cine EI / Log shooting 课题**，与驱动模式/连拍无关，不要混用。

**注意**：`/tmp/jiritsu` 位于 `nflasha6`（Jiritsu 25 MB，flash 分区），残留文件**跨重启保留并在后续加载时再次执行** —— 与 A6700 一致，用完必须 `FILE_DELETE (0x4009)`，不能靠断电清除。

---

## Powerful6700 作者 2026-10-24 的公开回复（Issue #2 交叉核验）

对方（`xyzhanxin`）在 A6700 项目 Issue #2 下回复了本项目的提问，核心内容与本项目实测的对照：

| 对方说法 | 本项目 FX30 Ver.6.00 实测 | 判定 |
|---|---|---|
| 不走 `0xff03` MemoryDump / `0xff01` FileControl，走 Senser 认证后的 Jiritsu 文件服务 | 两者在 FX30 上**全部 128** | ✅ 边界相同 |
| `pFunc=0x40` / `category=0x1001` | 相同（`0x4001`–`0x4012`） | ✅ |
| 载荷前缀 `{area=0, file_id, transfer_mode=0}` | `[0, 2, 0] + data`，**逐字节一致** | ✅ 字节级互证 |
| `0x4007 SET_FILE / file_id=2` 加载 `/tmp/jiritsu/libJit.so` | `res=0`，读回自写副作用 `PWNED-JITLOG-V4` | ✅ **已实证执行** |
| 「固定范围」不是 `0x603/0x05` 的 BK4 设置区 | 本项目独立判定 PDT 是 CP/MP 参数**备份副本**，启动不从它恢复 | ✅ 同向 |
| `0x4010 SET_FILE_2 / file_id=0` = 发送「读取器配置」 | 反汇编判定 `0x4010` = 配合 `0x400F` 的**按路径写**；`file_id=0` 落点 `tmmc.jit` | ⚠️ 编号语义待实测 |
| `0x4008 GET_FILE / file_id=0` = 取回「执行结果」 | `file_id=0` 是 `tmmc.jit`；本项目用 `file_id=3`（`jit.log`）闭环成功 | ⚠️ 同上 |
| 加载路径「仅在 A6700 2.00 验证，FX30 6.00 仍需单独确认」 | **已确认**：FX30 6.00 同构可用 | 🟢 本方补上 |
| 「目前没有已验证的驱动模式属性 ID 可提供」 | 本项目已解出 `BKID_APP_setting_drive_mode_cont_shooting = 0x04B8` 与属性访问器表 | 🟢 路线不同 |

**两条路线差异**（不是冲突，是层次不同）：

| 层次 | Powerful6700 | 本项目 |
|---|---|---|
| 块设备扇区 | 260 扇区（`260 × 512 = 133,120` B）固定范围 | 未做 |
| 文件系统路径 | — | `0x400F` + `0x4011` 任意路径读，SHA-256 级验证 |
| 属性语义（BKID） | 无 ID | BKID 表 25,167 条 + 属性访问器表 2,692 条 id |

> 旁证：`0x603/6` 报 PDT size = 2,253,052，`0x603/5` 实读 2,253,564，差 **512** —— 正好一个扇区，说明这条链路本身也是扇区对齐搬运。

## 对本项目（FX30）的意义

早期本项目仅测了 `0xff01`（FileControl）返回 `128`，据此判断「无写通道」。但上述项目显示：同代机型的实际写入**并不依赖 `0xff01`**，而走 **Jiritsu 文件命令 + 路径穿越**等另一套命令面；且改完都需要**冷重载**才从 NV 加载。

因此本项目的「无写通道」结论**需在 FX30 上重新验证 Jiritsu 命令面**，而非固守单一命令的返回码。（详见 [`04-dead-ends.md`](04-dead-ends.md) 与 README「与其他机型研究的差异」。）

---

*仅项目索引，不含固件内容。各项目版权与许可归原作者所有。*
