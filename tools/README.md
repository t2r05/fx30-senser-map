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
| 🟡 含写操作 | `probe_fileid_map.py` | **默认只读**；仅当传入 `--delete <file_id>` 或 `--mount` 时**会写相机** |

⚠️ `probe_fileid_map.py --delete <file_id>` 会依次尝试 `0x4009` / `0x4012` 删除 `/tmp/jiritsu` 下的文件，
成功后自动发 `0x4002`(MOUNT) 重挂并读回验证。**该文件在相机 flash 分区里，跨重启保留**，用完务必清理。

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
