#!/usr/bin/env python3
"""
senser_auth.py - attempt Sony service-mode (senser) authentication on FX30

INFORMATIONAL ONLY: this does not read or write firmware.
It asks the camera to switch into service mode, then reports whether the
service-mode device (PID 0x0336) appears.

If authentication is rejected, power-cycle the camera to return to normal.
"""
import sys
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pmca-src"))

from pmca.commands.usb import importDriver, getDevice, listDevices
from pmca.usb.sony import (
    SonyMscExtCmdDevice, SonySenserAuthDevice, SonySenserDevice,
)


def main():
    drv = "libusb" if sys.platform == "win32" else None
    with importDriver(drv) as driver:
        dev = getDevice(driver)
        if dev is None:
            print("RESULT: device not found")
            return 2
        print("current device:", type(dev).__name__)

        if not isinstance(dev, SonyMscExtCmdDevice):
            print("RESULT: not in MSC mode, abort")
            return 2

        print("--- step 1: vendorRequest StartSenser (1, 0x37ff, 0xd7aa) ---")
        auth = SonySenserAuthDevice(dev.driver)
        auth.start()
        print("    sent")

        print("--- step 2: authenticate() with built-in senserKeys ---")
        try:
            auth.authenticate()
            print("    AUTH OK")
        except Exception as e:
            print("    AUTH FAILED: %s: %s" % (type(e).__name__, e))
            print("RESULT: senserKeys not accepted by this body")
            return 3

        print("--- step 3: waiting for service-mode device (PID 0x0336) ---")
        for i in range(24):
            time.sleep(0.5)
            try:
                devs = list(listDevices(driver, True))
            except Exception:
                devs = []
            names = [type(d).__name__ for d in devs]
            print("    t=%4.1fs  see=%s" % ((i + 1) * 0.5, names or "-"))
            for d in devs:
                if isinstance(d, SonySenserDevice):
                    print("")
                    print("*** SENSER MODE REACHED ***")
                    print("RESULT: service mode is OPEN on this body")
                    return 0
        print("")
        print("RESULT: no service-mode device appeared (timeout)")
        return 4


if __name__ == "__main__":
    sys.exit(main())
