#!/usr/bin/env python3
"""
extcmd_probe.py - Windows native SCSI vendor-command probe for Sony camera (READ ONLY)

Reimplements PMCA-RE's SonyExtCmdCamera._sendCommand over Windows
IOCTL_SCSI_PASS_THROUGH_DIRECT. No libusb, no Zadig, no driver replacement.

Only command issued: SONY_CMD_DevInfoSender_GetModelInfo = (1, 1)
  -> returns model name / model code / serial number. Pure read, zero mutation.

Reference: pmca/usb/sony.py
  _BaseSonyMscExtCmdDevice.MSC_OC_ExtCmd = 0x7a
  command = dump8(0x7a) + dump32le(cmd) + 7*b'\x00'
  ExtCmdHeader = INT32 dataSize, INT16 cmd, INT16 direction, 8 bytes reserved
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
SCSI_IOCTL_DATA_OUT = 0
SCSI_IOCTL_DATA_IN = 1
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
SENSE_SIZE = 32
XFER = 0x2000


class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
    _fields_ = [
        ("Length", wt.USHORT), ("ScsiStatus", ctypes.c_ubyte),
        ("PathId", ctypes.c_ubyte), ("TargetId", ctypes.c_ubyte),
        ("Lun", ctypes.c_ubyte), ("CdbLength", ctypes.c_ubyte),
        ("SenseInfoLength", ctypes.c_ubyte), ("DataIn", ctypes.c_ubyte),
        ("DataTransferLength", wt.ULONG), ("TimeOutValue", wt.ULONG),
        ("DataBuffer", ctypes.c_void_p), ("SenseInfoOffset", wt.ULONG),
        ("Cdb", ctypes.c_ubyte * 16),
    ]


class SPTD_WITH_BUFFER(ctypes.Structure):
    _fields_ = [("sptd", SCSI_PASS_THROUGH_DIRECT),
                ("sense", ctypes.c_ubyte * SENSE_SIZE)]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def open_drive(n):
    h = kernel32.CreateFileW(r"\\.\PhysicalDrive%d" % n,
                             GENERIC_READ | GENERIC_WRITE,
                             FILE_SHARE_READ | FILE_SHARE_WRITE,
                             None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE or h is None:
        return None
    return h


def raw_scsi(h, cdb, data_in, payload_len):
    buf = ctypes.create_string_buffer(payload_len if payload_len else 1)
    if data_in == SCSI_IOCTL_DATA_OUT and payload_len:
        ctypes.memmove(buf, payload_len if isinstance(payload_len, bytes) else b"", 0)

    pkt = SPTD_WITH_BUFFER()
    ctypes.memset(ctypes.byref(pkt), 0, ctypes.sizeof(pkt))
    pkt.sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    pkt.sptd.CdbLength = len(cdb)
    pkt.sptd.SenseInfoLength = SENSE_SIZE
    pkt.sptd.DataIn = data_in
    pkt.sptd.DataTransferLength = payload_len
    pkt.sptd.TimeOutValue = 30
    pkt.sptd.DataBuffer = ctypes.addressof(buf)
    pkt.sptd.SenseInfoOffset = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    for i, b in enumerate(cdb):
        pkt.sptd.Cdb[i] = b

    returned = wt.DWORD(0)
    ok = kernel32.DeviceIoControl(
        h, IOCTL_SCSI_PASS_THROUGH_DIRECT,
        ctypes.byref(pkt), ctypes.sizeof(pkt),
        ctypes.byref(pkt), ctypes.sizeof(pkt),
        ctypes.byref(returned), None)
    if not ok:
        return None, "ioctl err=%d" % ctypes.get_last_error()
    sense = bytes(pkt.sense)
    return (buf.raw, pkt.sptd.ScsiStatus, sense), None


def scsi_send_with_data(h, cdb, out_data, in_len):
    """Send CDB with DATA OUT, then read with same CDB (DATA IN). PMCA semantics."""
    payload = out_data.ljust(XFER, b"\x00")
    buf = ctypes.create_string_buffer(payload, XFER)

    pkt = SPTD_WITH_BUFFER()
    ctypes.memset(ctypes.byref(pkt), 0, ctypes.sizeof(pkt))
    pkt.sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    pkt.sptd.CdbLength = len(cdb)
    pkt.sptd.SenseInfoLength = SENSE_SIZE
    pkt.sptd.DataIn = SCSI_IOCTL_DATA_OUT
    pkt.sptd.DataTransferLength = XFER
    pkt.sptd.TimeOutValue = 30
    pkt.sptd.DataBuffer = ctypes.addressof(buf)
    pkt.sptd.SenseInfoOffset = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    for i, b in enumerate(cdb):
        pkt.sptd.Cdb[i] = b

    BUSY = (0x09, 0x81, 0x81)
    sense_out = None
    for _attempt in range(40):
        returned = wt.DWORD(0)
        ok = kernel32.DeviceIoControl(
            h, IOCTL_SCSI_PASS_THROUGH_DIRECT,
            ctypes.byref(pkt), ctypes.sizeof(pkt),
            ctypes.byref(pkt), ctypes.sizeof(pkt),
            ctypes.byref(returned), None)
        if not ok:
            return None, None, "OUT ioctl err=%d" % ctypes.get_last_error()
        sense_out = bytes(pkt.sense)
        key = (sense_out[2] & 0x0F, sense_out[12], sense_out[13])
        if key == BUSY:
            time.sleep(0.05)
            continue
        break
    if pkt.sptd.ScsiStatus != 0:
        return None, sense_out, "OUT scsiStatus=%d sense=%s" % (pkt.sptd.ScsiStatus, sense_out.hex())

    rbuf = ctypes.create_string_buffer(in_len)
    pkt2 = SPTD_WITH_BUFFER()
    ctypes.memset(ctypes.byref(pkt2), 0, ctypes.sizeof(pkt2))
    pkt2.sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    pkt2.sptd.CdbLength = len(cdb)
    pkt2.sptd.SenseInfoLength = SENSE_SIZE
    pkt2.sptd.DataIn = SCSI_IOCTL_DATA_IN
    pkt2.sptd.DataTransferLength = in_len
    pkt2.sptd.TimeOutValue = 30
    pkt2.sptd.DataBuffer = ctypes.addressof(rbuf)
    pkt2.sptd.SenseInfoOffset = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    for i, b in enumerate(cdb):
        pkt2.sptd.Cdb[i] = b

    for _attempt in range(40):
        returned2 = wt.DWORD(0)
        ok2 = kernel32.DeviceIoControl(
            h, IOCTL_SCSI_PASS_THROUGH_DIRECT,
            ctypes.byref(pkt2), ctypes.sizeof(pkt2),
            ctypes.byref(pkt2), ctypes.sizeof(pkt2),
            ctypes.byref(returned2), None)
        if not ok2:
            return None, sense_out, "IN ioctl err=%d" % ctypes.get_last_error()
        s2 = bytes(pkt2.sense)
        key2 = (s2[2] & 0x0F, s2[12], s2[13])
        if key2 == BUSY:
            time.sleep(0.05)
            continue
        if pkt2.sptd.ScsiStatus != 0:
            return None, s2, "IN scsiStatus=%d sense=%s" % (pkt2.sptd.ScsiStatus, s2.hex())
        break
    return rbuf.raw, sense_out, None


def parse_camera_info(data):
    try:
        off = 0
        plist_size = struct.unpack_from("<I", data, off)[0]
        off += 4
        plist = data[off:off + plist_size]
        off += plist_size
        off += 4
        name_len = data[off]
        off += 1
        name = data[off:off + name_len].decode("latin1", "replace")
        off += name_len
        model_code = data[off:off + 5].hex()
        off += 5
        serial = data[off:off + 4].hex()
        return {"model": name, "model_code": model_code, "serial": serial,
                "plist_len": plist_size}
    except Exception as e:
        return {"parse_error": str(e), "hex": data[:64].hex()}


def main():
    drives = [int(x) for x in sys.argv[1:]] or [7, 8, 9]
    MODULE_DEVINFO = 1
    CMD_GET_MODEL_INFO = 1

    cdb = bytes([0x7A]) + struct.pack("<I", MODULE_DEVINFO) + b"\x00" * 7
    header = struct.pack("<ihh8x", 0, CMD_GET_MODEL_INFO, 0)

    for d in drives:
        h = open_drive(d)
        if not h:
            print("Drive %d: cannot open" % d)
            continue
        try:
            raw, sense, err = scsi_send_with_data(h, cdb, header, XFER)
            print("Drive %d:" % d)
            if err:
                print("   FAILED: %s  sense=%s" % (err, sense.hex() if sense else "-"))
                continue
            data_size = struct.unpack_from("<i", raw, 0)[0]
            resp_cmd, resp_dir = struct.unpack_from("<hh", raw, 4)
            print("   ExtCmdHeader: dataSize=%d cmd=%d dir=%d" % (data_size, resp_cmd, resp_dir))
            body = raw[16:16 + data_size]
            if data_size > 0:
                info = parse_camera_info(body)
                print("   CAMERA INFO: %s" % info)
            else:
                print("   empty payload (channel responded but no data)")
        finally:
            kernel32.CloseHandle(h)


if __name__ == "__main__":
    main()
