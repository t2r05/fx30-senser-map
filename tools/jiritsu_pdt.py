#!/usr/bin/env python3
"""
jiritsu_pdt.py - capture the large PDT payload and 0x604 subcommands (READ ONLY)

Saves under dump/:
  0x603_cmd05.bin  (~2.25 MB preset data)
  0x603_cmd06.bin
  0x603_cmd0F.bin
  0x603_cmd10.bin
  0x604_cmd06..10.bin

Read only. Sends StopSenser at the end.
"""
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

PFUNC_ADJ = SonySenserCamera.SONY_PFUNC_AdjustControl
HDR = SonySenserCamera.CommandHeader

TARGETS = [
    (0x603, 0x05, "0x603_cmd05.bin"),
    (0x603, 0x06, "0x603_cmd06.bin"),
    (0x603, 0x0F, "0x603_cmd0F.bin"),
    (0x603, 0x10, "0x603_cmd10.bin"),
    (0x604, 0x06, "0x604_cmd06.bin"),
    (0x604, 0x07, "0x604_cmd07.bin"),
    (0x604, 0x08, "0x604_cmd08.bin"),
    (0x604, 0x09, "0x604_cmd09.bin"),
    (0x604, 0x10, "0x604_cmd10.bin"),
]


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


def main():
    os.makedirs(OUT, exist_ok=True)
    with importDriver("libusb") as driver:
        device = enter(driver)
        cam = SonySenserCamera(device)
        cam.readHasp()

        p("\n=== capturing ===")
        for cat, cmd, fn in TARGETS:
            try:
                hdr = HDR.pack(category=cat, command=cmd)
                res, data = device.sendSenserPacket(PFUNC_ADJ, hdr + b"")
                dlen = len(data) if data else 0
                p("  cat=0x%04X cmd=0x%02X -> res=%s dlen=%d" % (cat, cmd, res, dlen))
                if res == 0 and data:
                    path = os.path.join(OUT, fn)
                    with open(path, "wb") as f:
                        f.write(data)
                    p("      saved %s  head=%s" % (fn, data[:32].hex()))
            except Exception as e:
                p("  cat=0x%04X cmd=0x%02X -> EXC %s" % (cat, cmd, type(e).__name__))

        try:
            SonySenserAuthDevice(device.driver).stop()
            p("\n[*] StopSenser sent - power-cycle to return to MSC")
        except Exception as e:
            p("[*] stop failed:", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
