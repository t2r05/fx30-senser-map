#!/usr/bin/env python3
"""
jiritsu_probe.py - probe the pFunc=0x40 (Jiritsu/AdjustControl) channel on FX30

READ ONLY. Sends only read-type requests. Never writes files, never calls
writeFile / push / writeBackup / deleteFile.

Purpose: confirm the 0x40 channel is alive and discover which
(category, command) pairs respond, since PROTOCOL.md says Jiritsu uses
pFunc=0x40 (not PMCA's 0xff01 FileControl which returns 128 on this body).

Does NOT call dev.stop() at the end -> camera stays in service mode.
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
from pmca.usb.sony import dump8, dump32le


def enter_service(driver):
    ds = list(listDevices(driver, True))
    senser = [d for d in ds if isinstance(d, SonySenserDevice)]
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]

    if senser and not os.environ.get("ALLOW_REUSE"):
        raise RuntimeError(
            "camera already in service mode but session state may be dirty. "
            "Power-cycle the camera (remove battery 10s), set USB=Mass Storage, reconnect.")
    if senser and os.environ.get("ALLOW_REUSE"):
        print("[*] reusing EXISTING service session (may be dirty)")
        device = senser[0]
    elif msc:
        print("[*] MSC -> authenticating")
        device = msc[0]
        a = SonySenserAuthDevice(device.driver)
        a.start(); a.authenticate()
        print("[*] waiting for service identity...")
        device = None
        for _ in range(40):
            time.sleep(0.5)
            try:
                d2 = list(listDevices(driver, True))
            except Exception:
                d2 = []
            f = [x for x in d2 if isinstance(x, SonySenserDevice)]
            if f:
                device = f[0]
                break
        if device is None:
            raise RuntimeError("service identity did not appear")
    else:
        raise RuntimeError("NO PMCA-COMPATIBLE DEVICE (camera likely in HID mode - replug Type-C)")

    print("[*] authenticating service identity")
    a = SonySenserAuthDevice(device.driver)
    a.start(); a.authenticate()
    return device


def cleanup(device):
    """Send StopSenser so the camera leaves service mode cleanly."""
    try:
        SonySenserAuthDevice(device.driver).stop()
        print("[*] StopSenser sent (clean exit); power-cycle or replug to return to MSC")
    except Exception as e:
        print("[*] stop failed:", e)


def probe(device, category, command, payload=b"", label=""):
    """Send one AdjustControl request; report result code without raising."""
    try:
        hdr = SonySenserCamera.CommandHeader.pack(category=category, command=command)
        res, data = device.sendSenserPacket(
            SonySenserCamera.SONY_PFUNC_AdjustControl, hdr + payload
        )
        print("  cat=0x%04X cmd=0x%02X  res=%s  len=%s  %s" % (
            category, command, res,
            len(data) if data else 0,
            (data[:48].hex() if data else "")), flush=True)
        return res, data
    except Exception as e:
        print("  cat=0x%04X cmd=0x%02X  EXC %s: %s" % (
            category, command, type(e).__name__, e), flush=True)
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
            print("[+] HASP 88 B  [OK] 服务通道可用")
            return True
        print("[!] HASP 长度 %d（期望 88）—— 本次会话可能未完全建立，结果不可信" % n)
        return False
    except Exception as e:  # noqa: BLE001
        print("[!] HASP 读取异常: %r" % (e,))
        return False

def main():
    with importDriver("libusb") as driver:
        device = enter_service(driver)
        cam = SonySenserCamera(device)
        print("[*] readHasp")
        check_hasp(cam)
        print("[*] epIn=%s epOut=%s" % (
            [hex(x) for x in device.driver.epIn],
            [hex(x) for x in device.driver.epOut]))

        print("\n=== A) known-good AdjustControl probe (backup read 0x603/1) ===")
        for bid in (0, 1, 2):
            probe(device, 0x603, 1, dump32le(bid), "backup_read")

        if "--scan" not in sys.argv:
            print("\n[*] scan skipped (pass --scan to enable; it may stress the endpoint)")
            print("[*] done - camera left in service mode (no stop sent)")
            return 0

        print("\n=== B) scan category 0x600..0x60F, command 1..6 (empty payload) ===")
        hits = []
        cmd_max = 6 if "--full" in sys.argv else 3
        for cat in range(0x600, 0x610):
            print("-- category 0x%04X --" % cat, flush=True)
            for cmd in range(1, cmd_max + 1):
                res, data = probe(device, cat, cmd)
                if res == 0:
                    hits.append((cat, cmd, len(data) if data else 0))
        print("\n[*] categories that returned res=0:")
        for h in hits:
            print("    cat=0x%04X cmd=0x%02X len=%d" % h)

        cleanup(device)
        return 0


if __name__ == "__main__":
    sys.exit(main())
