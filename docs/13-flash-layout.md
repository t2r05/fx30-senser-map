# Flash 布局与存储层身份（官方 conf 直读）

> 本文内容**不是推测**：全部来自固件包自带的两个配置文件，路径与用途由 Sony 自己在注释里写明。
> 来源：`firmware.tar_unpacked/0300_partconf/partinf.conf`、`firmware.tar_unpacked/0100_config/mount.conf`
> （生成时间戳 2021/11/26，Macro Version 2019/01/25）

---

## 一、分区表（`partinf.conf`）

格式：`start_sector, size_sector, type, flag`（1 扇区 = 512 字节）

| 节点 | 大小 | 官方注释用途 | 起始扇区 |
|---|---|---|---|
| `nflasha1` | 23.9375 MB | System Group — **SYSTEM (Updater)** | `0x00000080` |
| `nflasha2` | **20 MB** | System Group — **SYSTEM (Setting)** | `0x0000C000` |
| `nflasha3` | **75 MB** | System Group — **SYSTEM (Main)** | `0x00016000` |
| `nflasha4` | 12 MB | System Group — **MPR Flash Backup** | `0x0003B800` |
| `nflasha5` | 300 MB | System Group — **Warm Boot Image** | `0x00041800` |
| `nflasha6` | **25 MB** | System Group — **Jiritsu** | `0x000D7800` |
| `nflasha7` | 16 MB | System Group — **Rootfs** | `0x000E4000` |
| `nflasha8` | **64 MB** | System Group — **CP Data** | `0x000EC000` |
| `nflasha10` | 12 MB | Work Group — Work | `0x0010C000` |
| `nflasha11` | 300 MB | Work Group — **Log** | `0x00112000` |
| `nflasha12` | 40 MB | Work Group — Network | `0x001A8000` |
| `nflasha13` | 4 MB | Work Group — UpdaterWork | `0x001BC000` |
| `nflasha15` | **715 MB** | User Group — **usr** | `0x001BE000` |
| `nflasha18` | 20 MB | User Group — LensData | `0x00323800` |
| `nflasha22` | 65 MB | User Group — AiDictionary | `0x0032D800` |
| `nflasha23` | **64 MB** | Customer Group — **PMBP** | `0x0034E000` |

---

## 二、挂载表（`mount.conf`）

格式：`DeviceNode MountPoint type PartitionSize ClusterSize`

| 节点 | 挂载点 | 类型 | 大小 |
|---|---|---|---|
| `nflasha1` | *(none)* | vfat | 25,100,288 |
| `nflasha2` | **`/setting`** | vfat | 20,971,520 |
| `nflasha3` | **`/system`** | vfat | 78,643,200 |
| `nflasha5` | `/wbi` | wbi | 314,572,800 |
| `nflasha6` | ***(none)*** | vfat | 26,214,400 |
| `nflasha7` | `/rootfs` | raw | 16,777,216 |
| `nflasha8` | **`/cp`** | vfat | 67,108,864 |
| `nflasha10` | `/tmp` | vfat | 12,582,912 |
| `nflasha11` | `/log` | vfat | 314,572,800 |
| `nflasha12` | `/cert` | vfat | 41,943,040 |
| `nflasha15` | **`/usr`** | raw | 749,731,840 |
| `nflasha18` | `/lens` | vfat | 20,971,520 |
| `nflasha22` | `/usr/data/ai_dict/usr` | vfat | 68,157,440 |
| `nflasha23` | **`/PMBP`** | prfile | 67,108,864 |
| `nflasha30` | `/usr/data/lut` | vfat | 23,068,672 |

---

## 三、三个关键推论

### 1. `nflasha6` = Jiritsu 的独立分区

`partinf.conf` 注释明写 **Jiritsu 25 MB**，而 `mount.conf` 里挂载点是 **`none`**——不常驻挂载。

这解释了 Jiritsu 文件服务为什么以 `/tmp/jiritsu` 为 base：
**该分区按需挂载到 `/tmp/jiritsu`**，用完可能卸载。这也是 `SET_FILE_PATH` 的 base 目录名的来源。

⇒ 文件服务的根目录是**独立 flash 分区**，不是 `/usr` 的子目录。

### 2. `/setting` 是独立 20 MB vfat，且可写

`nflasha2` → `/setting`。本仓库早前实测已能从该分区读到 `/setting/facedmy.bin`（51,200 字节）。

从 ELF 字符串里挖出的 `/setting` 下真实文件：

| 路径 | 来源 | 性质 |
|---|---|---|
| `/setting/mode/dmode` | `bin/change_mode.sh` | 启动阶段模式（0–12），**不是驱动模式** |
| `/setting/mode/preload` / `tmode` / `cmode` | `libInfraAdjMedia.so` / `libInfraMediaDetect.so` | 启动模式 |
| `/setting/sen/smode` | `appFw.so` / `im.elf` / `libsencore` | Senser 模式 |
| `/setting/.hasp` | `sen.elf` | 授权校验 |
| `/setting/Backup.bin` / `/setting/Backup.bak` | `bk.elf` | **CP/MP 芯片参数备份**（见下） |
| `/setting/defdet.bin` / `psd.bin` / `bt_conf.cnf` / `facerec` | 多处 | 检测/蓝牙/人脸 |
| `/setting/IPTC_001.XMP` | 多处 | IPTC 元数据 |
| `/setting/updater/dat4` | 多处 | 升级器 |

### 3. `/setting/Backup.bin` 不是用户设置 —— 这是本文最重要的一条

固件包里有出厂备份：`0110_backup/SYSIPSX-DSLR/{LAX, ALCINA, DZ}/CX{96701,94701,89501}_*.bin`

| 机型 | 机身代号 | 机型串 | 文件大小 |
|---|---|---|---|
| FX30 | `LAX` | `CX96701_CN2` | **2,253,564** |
| FX3 | `ALCINA` | `CX94701_CN2` | 2,229,740 |
| A6700 | `DZ` | `CX89501_CN1` | 2,351,065 |

**FX30 那份 2,253,564 字节，与 `0x603/5` 读回的 PDT 分毫不差。** 头部 magic 为 `BK4\0`（offset `0x0C`），`0x40` 处有 ASCII `31182_15.2025122501`。

而 `bin/bk.elf`（18,952 字节）的用法字符串是：

```
usage: bk g[ChipID] BackupID      # g = get
       bk r[ChipID] BackupID      # r = read
       bk d[kind] [sid] [BackupID] [mode]
ChipID: c:CP / m:MP / 0:MP / 1:CP
error: inter chip read error:%d
```

⇒ **`/setting/Backup.bin` 是从 CP/MP 芯片读出来的参数备份，`0x603/5` 读的是它的副本。**

### ⚠️ 更正（2026-10-24）：本节原推断已被推翻

~~这解释了困扰很久的一个现象：改 PDT 里的字节，读回确认「已生效」，但相机行为完全不变——因为**固件启动时不从这个文件恢复任何东西**。它不是真值源，只是一个导出品。~~

**原推断错误。** 实机验证：

```bash
python probe_drive_write.py 0x8EF80=0x01 0x91690=0x01
# 拔电池 ≥30 秒冷启动后 → 相机进入连拍且能正常连拍
```

⇒ **PDT（`/setting/Backup.bin`）确实是启动真值源。**
原观察「改了没反应」有两个原因：
1. **只写了一个字段**（`0x8EF80`），配套的 `0x91690` 没写 ⇒ 状态不完整 ⇒ 固件回退；
2. **用关机再开机（热重启）验证**，走 `nflasha5` 暖启动镜像恢复路径，把状态刷掉了。

**必须拔电池 ≥30 秒才是冷启动。** 详见 [`04-dead-ends.md`](04-dead-ends.md) §十三 与
内部文档 `audit/11-驱动模式写入成功-枚举索引映射.md`。

---

## 四、出厂备份可用作偏移体系校验

FX30 出厂文件在新旧偏移上与「单张」快照一致：

| 偏移 | 出厂文件 | 单张快照 |
|---|---|---|
| `0x8EF80` | `00` | `00` |
| `0x91690` | `00` | `00` |

⇒ 偏移体系无误（同一个 PDT 布局）。

出厂 vs 当前快照全量差分：**97,179 字节 / 4.31% / 1,078 个区间**（用户设置累积差异，含头部版本串）。

**但不要用它做跨机型能力对比**：三份备份文件的 4 KB 块集合交集只有 **1.4%**（5 块），被机型校准数据占满。同一张表在 FX30 的偏移在 FX3 上不是同一字段。

---

## 五、此前的错误标签（供对照）

社区流传的 Flash 布局表有 3 处标签错误，本仓库以官方 `partinf.conf` 为准：

| 节点 | 流传说法 | 官方注释 |
|---|---|---|
| `nflasha3` | 数据 | **SYSTEM (Main)** |
| `nflasha8` | 频闪 | **CP Data** |
| `nflasha23` | 空 FAT32 | **PMBP**（`prfile` 类型） |
| `nflasha6` | （漏项） | **Jiritsu 25 MB** |
