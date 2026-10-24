#!/usr/bin/env python3
"""
jiritsu_deep.py - deeper probe of pFunc=0x40 command space on FX30 (READ ONLY)

Stage A: characterise 0x604 cmd1/2/3  (repeat x3 to see if data is stateful)
Stage B: 0x603 cmd1/cmd2 with various payload shapes (path vs id vs empty)
Stage C: scan 0x610..0x61F x cmd1..3

Never writes. Sends StopSenser at the end.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pmca-src"))

from pmca.commands.usb import importDriver, listDevices
from pmca.usb.sony import (
    SonyMscExtCmdDevice, SonySenserAuthDevice, SonySenserDevice,
    SonySenserCamera,
)

PFUNC_ADJ = SonySenserCamera.SONY_PFUNC_AdjustControl
HDR = SonySenserCamera.CommandHeader


def p(*a):
    print(*a, flush=True)


def enter(driver):
    ds = list(listDevices(driver, True))
    senser = [d for d in ds if isinstance(d, SonySenserDevice)]
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]
    if senser:
        raise RuntimeError("camera already in service mode - power-cycle first")
    if not msc:
        raise RuntimeError("no MSC device - set USB=Mass Storage / replug")
    p("[*] MSC found, authenticating")
    dev = msc[0]
    a = SonySenserAuthDevice(dev.driver); a.start(); a.authenticate()
    p("[*] waiting for service identity")
    device = None
    for _ in range(40):
        time.sleep(0.5)
        try:
            d2 = list(listDevices(driver, True))
        except Exception:
            d2 = []
        f = [x for x in d2 if isinstance(x, SonySenserDevice)]
        if f:
            device = f[0]; break
    if device is None:
        raise RuntimeError("service identity not found")
    p("[*] authenticating service identity")
    a = SonySenserAuthDevice(device.driver); a.start(); a.authenticate()
    return device


def send(device, cat, cmd, payload=b"", label=""):
    try:
        hdr = HDR.pack(category=cat, command=cmd)
        res, data = device.sendSenserPacket(PFUNC_ADJ, hdr + payload)
        hexs = data.hex() if data else ""
        p("  [%s] cat=0x%04X cmd=0x%02X plen=%d -> res=%s dlen=%s %s"
          % (label, cat, cmd, len(payload), res, len(data) if data else 0, hexs[:80]))
        return res, data
    except Exception as e:
        p("  [%s] cat=0x%04X cmd=0x%02X plen=%d -> EXC %s"
          % (label, cat, cmd, len(payload), type(e).__name__))
        return None, None



def check_hasp(cam):
    """HASP 服务令牌健康检查 —— 长度必须是 88 字节。

    为什么要这个：早前日志只写「HASP 完成」，不记长度 —— 返回 0 字节也会
    被当成「完成」，等于没有验收标准。按 Sony 定义，HASP 令牌固定 88 字节
    （pmca: SONY_PRODUCT_INFO_READ_HASP = (0, 0x001f)，走 pFunc 0x10），
    长度不对就说明本次会话没真正建立，后续所有读取结果一律不可信。
    """
    try:
        hasp = cam.readHasp()
        n = len(hasp) if hasp else 0
        if n == 88:
            p("[+] HASP 88 B  [OK] 服务通道可用")
            return True
        p("[!] HASP 长度 %d（期望 88）—— 本次会话可能未完全建立，结果不可信" % n)
        return False
    except Exception as e:  # noqa: BLE001
        p("[!] HASP 读取异常: %r" % (e,))
        return False

def main():
    with importDriver("libusb") as driver:
        device = enter(driver)
        cam = SonySenserCamera(device)
        check_hasp(cam)

        p("\n=== A) 0x604 characterisation (3 repeats each) ===")
        for cmd in (1, 2, 3):
            for i in range(3):
                send(device, 0x604, cmd, b"", "604/%d#%d" % (cmd, i + 1))

        p("\n=== B) 0x603 with payload shapes ===")
        shapes = [
            ("empty", b""),
            ("u32_0", struct.pack("<I", 0)),
            ("u32_1", struct.pack("<I", 1)),
            ("ascii_0", b"0\x00\x00\x00"),
            ("path", b"/usr/lib/appFw.so\x00"),
            ("name", b"appFw.so\x00"),
            ("zeros16", b"\x00" * 16),
        ]
        for cmd in (1, 2):
            for name, pl in shapes:
                send(device, 0x603, cmd, pl, "603/%d:%s" % (cmd, name))

        p("\n=== C) scan 0x610..0x61F x cmd1..3 ===")
        hits = []
        for cat in range(0x610, 0x620):
            p("-- category 0x%04X --" % cat)
            for cmd in (1, 2, 3):
                res, data = send(device, cat, cmd)
                if res == 0:
                    hits.append((cat, cmd, len(data) if data else 0))

        p("\n[*] res=0 hits in 0x610..0x61F:")
        for h in hits:
            p("    cat=0x%04X cmd=0x%02X len=%d" % h)
        if not hits:
            p("    (none)")

        try:
            SonySenserAuthDevice(device.driver).stop()
            p("\n[*] StopSenser sent (clean exit) - power-cycle to return to MSC")
        except Exception as e:
            p("[*] stop failed:", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
