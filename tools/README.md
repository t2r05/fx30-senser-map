# 探测脚本

**全部只读**。脚本只发送读请求，不写任何数据。每个脚本结束时发 `StopSenser` 干净退出。

> **不接相机、只分析固件镜像的脚本在 [`offline/`](offline/)** —— 那里有「设置名称 → 数字 id → `.bss` 地址」
> 的完整工具链（依赖 `pyelftools` + `capstone`，无需驱动）。

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

## 脚本

| 脚本 | 用途 |
|---|---|
| `probe_sony.ps1` | Windows PnP 枚举，确认 PID / 驱动 / 是否在 MSC 模式 |
| `scsi_probe.py` | 用 Windows 原生 SCSI 直通发 `INQUIRY`，验证存储层（无需换驱动） |
| `extcmd_probe.py` | 用原生 SCSI 发厂商命令 `0x7A`；**记录 Windows USBSTOR 会拦截该命令** |
| `pmca_extcmd_check.py` | 换驱动后在 libusb 下验证 ExtCmd 通道（读机型 / 机器码 / 序列号） |
| `senser_auth.py` | 尝试 Senser 认证，观察是否切到 `054C:0336` |
| `jiritsu_probe.py` | 阶段 A 验证 `0x40` 通道 + 可选命令扫描（`--scan` / `--full`） |
| `jiritsu_deep.py` | `0x604` 特征化、`0x603` 多 payload 试探、`0x610+` 补扫 |
| `jiritsu_deep2.py` | `cmd 4–16` × 命中类别 + `0x620–0x62F` |
| `jiritsu_pdt.py` | 落盘 `0x603 cmd5` 全量备份 + 各子命令返回 |
| `probe_fileid_map.py` | 逐槽 `GET_FILE`（`file_id 0..4`），核对 `get_jiritsu_area_filename()` 索引表；`0x4010` 需显式 `--allow-4010` |
| `mem_probe.py` | 验证 MemoryDump（`0xff03`）通道 —— 在 FX30 上返回 128 |
| `term_probe.py` | 诊断服务模式终端端点 —— 在 FX30 上 `writeTerminal` 超时 |

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

- **会话不可复用**：每次都从 MSC 干净起步；脚本结束后相机会落到 HID 模式，需拔插 Type-C 恢复。
- 避开 `0x60F` 区间（会使端点异常）。
- `0x611 cmd1` 每次返回约 2 MB，扫描时需留足时间。
- 输出务必用 `python -u`，否则超时被杀时缓冲区内容全丢。
