#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_603_ns.py — 0x603/1 的 payload 首字节语义探测（纯只读）

===== 完全只读，不写任何东西 =====

## 要解决的问题

已知 `0x603/1` 的 payload 是 `[0x01] + u32le(id)`：

    0x50000 一族  -> res=0, len=4       （能读）
    0x0000        -> res=129            （实测）
    0x4FFFF       -> res=129            （实测）
    0x0272 / 0x0273 / 0x04B6 -> res=129 （实测，见 probe_id_range.log / probe_backup_read.log）
    0x02AF / 0x04B8（BKID 注册表 id）-> 未测过

**关键疑问**：`0x02AF` / `0x04B8` 这些 BKID id 到底走不走这条通道？
如果走，那 payload 首字节可能不是常量 `0x01`，而是 **namespace**。

## 本脚本做什么

固定 id 集合 × payload 首字节 0x00~0x05，做一个小矩阵，只读：

    payload = [ns] + u32le(id)

同时对每个 ns 用 `0x50000` 做对照（它已知能读），
用来判断「首字节变了之后通道是否还工作」。

## 判读表（只看一致性的变化）

| 现象 | 含义 |
|---|---|
| ns=0x01 时 0x50000 正常、0x04B8 返回 129 | 首字节无害，0x04B8 在这个 ns 下确实无效 |
| 某个 ns 下 0x50000 仍正常、0x04B8 变成 0/其他 | **找到了 BKID id 的 namespace** |
| 所有 ns 下 0x50000 都变坏 | 首字节就是写死的，不是 namespace |
| 所有 ns 下 0x04B8 都 129 | 这条通道压根不服务 BKID id，换方向 |

## 用法

    python probe_603_ns.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools", "pmca-src"))

from pmca.commands.usb import importDriver, listDevices  # noqa: E402
from pmca.usb.sony import (  # noqa: E402
    SonyMscExtCmdDevice, SonySenserAuthDevice, SonySenserDevice,
    SonySenserCamera,
)

PF_ADJ = SonySenserCamera.SONY_PFUNC_AdjustControl
HDR = SonySenserCamera.CommandHeader
CAT = 0x1001
CMD_SETTING = 0x603
SUB_READ = 0x01

# 探测 id：前两个是 BKID 注册表 id（目标），后两个是已知能读的对照
ID_SET = [
    (0x50000, "对照 · 已知能读"),
    (0x04B8, "BKID cont_shooting ★"),
    (0x02AF, "BKID menu_drive_mode ★"),
    (0x0272, "BKID DRIVE_MODE_1_IMAGE_SHOOTING"),
    (0x0000, "对照 · 已知 129"),
]
NS_SET = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x10, 0xFF]


def p(*a):
    print(*a, flush=True)


def enter(driver):
    """MSC -> 认证 -> 服务身份 -> 再认证（与 probe_bkid_read.py 同流程）"""
    ds = list(listDevices(driver, True))
    senser = [d for d in ds if isinstance(d, SonySenserDevice)]
    if senser:
        raise RuntimeError(
            "相机已在服务模式，会话状态可能脏。"
            "请拔电池 10 秒冷启动 -> USB 选「存储」-> 重插。")
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]
    if not msc:
        raise RuntimeError("没找到 PMCA 兼容设备（相机可能在 HID 模式，重插 Type-C）")

    p("[*] 认证 #1")
    a = SonySenserAuthDevice(msc[0].driver)
    a.start()
    a.authenticate()

    p("[*] 等服务身份 054C:0336 ...")
    dev = None
    for _ in range(50):
        time.sleep(0.5)
        try:
            d2 = list(listDevices(driver, True))
        except Exception:
            d2 = []
        f = [x for x in d2 if isinstance(x, SonySenserDevice)]
        if f:
            dev = f[0]
            break
    if dev is None:
        raise RuntimeError("服务身份未出现（20 秒）")

    p("[*] 认证 #2")
    a = SonySenserAuthDevice(dev.driver)
    a.start()
    a.authenticate()
    return dev


def send(dev, payload):
    h = HDR.pack(category=CAT, command=CMD_SETTING)
    res, data = dev.sendSenserPacket(PF_ADJ, h + payload)
    return res, (data or b"")


def check_hasp(dev):
    """HASP 必须是 88 字节，否则本次会话不可信"""
    try:
        hasp = SonySenserCamera(dev).readHasp()
        n = len(hasp) if hasp else 0
        if n == 88:
            p("[+] HASP 88 B  OK")
            return True
        p("[!] HASP %d B（期望 88）-> 会话可能不完整，结果打折扣看" % n)
        return False
    except Exception as e:  # noqa: BLE001
        p("[!] HASP 异常: %r" % (e,))
        return False


def main():
    p("=" * 74)
    p("0x603/1 payload 首字节语义探测（纯只读）")
    p("=" * 74)

    rows = []
    try:
        with importDriver("libusb") as driver:
            dev = enter(driver)
            hasp_ok = check_hasp(dev)

            p("\n[-] GET_VERSION 0x400D（版本记录）")
            h = HDR.pack(category=CAT, command=0x400D)
            res, data = dev.sendSenserPacket(PF_ADJ, h)
            p("    res=%s len=%d  hex=%s" % (res, len(data), data[:16].hex(" ")))

            p("\n[*] 矩阵：ns x id = %d x %d = %d 次只读请求"
              % (len(NS_SET), len(ID_SET), len(NS_SET) * len(ID_SET)))
            p("")
            p("  %-6s %-10s %-28s %-5s %-5s %s" % ("ns", "id", "说明", "res", "len", "data"))
            p("  " + "-" * 90)

            for ns in NS_SET:
                for rid, note in ID_SET:
                    payload = bytes([ns]) + rid.to_bytes(4, "little")
                    try:
                        res, data = send(dev, payload)
                    except Exception as e:  # noqa: BLE001
                        p("  %#04x  %#010x %-28s EXC   %s" % (ns, rid, note, repr(e)))
                        continue
                    rows.append((ns, rid, res, len(data), data[:8].hex(" ")))
                    p("  %#04x  %#010x %-28s %-5s %-5d %s"
                      % (ns, rid, note, res, len(data), data[:8].hex(" ")))
                    time.sleep(0.03)
                p("")

            p("=" * 74)
            p("判读提示")
            p("=" * 74)
            p("1. 先看 ns=0x01 这一组：0x50000 应 res=0 len=4（说明基线和历史一致）")
            p("2. 再看其它 ns 下 0x50000 是否也正常 —— 不正常说明首字节不能改")
            p("3. 最后找：哪个 ns 下 0x04B8 / 0x02AF 从 129 变成 0（或非 129）")
            p("4. 全部 ns 下 0x04B8 都是 129 -> 这条通道不服务 BKID id，换方向")
            if not hasp_ok:
                p("\n⚠️ 本次 HASP 未达 88 B，上述结果可靠性下降")
    except Exception as e:  # noqa: BLE001
        p("\n[FAIL] %r" % (e,))
        return 1

    p("\n完成，共 %d 次只读请求。" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
