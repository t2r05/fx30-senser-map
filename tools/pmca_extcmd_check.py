#!/usr/bin/env python3
"""
pmca_extcmd_check.py - verify Sony ExtCmd channel over libusb (READ ONLY)

Issues only SONY_CMD_DevInfoSender_GetModelInfo = (1,1), which returns
model name / model code / serial. No write, no mode switch.

Run with the PMCA source on sys.path (it lives next to this script under tools/pmca-src).
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pmca-src"))

from pmca.commands.usb import importDriver, getDevice
from pmca.usb.sony import SonyMscExtCmdDevice, SonyExtCmdCamera


def main():
    drv = "libusb" if sys.platform == "win32" else None
    print("driver backend:", drv or "system default")
    with importDriver(drv) as driver:
        dev = getDevice(driver)
        if dev is None:
            print("RESULT: no camera found on libusb backend")
            print("  -> check the device still shows Service=libusb0, and camera is on")
            return
        print("device class:", type(dev).__name__)
        if not isinstance(dev, SonyMscExtCmdDevice):
            print("RESULT: device found but not Sony MSC ExtCmd class ->", type(dev).__name__)
            return

        print("SCSI identify:", dev.getDeviceInfo())

        cam = SonyExtCmdCamera(dev)
        info = cam.getCameraInfo()
        print("")
        print("=== CAMERA INFO (read only) ===")
        print("  model      :", info.modelName)
        print("  model code :", info.modelCode)
        print("  serial     :", info.serial)
        print("  plist len  :", len(info.plist) if hasattr(info, "plistData") else "n/a")
        print("")
        print("RESULT: ExtCmd channel WORKS over libusb -> service mode is reachable")


if __name__ == "__main__":
    main()
