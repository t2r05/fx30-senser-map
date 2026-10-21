#!/usr/bin/env python3
"""
scsi_probe.py - Windows native SCSI pass-through probe for Sony camera (READ ONLY)

Purpose: verify that the camera's mass-storage SCSI channel accepts vendor
commands, WITHOUT replacing any USB driver (no Zadig / no libusb needed).

Stage 1 (this script): standard INQUIRY (0x12) only. Pure read, zero mutation.

Usage:
    python scsi_probe.py            # probe all candidate physical drives
    python scsi_probe.py 7          # probe specific drive number

Reference: PMCA-RE pmca/usb/__init__.py MscDevice (MSC_OC_INQUIRY = 0x12,
MSC_OC_ExtCmd = 0x7A, CDB built as 0x7A + cmd(4B LE) + 7 zero bytes).
"""
import ctypes
import ctypes.wintypes as wt
import sys

IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
SCSI_IOCTL_DATA_OUT = 0
SCSI_IOCTL_DATA_IN = 1
SCSI_IOCTL_DATA_UNSPECIFIED = 2
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
    _fields_ = [
        ("Length", wt.USHORT),
        ("ScsiStatus", ctypes.c_ubyte),
        ("PathId", ctypes.c_ubyte),
        ("TargetId", ctypes.c_ubyte),
        ("Lun", ctypes.c_ubyte),
        ("CdbLength", ctypes.c_ubyte),
        ("SenseInfoLength", ctypes.c_ubyte),
        ("DataIn", ctypes.c_ubyte),
        ("DataTransferLength", wt.ULONG),
        ("TimeOutValue", wt.ULONG),
        ("DataBuffer", ctypes.c_void_p),
        ("SenseInfoOffset", wt.ULONG),
        ("Cdb", ctypes.c_ubyte * 16),
    ]


SENSE_SIZE = 32
BUF_SIZE = 512


class SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER(ctypes.Structure):
    _fields_ = [
        ("sptd", SCSI_PASS_THROUGH_DIRECT),
        ("sense", ctypes.c_ubyte * SENSE_SIZE),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def open_drive(n):
    path = r"\\.\PhysicalDrive%d" % n
    h = kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if h == INVALID_HANDLE_VALUE or h is None:
        err = ctypes.get_last_error()
        h = kernel32.CreateFileW(
            path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None,
        )
        if h == INVALID_HANDLE_VALUE or h is None:
            return None, ctypes.get_last_error()
        print("  (opened read-only; write access denied: %d)" % err)
    return h, 0


def scsi_inquiry(h, lun=0):
    buf = ctypes.create_string_buffer(BUF_SIZE)
    pkt = SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER()
    ctypes.memset(ctypes.byref(pkt), 0, ctypes.sizeof(pkt))

    pkt.sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    pkt.sptd.CdbLength = 6
    pkt.sptd.SenseInfoLength = SENSE_SIZE
    pkt.sptd.DataIn = SCSI_IOCTL_DATA_IN
    pkt.sptd.DataTransferLength = 36
    pkt.sptd.TimeOutValue = 10
    pkt.sptd.DataBuffer = ctypes.addressof(buf)
    pkt.sptd.SenseInfoOffset = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)

    # CDB: 0x12 0 0 0 <alloc_len> 0
    pkt.sptd.Cdb[0] = 0x12
    pkt.sptd.Cdb[4] = 36

    returned = wt.DWORD(0)
    ok = kernel32.DeviceIoControl(
        h, IOCTL_SCSI_PASS_THROUGH_DIRECT,
        ctypes.byref(pkt), ctypes.sizeof(pkt),
        ctypes.byref(pkt), ctypes.sizeof(pkt),
        ctypes.byref(returned), None,
    )
    if not ok:
        return None, "DeviceIoControl failed err=%d" % ctypes.get_last_error()
    if pkt.sptd.ScsiStatus != 0:
        return None, "ScsiStatus=0x%02x" % pkt.sptd.ScsiStatus

    raw = buf.raw[:64]
    vendor = raw[8:16].decode("latin1", "replace").strip(" \0")
    product = raw[16:32].decode("latin1", "replace").strip(" \0")
    rev = raw[32:36].decode("latin1", "replace").strip(" \0")
    if not vendor and not product:
        print("   [debug] raw36=%s" % raw[:36].hex())
        print("   [debug] scsiStatus=%d returned=%d" % (pkt.sptd.ScsiStatus, returned.value))
        print("   [debug] sense=%s" % bytes(pkt.sense).hex())
    return {"vendor": vendor, "product": product, "rev": rev}, None


def main():
    if len(sys.argv) > 1:
        cands = [int(sys.argv[1])]
    else:
        cands = list(range(0, 16))

    found = []
    for n in cands:
        h, err = open_drive(n)
        if h is None:
            continue
        try:
            info, e = scsi_inquiry(h)
            if info:
                line = "Drive %d: vendor=%r product=%r rev=%r" % (
                    n, info["vendor"], info["product"], info["rev"])
                print(line)
                if "SONY" in info["vendor"].upper() or "DSC" in info["product"].upper():
                    found.append((n, info))
            else:
                print("Drive %d: no inquiry (%s)" % (n, e))
        finally:
            kernel32.CloseHandle(h)

    print("")
    if found:
        print("==> SONY camera LUNs detected: %s" % [n for n, _ in found])
        print("==> SCSI pass-through channel is WORKING (no driver swap needed)")
    else:
        print("==> no SONY LUN found; camera may be disconnected or in another mode")


if __name__ == "__main__":
    main()
