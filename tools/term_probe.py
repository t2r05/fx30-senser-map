#!/usr/bin/env python3
"""
term_probe.py - diagnose terminal endpoint availability on FX30 service mode

READ ONLY: only sends terminal-enable packets and empty/benign probes.

Steps:
 1. verify both terminal-enable packets succeed
 2. identify epIn/epOut lists
 3. try a write on each OUT endpoint index, report which one accepts
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pmca-src"))

from pmca.commands.usb import importDriver, listDevices
from pmca.usb.sony import (
    SonySenserAuthDevice, SonySenserDevice, SonySenserCamera,
)
from pmca.util import *
from pmca.usb.sony import dump8


def main():
    with importDriver("libusb") as driver:
        ds = list(listDevices(driver, True))
        senser = [d for d in ds if isinstance(d, SonySenserDevice)]
        if not senser:
            print("no senser device; camera must be in service mode")
            return 2
        device = senser[0]
        d = device.driver

        print("epIn  =", [hex(x) for x in d.epIn])
        print("epOut =", [hex(x) for x in d.epOut])

        auth = SonySenserAuthDevice(d)
        auth.start(); auth.authenticate()
        cam = SonySenserCamera(device)
        try:
            hasp = cam.readHasp()
            n = len(hasp) if hasp else 0
            if n == 88:
                print("[+] HASP 88 B  [OK] 服务通道可用")
            else:
                print("[!] HASP 长度 %d（期望 88）—— 会话可能未完全建立" % n)
        except Exception as e:  # noqa: BLE001
            print("[!] HASP 读取异常: %r" % (e,))

        print("\n-- terminal enable packet 1 (ProductInfo TERM_CHANGE) --")
        try:
            data = cam._sendProductInfoPacket(*cam.SONY_PRODUCT_INFO_TERM_CHANGE, dump8(1))
            print("   OK, resp:", data[:16].hex() if data else "(empty)")
        except Exception as e:
            print("   FAIL:", type(e).__name__, e)

        print("-- terminal enable packet 2 (AdjustControl SENSER_TERM_MODE) --")
        try:
            data = cam._sendAdjustControlPacket(*cam.SONY_ADJUST_SENSER_TERM_MODE, dump8(2))
            print("   OK, resp:", data[:16].hex() if data else "(empty)")
        except Exception as e:
            print("   FAIL:", type(e).__name__, e)

        time.sleep(2.0)

        for idx in range(len(d.epOut)):
            for attempt in (1,):
                try:
                    d.write(b"\r\n", ep=idx)
                    print("   write ep[%d]=0x%02x OK" % (idx, d.epOut[idx]))
                except Exception as e:
                    print("   write ep[%d]=0x%02x FAIL: %s" % (idx, d.epOut[idx], type(e).__name__))

        for idx in range(len(d.epIn)):
            try:
                data = d.read(0x40, ep=idx, timeout=800)
                print("   read  ep[%d]=0x%02x OK len=%d %s" % (
                    idx, d.epIn[idx], len(data), data[:32].hex()))
            except Exception as e:
                print("   read  ep[%d]=0x%02x FAIL: %s" % (idx, d.epIn[idx], type(e).__name__))

        return 0


if __name__ == "__main__":
    sys.exit(main())
