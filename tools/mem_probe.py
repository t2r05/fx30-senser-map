#!/usr/bin/env python3
"""
mem_probe.py - verify MemoryDump (pFunc=0xff03) channel on FX30 (READ ONLY)

Tries to read BootROM at 0xffff0000 (24KB) - the address documented in
ILCE-7M4-RE. If this works, we can dump firmware by address and skip the
whole "find the file command" problem.

Read only. No writes. Sends StopSenser at the end.
"""
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pmca-src"))
OUT = os.path.join(HERE, "dump")

from pmca.commands.usb import importDriver, listDevices
from pmca.usb.sony import (
    SonyMscExtCmdDevice, SonySenserAuthDevice, SonySenserDevice,
    SonySenserCamera,
)


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


def try_dump(cam, base, size, label):
    buf = io.BytesIO()
    try:
        cam.readMemory(base, size, buf)
        data = buf.getvalue()
        p("  %-28s base=0x%08X size=0x%X -> OK, got %d bytes" % (
            label, base, size, len(data)))
        if data:
            p("      head: %s" % data[:48].hex())
            path = os.path.join(OUT, "mem_%08X.bin" % base)
            with open(path, "wb") as f:
                f.write(data)
            p("      saved -> %s" % path)
        return data
    except Exception as e:
        p("  %-28s base=0x%08X size=0x%X -> EXC %s: %s" % (
            label, base, size, type(e).__name__, e))
        return None


def main():
    os.makedirs(OUT, exist_ok=True)
    with importDriver("libusb") as driver:
        device = enter(driver)
        cam = SonySenserCamera(device)
        cam.readHasp()

        p("\n=== MemoryDump (pFunc=0xff03) probes ===")
        # BootROM: the documented address
        ok = try_dump(cam, 0xFFFF0000, 0x6000, "BootROM")
        if ok is None:
            p("\n[!] 0xffff0000 failed, trying a few more bases to see if it is address-specific")
            for base, size, label in [
                (0x00000000, 0x1000, "addr0"),
                (0x400000000, 0x1000, "RAM 0x400000000"),
                (0xFE000000, 0x1000, "eSRAM 0xfe000000"),
            ]:
                try_dump(cam, base, size, label)

        try:
            SonySenserAuthDevice(device.driver).stop()
            p("\n[*] StopSenser sent - power-cycle to return to MSC")
        except Exception as e:
            p("[*] stop failed:", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
