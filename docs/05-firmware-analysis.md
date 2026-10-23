# 固件分析与 BKID 定位

本文记录 FX30（Ver.6.00）官方固件的解密、解包，以及从 `appFw.so` 中定位设置项 ID（BKID）的方法。

**不含固件二进制、不含完整 BKID 表。** 只给出方法与关键结论，供有能力自行解包者复现。

---

## 一、官方固件是可解密的

此前（含本仓库早期判断）普遍认为 CXD90057 / BIONZ XR 的固件无法解开。**这个判断是错的。**

社区研究者 DavidBuchanan314 已提取全部 CXD90057 设备的密钥，见 `ma1co/fwtool.py` **PR #52**。

**密钥派生方式**（来自 PR 讨论）：

```
从 MMIO 读取 EFuse：
  1024 字节 @ PA 0xffffb800
    32 字节 @ PA 0xf340f000
→ 这些 eFuse 在所有 CXD90057 设备上相同
```

共 **13 把密钥**，由固件派生代码中的索引选择；已观察到 **k0** 与 **k8**。这也解释了索尼的"必须先升 x 再升 y"——升级会改变密钥索引。

已测试可用机型（PR #52 列出）：`ILCE-7M4` `ILCE-7SM3` `ILCE-1` `ILCE-1M2` `ILCE-6700` `ILCE-7CM2` `ILCE-7RM5` `ILME-FX2` `ILME-FX3` `ILME-FX6` `ILX-LR1`。

**FX30 不在该列表内，但实测可以解开。**

---

## 二、解包流程

```bash
# 1. 工具 + PR
git clone https://github.com/ma1co/fwtool.py
curl -L https://github.com/ma1co/fwtool.py/pull/52.patch -o pr52.patch
cd fwtool.py && patch -p1 < ../pr52.patch

# 2. 固件（索尼官网，走存储卡方式）
#    BODYDATA.DAT，约 906 MB
#    魔数 89 55 46 55 0d 0a 1a 0a  ("\x89UFU")

# 3. 解密 + 解包
python fwtool.py unpack -f BODYDATA.DAT -o out
```

**实测耗时：81 秒。**

产物结构：

```
out/firmware.tar_unpacked/
  0100_config    0101_config_sum
  0110_backup    0111_backup_sum      ← 设置备份母版
  0300_partconf  0301_partconf_sum    ← 分区表
  0700_part_image/
      dev/nflasha3, nflasha7, nflasha8
      dev/nflasha15_unpacked/         ← 主要文件系统
  0800_appli     0801_appli_sum
  0750_nor_loader
```

目标文件：

```
0700_part_image/dev/nflasha15_unpacked/lib/appFw.so
  79,032,104 字节 (75.4 MB)，AArch64 共享库
```

---

## 三、从 appFw.so 定位 BKID

### 3.1 先找字符串

`appFw.so` 的 `.rodata` 里有完整的设置项名字表：

```
0x3BD195F   BKID_APP_setting_drive_mode_cont_shooting
0x3BD19B6   BKID_APP_setting_drive_mode_cont_shooting_limited
0x3BD1A1D   BKID_APP_setting_drive_mode_single_burst_shooting
0x3BD1A84   BKID_APP_setting_drive_mode_self_timer
...
```

同一区域还有 `drive_mode_self_portrait` / `cont_self_timer` / `cont_bracket` / `bracket_single` / `white_balance_bracket` / `dro_adv_bracket`。

### 3.2 找引用这些字符串的表

搜索某个字符串**虚拟地址**作为 `u64` 出现的位置，会在 `.data.rel.ro` 段找到表结构：

```
每条 16 字节：{ u64 name_ptr, u32 id, u32 extra }

0x3BD1939  BKID_APP_MR_setting_shooting_mode_scn              → id 1207
0x3BD195F  BKID_APP_setting_drive_mode_cont_shooting          → id 1208
0x3BD1989  BKID_APP_MR_setting_drive_mode_cont_shooting       → id 1209
0x3BD19B6  BKID_APP_setting_drive_mode_cont_shooting_limited  → id 1210
```

**注意地址换算**：`.data.rel.ro` 段的 `sh_addr - sh_offset = 0x10000`，所以虚拟地址 `0x414F000` 对应文件偏移 `0x413F000`。两者别混。

### 3.3 驱动模式的完整编号

| BKID | 名称 |
|---|---|
| 1206 | shooting_mode_scn |
| **1208** | **drive_mode_cont_shooting（连拍）** |
| 1209 | MR_setting_drive_mode_cont_shooting |
| **1210** | **drive_mode_cont_shooting_limited（连拍·限制版）** |
| 1211 | MR_..._limited |
| 1212 | drive_mode_single_burst_shooting |
| 1214 | drive_mode_self_timer |
| 1216 | drive_mode_self_portrait |
| 1218 | drive_mode_cont_self_timer |
| 1220 | drive_mode_cont_bracket |
| 1222 | drive_mode_bracket_single |
| 1224 | drive_mode_white_balance_bracket |
| 1226 | drive_mode_dro_adv_bracket |

**表内共 768 条 BKID 映射**（覆盖所有 `BKID_APP_setting_*`）。

### 3.4 连拍的枚举值也在固件里

```
VAL_setting_drive_mode_cont_shooting_DRIVE_MODE_CONT_SHOOTING_OPTION_HI_PLUS
VAL_setting_drive_mode_cont_shooting_DRIVE_MODE_CONT_SHOOTING_OPTION_HI
VAL_setting_drive_mode_cont_shooting_DRIVE_MODE_CONT_SHOOTING_OPTION_MID
VAL_setting_drive_mode_cont_shooting_DRIVE_MODE_CONT_SHOOTING_OPTION_LOW
VAL_setting_drive_mode_cont_shooting_PRM_ALL
```

**四档选项完整存在**，与 FX3 的 Hi+/Hi/Mid/Lo 结构对应。

> 附带结论：`customFps_Elec_*`（四档速度参数）在 FX30 固件中 **0 命中** —— FX30 没有独立的连拍速度调节项。

---

## 四、读写链路的反汇编结果

`libbackup.so` 导出了一组 C 接口：

```
Backup_read        Backup_read_4Byte     Backup_read_8Byte
Backup_read_setting_attr                 Backup_read_multi
Backup_write       Backup_write_vsize    Backup_write_setting_attr
Backup_get_attribute                     Backup_get_datasize
```

反汇编所有 `Backup_*` 函数，发现它们统一调用 `libbackup.so` 的 **PLT 第 5 项**（`0x1530` = `osal_snd_msg`），并传入：

```
w1 = 0x3E014D    ← 模块 ID（mov w1,#0x14d / movk w1,#0x3e,lsl#16）
w2 = 操作码
w3 = 类型
```

**操作码对照：**

| 函数 | 操作码 |
|---|---|
| `Backup_get_attribute` | 2 |
| `Backup_read_4Byte` | 4 |
| **`Backup_read_setting_attr`** | **0x1B** |
| **`Backup_write_setting_attr`** | **0x1D** |

**链路：**

```
libbackup.so  →  IPC {0x3E014D, opcode}  →  bkdmn 守护进程  →  ???
```

最后一段（bkdmn → USB）在 FX30 上没有暴露。

### 旁证：相机内的命令行工具

`bin/bk.elf` 的 usage 字符串完整暴露了本地接口：

```
usage: bk command [command-option-and-arguments]
  bk g [ChipID] BackupID              → get data attribute
  bk r [ChipID] BackupID              → read backup data
  bk x BackupID                       → read setting backup data
  bk z num BackupID Data              → write setting backup data
  bk y [ChipID] num BackupID          → list backup data
  ChipID: c:CP / m:MP / 0:MP / 1:CP
  BackupID (HEX)
```

**注意**：这是相机内部命令行接口，不是 USB 协议。把它当 USB 命令格式去试会一直返回 129。

---

## 五、两个容易走错的方向

| 误区 | 真相 |
|---|---|
| `libInfraExtBackupCommunicator.so` 是设置读写通道 | 它是**远程备份通信**（网络传照片）。ExtCmd 模块 4 支持的命令只有 `[1,6,7,8,9]`（表在 `.data` 段 0x151E8），无 ReadBackup |
| `share/app/area_check_data.dat` 是 BKID 映射表 | 是 **UI 字符串表**（内容全是 `STRID_*`），与 BKID 无关 |

---

## 六、这些结论能做什么

固件解开之后，**离线分析的上限就打开了**：

- 任意设置项的 BKID 都能查（768 条表）
- 任意功能的枚举值都能确认是否存在
- 任何代码路径都能反汇编确认

但**最终写入设备**仍需要一条能改内存或改文件的通道。**该通道尚未验证**（早期「FX30 不存在此通道」的判断源于一次格式错误的 FileControl 调用，已撤回，见 [04-dead-ends.md](04-dead-ends.md) 与 [07-jiritsu-breakthrough.md](07-jiritsu-breakthrough.md)）。

**固件已无需 Pico 即可获得**：官方 `BODYDATA.DAT` 可直接用 fwtool（PR #52）解包，本文所有方法已在本机离线跑通。
