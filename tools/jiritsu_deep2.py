#!/usr/bin/env python3
"""
jiritsu_deep2.py - final sweep of remaining pFunc=0x40 space (READ ONLY)

Stage A: cmd 4..16 x {0x603, 0x604, 0x610, 0x611}   (52 probes)
Stage B: category 0x620..0x62F x cmd 1..3          (48 probes)

Read only. Sends StopSenser at end.
"""
import os
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
CATS = [0x603, 0x604, 0x610, 0x611]


def p(*a):
    print(*a, flush=True)


def enter(driver):
    ds = list(listDevices(driver, True))
    if any(isinstance(d, SonySenserDevice) for d in ds):
        raise RuntimeError("camera already in service mode - power-cycle first")
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]
    if not msc:
        raise RuntimeError("no MSC device - USB=Mass Storage / replug")
    p("[*] MSC found, auth #1")
    dev = msc[0]
    a = SonySenserAuthDevice(dev.driver); a.start(); a.authenticate()
    p("[*] waiting service identity")
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
    p("[*] auth #2")
    a = SonySenserAuthDevice(device.driver); a.start(); a.authenticate()
    return device


def send(device, cat, cmd):
    try:
        hdr = HDR.pack(category=cat, command=cmd)
        res, data = device.sendSenserPacket(PFUNC_ADJ, hdr + b"")
        dlen = len(data) if data else 0
        p("  cat=0x%04X cmd=0x%02X -> res=%s dlen=%d %s" % (
            cat, cmd, res, dlen, (data[:32].hex() if data else "")))
        return res, data
    except Exception as e:
        p("  cat=0x%04X cmd=0x%02X -> EXC %s" % (cat, cmd, type(e).__name__))
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
    hits = []
    with importDriver("libusb") as driver:
        device = enter(driver)
        cam = SonySenserCamera(device)
        check_hasp(cam)

        p("\n=== A) cmd 4..16 x %s ===" % [hex(c) for c in CATS])
        for cat in CATS:
            p("-- category 0x%04X --" % cat)
            for cmd in range(4, 17):
                res, data = send(device, cat, cmd)
                if res == 0:
                    hits.append((cat, cmd, len(data) if data else 0))

        p("\n=== B) category 0x620..0x62F x cmd 1..3 ===")
        for cat in range(0x620, 0x630):
            p("-- category 0x%04X --" % cat)
            for cmd in (1, 2, 3):
                res, data = send(device, cat, cmd)
                if res == 0:
                    hits.append((cat, cmd, len(data) if data else 0))

        p("\n[*] res=0 hits:")
        for h in hits:
            p("    cat=0x%04X cmd=0x%02X len=%d" % h)
        if not hits:
            p("    (none) -> FX30 senser has no file/memory channel in tested space")

        try:
            SonySenserAuthDevice(device.driver).stop()
            p("\n[*] StopSenser sent - power-cycle to return to MSC")
        except Exception as e:
            p("[*] stop failed:", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
