# 探测脚本

> ⚠️ **先读 [`../docs/17-disclaimer-and-boundaries.md`](../docs/17-disclaimer-and-boundaries.md)。**
> 固件研究有变砖风险；脚本分级、危险命令、已知踩坑都在那里。

**默认只读**，但**并非全部只读** —— 见下方风险分级。每个脚本结束时发 `StopSenser` 干净退出。

> **不接相机、只分析固件镜像的脚本在 [`offline/`](offline/)** —— 那里有「设置名称 → 数字 id → `.bss` 地址」
> 的完整链路；**dlopen 载荷的构建与结构校验在 [`payload/`](payload/)**（zig 交叉编译 + ELF 五条铁律自检）。
> 的完整工具链（依赖 `pyelftools` + `capstone`，无需驱动）。

## 风险分级

| 级别 | 脚本 | 说明 |
|---|---|---|
| 🟢 纯静态 | `offline/*`、`payload/check_so.py` | 不接触相机，只读本地文件 |
| 🔵 只读探针 | 除下列外全部脚本 | 只发送**读**请求，不改相机状态 |
| 🟡 含写操作 | `probe_fileid_map.py`、**`probe_drive_write.py`** | `probe_fileid_map.py` **默认只读**；仅当传入 `--delete <file_id>` 或 `--mount` 时**会写相机**。`probe_drive_write.py` **每次运行都会写设置区**（2.25 MB 全量写回） |

⚠️ `probe_fileid_map.py --delete <file_id>` 会依次尝试 `0x4009` / `0x4012` 删除 `/tmp/jiritsu` 下的文件，
成功后自动发 `0x4002`(MOUNT) 重挂并读回验证。**该文件在相机 flash 分区里，跨重启保留**，用完务必清理。

🟡 **`probe_drive_write.py` 会改相机的驱动模式**（写入设置区 `0x8EF80` / `0x91690`）。
每次运行前自动落一份完整快照（`dump/drive_before.bin`）作为回滚材料。
**只写一个字段会被固件回退**（模式是两个字段的组合），详见下方「驱动模式写入」一节。
写入后**必须拔电池 ≥30 秒冷启动** —— 实测**关机再开机（热重启）不生效**，
只有冷启动能让固件加载新值。

但**生效之后**就不需要再拔电池了：关机再开机、进菜单浏览、切视频模式录视频
**都保持连拍**。只有**手动修改驱动模式设置**才会掉回单张。

## 驱动模式写入（`probe_drive_write.py`）

FX30 上**开启隐藏连拍模式**（2026-10-24 实机验证）：

```bash
python probe_drive_write.py --burst
# → 拔电池 ≥30 秒冷启动 → 相机进入连拍，能正常连拍
#   （菜单不显示该选项，手动切换即掉回单张，需要重新跑一次 --burst）
```

回滚单张 / 只看状态：

```bash
python probe_drive_write.py --single     # 回滚成单张
python probe_drive_write.py --probe      # 只看当前状态，不写任何数据
```

其它预设：`--bracket`（包围曝光）、`--timer2` / `--timer5` / `--timer10`（自拍定时）。
**只有 `--burst` 与 `--single` 经实机验证**，其余🟡请自行承担风险。
完整预设表见脚本内 `PRESETS`，上手流程见 [`docs/18`](../docs/18-开启隐藏连拍-最简步骤.md)。

等价原始写法：`probe_drive_write.py 0x8EF80=0x01 0x91690=0x01`。

### 为什么是这两个字节、这两个值

`0x8EF80` / `0x91690` 存的不是属性 id，而是**两张枚举表的 0-based 位置索引**：

| 偏移 | 枚举表 | 表基 vaddr | `0x00` | `0x01` | `0x02` | `0x05` | `0x08` | `0x09` | `0x0C` |
|---|---|---|---|---|---|---|---|---|---|
| `0x8EF80` | `EXTERN_VAL_DRIVE_MODE_*` | `0x41A0550` | SINGLE | **BURST** | BRACKET | RAW_BURST | SINGLE_SELF_2S | BURST_SELF_10S | SINGLE_SELF_5S |
| `0x91690` | `DRIVE_MODE_*` | `0x41A28F0` | 1_IMAGE_SHOOTING | **CONT_SHOOTING** | CONT_SHOOTING_LIMITED | SELF_TIMER | CONT_BRACKET | BRACKET_SINGLE | DRO_ADV_BRACKET |

两字段是**同一设置的两层表示，必须成对写入**。只写一个，固件发现不一致会回退。

| 偏移 | 固件内枚举表 vaddr | 项结构 |
|---|---|---|
| `0x8EF80` | `0x41A0550` | `{char* name; u32 id; u16 code}`，16 字节/项 |
| `0x91690` | `0x41A28F0` | 同上 |

**已知的坑**：

- ⚠️ **首次生效必须拔电池 ≥30 秒冷启动**。实测关机再开机（热重启）**不生效**。
  但生效之后热重启能保持 —— 两个不同阶段，别混为一谈。
- ⚠️ **只有「修改驱动模式设置」才掉回**。进菜单浏览、切视频模式录视频、
  关机重启**都没事**（用户实测）。掉了重新 `--burst` 一次即可。
- ⚠️ **连拍是隐藏模式**：菜单不列出该选项 ⇒ **没法更换拍照模式**。
  想换单张/定时/包围，一选就掉回且回不去（要重刷）；速度档也调不了。
- ⚠️ 本脚本**故意不调用 `stop()`**，会话结束后相机保持在服务身份（`054C:0336`），
  下次运行会自动复用，**不必重新切 USB 模式**。只有拔电池冷启动后才会回到 PTP（`096F`）。
- ⚠️ 写入前请确认电量 ≥ 50%，写失败时恢复出厂设置或写回 `dump/drive_before.bin`。

## 依赖

```bash
git clone https://github.com/ma1co/Sony-PMCA-RE.git pmca-src   # 放在仓库根目录
cd pmca-src && pip install -r requirements.txt
```

脚本按 `../pmca-src` 查找 PMCA 源码。

## 前置

1. 相机 USB 设为**海量存储器**
2. 用 Zadig 给 `054C:0E0E` **和** `054C:0336` 都装 **libusbK**
3. 相机屏幕显示「请检查所连接的设备」属正常
4. 相机电量 ≥ 50%

## 脚本

| 脚本 | 级别 | 用途 |
|---|---|---|
| `probe_sony.ps1` | 🔵 | Windows PnP 枚举，确认 PID / 驱动 / 是否在 MSC 模式 |
| `scsi_probe.py` | 🔵 | 用 Windows 原生 SCSI 直通发 `INQUIRY`，验证存储层（无需换驱动） |
| `extcmd_probe.py` | 🔵 | 用原生 SCSI 发厂商命令 `0x7A`；**记录 Windows USBSTOR 会拦截该命令** |
| `pmca_extcmd_check.py` | 🔵 | 换驱动后在 libusb 下验证 ExtCmd 通道（读机型 / 机器码 / 序列号） |
| `senser_auth.py` | 🔵 | 尝试 Senser 认证，观察是否切到 `054C:0336` |
| `jiritsu_probe.py` | 🔵 | 阶段 A 验证 `0x40` 通道 + 可选命令扫描（`--scan` / `--full`） |
| `jiritsu_deep.py` | 🔵 | `0x604` 特征化、`0x603` 多 payload 试探、`0x610+` 补扫 |
| `jiritsu_deep2.py` | 🔵 | `cmd 4–16` × 命中类别 + `0x620–0x62F` |
| `jiritsu_pdt.py` | 🔵 | 落盘 `0x603 cmd5` 全量备份 + 各子命令返回 |
| `probe_603_ns.py` | 🔵 | `0x603/1` 的 namespace 探测（确认该通道服务哪一族 id） |
| `probe_fileid_map.py` | 🔵/🟡 | 逐槽 `GET_FILE`（`file_id 0..4`），核对 `get_jiritsu_area_filename()` 索引表；`0x4010` 需显式 `--allow-4010`；`--delete` / `--mount` 会写相机 |
| `mem_probe.py` | 🔵 | 验证 MemoryDump（`0xff03`）通道 —— 在 FX30 上返回 128 |
| `probe_drive_write.py` | 🟡 | **写入驱动模式**（`0x8EF80` / `0x91690` 成对写入），开启隐藏连拍；每次运行前自动存回滚快照 |
| `term_probe.py` | 🔵 | 诊断服务模式终端端点 —— 在 FX30 上 `writeTerminal` 超时 |

## 运行示例

```bash
# 确认设备在位
python probe_sony.ps1                       # PowerShell

# 扫描 pFunc=0x40 命令空间（务必加 -u 避免缓冲丢输出）
python -u jiritsu_probe.py --scan

# 落盘完整备份（约 2.25 MB）
python -u jiritsu_pdt.py
```

## 注意

- **健康检查**：所有探针在 `readHasp()` 后会校验长度是否为 **88 字节**。
  不等于 88 说明本次会话未完全建立，**后续所有结果一律不可信** —— 换干净会话重试，别硬着头皮往下走。
- **会话不可复用**：每次都从 MSC 干净起步；脚本结束后相机会落到 HID 模式，需拔插 Type-C 恢复。
- **同一句柄不要既做 SCSI 查询又做认证**：bulk 端点状态会被污染。查询句柄用完即 dispose，认证另开句柄。
- 避开 `0x60F` 区间（会使端点异常）。
- `0x4003`(FORMAT) / `0x4006`(FIRMUP) **不要发** —— 同族平台实测卡死服务。
- `0x611 cmd1` 每次返回约 2 MB，扫描时需留足时间。
- 输出务必用 `python -u`，否则超时被杀时缓冲区内容全丢。
