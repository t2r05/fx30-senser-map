#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_cmdline.py — 一次性完成「清 jit.log → 下发载荷 → 读回」，判定载荷所在进程

===== 只写 SD 卡/tmpfs 日志，不碰设置区、不碰固件 =====

## 为什么合并成一个脚本

分步跑会遇到两个反复出现的坑：

  1. **会话不 stop 会污染 bulk 端点** → 下一次认证抛 GenericUsbException
  2. **每次脚本退出后相机掉出 MSC** → 被迫拔插重切

⇒ 把「清日志 → 写载荷 → 读回」放进**同一个会话**，一次跑完。

## 要回答的问题

载荷 `libJit.so` 是被 **Jiritsu** dlopen 的，而驱动模式的 `.bss` 地址
（`0x8230D78` 等）来自 **appFw.so**。如果是不同进程，地址空间隔离，
所有「改 .bss 让菜单显示连拍」的方案都不成立。

`/proc/self/cmdline` 能直接给出当前进程名 —— 一次 read 就够（cmdline < 64 字节）。

## 流程

    1. GET_FILE(0,3,0) 读一次 jit.log（留档）
    2. FILE_DELETE 0x4009 file_id=3
    3. MOUNT 0x4002 重挂（删文件会触发 nflasha6 卸载）
    4. GET_FILE 确认已空
    5. SET_FILE 0x4007 file_id=2 写入 cmdline 载荷
    6. 等 1.0s 让 constructor 执行
    7. GET_FILE file_id=3 读回 → 落盘 dump/CMDLINE.bin
    8. stop 干净退出

用法：
    python probe_cmdline.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools", "pmca-src"))

from pmca.commands.usb import importDriver, listDevices  # noqa: E402
from pmca.usb.sony import (  # noqa: E402
    SonyMscExtCmdDevice, SonySenserAuthDevice, SonySenserDevice,
    SonySenserCamera,
)

PF_ADJ = SonySenserCamera.SONY_PFUNC_AdjustControl
HDR = SonySenserCamera.CommandHeader

CMD_MOUNT = 0x4002
CMD_SET_FILE = 0x4007
CMD_GET_FILE = 0x4008
CMD_FILE_DELETE_A = 0x4009
CMD_FILE_DELETE_B = 0x4012
CMD_GET_VERSION = 0x400D

PAYLOAD = os.path.join(HERE, "payload_patched_cmdline.so")
OUT = os.path.join(HERE, "dump", "CMDLINE.bin")
FID_LOG = 2 + 1          # 3 = jit.log
FID_PAYLOAD = 2          # 2 = libJit.so

LOG = []


def p(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    LOG.append(line)


def enter(driver):
    ds = list(listDevices(driver, True))
    svc = [d for d in ds if isinstance(d, SonySenserDevice)]
    if svc:
        p("[*] 已在服务模式 —— 复用会话")
        dev = svc[0]
        a = SonySenserAuthDevice(dev.driver)
        a.start()
        a.authenticate()
        return dev
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]
    if not msc:
        raise RuntimeError("未找到 MSC 设备 —— 相机 USB 设「海量存储器」并拔插")
    p("[*] MSC 找到，第 1 阶段认证")
    a = SonySenserAuthDevice(msc[0].driver)
    a.start()
    a.authenticate()
    dev = None
    for _ in range(40):
        time.sleep(0.5)
        try:
            d2 = list(listDevices(driver, True))
        except Exception:
            d2 = []
        f = [x for x in d2 if isinstance(x, SonySenserDevice)]
        if f:
            dev = f[0]
            break
    if dev is None:
        raise RuntimeError("未出现服务身份")
    p("[*] 第 2 阶段认证")
    a = SonySenserAuthDevice(dev.driver)
    a.start()
    a.authenticate()
    return dev


def check_hasp(dev):
    try:
        hasp = SonySenserCamera(dev).readHasp()
        n = len(hasp) if hasp else 0
        if n == 88:
            p("[+] HASP 88 B  [OK]")
            return True
        p("[!] HASP 长度 %d（期望 88）—— 会话不可信" % n)
        return False
    except Exception as e:
        p("[!] HASP 异常: %r" % (e,))
        return False


def send(dev, cmd, payload, label):
    h = HDR.pack(category=0x1001, command=cmd)
    try:
        res, data = dev.sendSenserPacket(PF_ADJ, h + payload)
        p("  %-30s res=%-4s len=%-6d %s"
          % (label, res, len(data) if data else 0,
             data[:12].hex(" ") if data else ""))
        return res, data
    except Exception as e:
        p("  %-30s EXC %s" % (label, type(e).__name__))
        return None, None


def get_file(dev, fid, label):
    res, data = send(dev, CMD_GET_FILE, bytes([0, fid, 0]), label)
    body = data[4:] if data and len(data) > 4 else b""
    return res, body


def main():
    p("=" * 78)
    p("载荷所在进程判定（cmdline 探测，一次会话完成）")
    p("=" * 78)
    if not os.path.isfile(PAYLOAD):
        p("[!] 缺少载荷 %s" % PAYLOAD)
        p("    先跑: python patch_libssp.py --mode=cmdline")
        return 2
    so = open(PAYLOAD, "rb").read()
    p("载荷: %s  %d 字节" % (os.path.basename(PAYLOAD), len(so)))

    try:
        with importDriver("libusb") as driver:
            dev = enter(driver)
            if not check_hasp(dev):
                return
            send(dev, CMD_GET_VERSION, b"", "GET_VERSION")

            p("\n[1] 读一次 jit.log 留档")
            _, old = get_file(dev, FID_LOG, "GET jit.log 删除前")
            p("      %d 字节: %r" % (len(old), old[:60]))

            p("\n[2] 清空 jit.log")
            r1, _ = send(dev, CMD_FILE_DELETE_A, bytes([0, FID_LOG, 0]),
                         "FILE_DELETE 0x4009")
            if r1 != 0:
                send(dev, CMD_FILE_DELETE_B, bytes([0, FID_LOG, 0]),
                     "FILE_DELETE 0x4012")

            p("\n[3] 重挂 nflasha6（删文件会触发卸载）")
            send(dev, CMD_MOUNT, b"", "MOUNT 0x4002")
            time.sleep(0.3)

            _, chk = get_file(dev, FID_LOG, "GET jit.log 删除后")
            p("      确认: %s" % ("已空 ✓" if not chk else "仍有 %d 字节" % len(chk)))

            p("\n[4] 下发 cmdline 载荷")
            res, data = send(dev, CMD_SET_FILE, bytes([0, FID_PAYLOAD, 0]) + so,
                             "SET_FILE cmdline")
            code = int.from_bytes(data[:4], "little") if data and len(data) >= 4 else None
            p("      dlopen 返回码 = %s"
              % ("0x%08X" % code if code is not None else "无"))

            p("\n[5] 等 1.0s 让 constructor 执行")
            time.sleep(1.0)

            p("\n[6] 读回 jit.log")
            _, got = get_file(dev, FID_LOG, "GET jit.log")
            p("      %d 字节: %r" % (len(got), got[:80]))

            if got:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT, "wb") as f:
                    f.write(got)
                p("      已落盘 -> %s" % OUT)

                p("\n" + "=" * 78)
                p("解析")
                p("=" * 78)
                # cmdline 是 NUL 分隔的
                parts = [x for x in got.split(b"\x00") if x]
                p("  cmdline 片段（NUL 分隔）:")
                for k, seg in enumerate(parts[:6]):
                    try:
                        txt = seg.decode("utf-8", errors="replace")
                    except Exception:
                        txt = repr(seg)
                    p("    [%d] %r" % (k, txt))
                joined = " ".join(
                    s.decode("latin1", errors="replace") for s in parts)
                low = joined.lower()
                p("\n  关键字检测:")
                for kw in ("appfw", "jiritsu", "im.elf", "app", "sh", "init"):
                    if kw in low:
                        p("    命中 %-9s ✓" % kw)
                p("\n  ⇒ 判定:")
                if "appfw" in low:
                    p("     载荷运行在 **appFw 进程内**（或同地址空间）")
                    p("     ⇒ 可以直接读/写 0x8230D78 等 .bss 地址，B 方案可行")
                elif "jiritsu" in low:
                    p("     载荷运行在 **Jiritsu 独立进程**")
                    p("     ⇒ 与 appFw 地址空间隔离，需另找注入 appFw 的路径")
                else:
                    p("     未见 appFw / Jiritsu 关键字，请看上面的原始片段判断")
            else:
                p("\n[!] 没读到内容 —— 载荷未执行或写日志失败")
                p("    返回码 %s" % ("0x%08X" % code if code is not None else "无"))
    except Exception as e:
        import traceback
        p("[!] %r" % (e,))
        p(traceback.format_exc())
        if "GenericUsb" in type(e).__name__:
            p("\n[!] USB 端点污染 —— 请拔插一次 USB 后重跑")
    finally:
        try:
            if 'dev' in dir() and dev is not None:
                SonySenserAuthDevice(dev.driver).stop()
        except Exception:
            pass
        with open(os.path.join(HERE, "probe_cmdline.log"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n")
        p("\n日志: probe_cmdline.log")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
