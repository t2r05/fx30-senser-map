# 会话建立

在 FX30 Ver.6.00 上建立 USB 服务会话的可复现步骤。

---

## 一、驱动准备（关键）

使用 **Zadig**（[zadig.akeo.ie](https://zadig.akeo.ie/)）为**两个**设备安装 **libusbK**：

| 设备 | PID | 何时出现 |
|---|---|---|
| `ILME-FX30` / USB 大容量存储设备 | `054C:0E0E` | 相机 USB 设为「海量存储器」并连接时 |
| `Sony USB Device` | `054C:0336` | 认证成功后、相机切换到服务身份时 |

**两个都要换，只换一个会导致传输失败。**

操作：Zadig → `Options` 勾选 `List All Devices` → 下拉选目标设备 → 驱动选 `libusbK` → `Replace Driver`。

Zadig 的驱动绑定按 VID/PID 持久保存，装一次以后不用重复。

> 换成 libusbK 后相机屏幕会显示「请检查所连接的设备」——**这是预期现象**（libusbK 不主动应答 SCSI 轮询），只要枚举仍是 `054C:0E0E` 就正常。

## 二、相机设置

菜单 → 设置 → USB → USB 连接 → **海量存储器**

## 三、建立会话

```
[1] 枚举 MSC 身份 054C:0E0E
      ↓  claim interface 0（bulk IN/OUT）
[2] Senser 启动：vendor control OUT  bmRequestType=0x43  request=1
                  wValue=0x37FF  wIndex=0xD7AA
[3] 认证（三轮 challenge-response）
      每轮：发逻辑命令 1 → 收 challenge（result 2=SHA-1 分支 / 8=SHA-256）
            发逻辑命令 3 + marker + digest → 收 result 4
      最后：发逻辑命令 5 → 收 result 6 + success byte 1
[4] 相机重新枚举为 054C:0336（新句柄、新 sequence）
[5] 对 0336 再次执行 [2][3] 的认证
[6] 进入命令循环：pFunc=0x10 ProductInfo / 0x40 AdjustControl
[7] 结束：vendor control OUT  request=1  wValue=0xC800  wIndex=0x2855（StopSenser）
```

认证帧：**516 字节大端**（16-bit 补码命令 + 16-bit salt + 512 data），结果解码 `((~cmd)&0xFFFF) - salt`。

digest 输入按身份不同：
- MSC 身份：hash **前 4 字节** challenge
- `0336` 身份：hash **512 字节 challenge + 该轮 key 表条目**

**FX30 6.00 接受 PMCA 内置的密钥表**（`pmca/usb/constants.py` 的 `senserKeysSha1/Sha256`），`authenticate()` 直接通过。

命令包：**12 字节小端头**（`size:32`, `pFunc:16`, `sequence:16`, 4×8bit），`sequence` 从 1 递增。

---

## 四、三条必须遵守的纪律

1. **会话不可复用**。每次操作：从 MSC 干净起步 → 一次运行内做完 → `StopSenser` → 断电/拔插回 MSC。残留会话再认证必然失败。
2. **退出后相机落到 HID 模式**（`054C:096F`），必须拔插 Type-C 或取电池才能回 MSC。
3. **避免 `0x60F` 区间**，它会让端点进入异常状态。

---

## 五、参考实现

- 认证与帧格式：[Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) 的 `pmca/usb/sony.py`（`SonySenserAuthDevice`）、`pmca/usb/crypto.py`
- 协议描述：[YuuLuo/a7c2-service-preload](https://github.com/YuuLuo/a7c2-service-preload) 的 `PROTOCOL.md`
- 备份解析：PMCA `pmca-console.py print_backup <file>`

本仓库的 `tools/` 脚本封装了上述流程，可直接运行。
