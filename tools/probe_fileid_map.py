#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_fileid_map.py — 只读核对 Jiritsu 文件槽位语义（FX30 6.00）

目的：验证 xyzhanxin 在 Issue #2 回复里提到的
      「0x4010 file_id=0 = 读取器配置 / 0x4008 file_id=0 = 取回执行结果」
      与我方从 libJiritsu.so 反汇编得到的索引表是否同一套：

          get_jiritsu_area_filename(arg1)  @ libJiritsu.so 0x1236C
          0 -> /tmp/jiritsu/tmmc.jit
          1 -> /tmp/jiritsu/DIAC.csv
          2 -> /tmp/jiritsu/libJit.so
          3 -> /tmp/jiritsu/jit.log
          4 -> /tmp/jiritsu/history.txt

安全性：
  默认**只发 GET_FILE(0x4008)**，纯读，不写、不删、不改任何东西。
  0x4010(SET_FILE2) 只有加 --allow-4010 才会发，且只发 3 字节空头
  （无正文 -> 不会向文件写入任何内容，但可能把目标截断，故默认关闭）。

用法：
  python probe_fileid_map.py                 # 纯读 5 个槽
  python probe_fileid_map.py --allow-4010    # 额外探 0x4010 是否响应
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools", "pmca-src"))

from pmca.commands.usb import importDriver, listDevices          # noqa: E402
from pmca.usb.sony import (                                      # noqa: E402
    SonyMscExtCmdDevice, SonySenserAuthDevice, SonySenserDevice,
    SonySenserCamera,
)

PF_ADJ = SonySenserCamera.SONY_PFUNC_AdjustControl
HDR = SonySenserCamera.CommandHeader
CAT = 0x1001

CMD_SET_FILE = 0x4007
CMD_GET_FILE = 0x4008
CMD_GET_VERSION = 0x400D
CMD_SET_FILE2 = 0x4010          # 仅 --allow-4010 时使用

# 反汇编得出的索引表（自检用，不是猜的）
SLOTS = [
    (0, "tmmc.jit",     "读取器配置（对方称之为『读取器配置』）"),
    (1, "DIAC.csv",     "Jiritsu 命令映射表本体"),
    (2, "libJit.so",    "代码载荷槽（dlopen 目标）"),
    (3, "jit.log",      "执行日志（我方闭环用这个）"),
    (4, "history.txt",  "历史注入记录"),
]

LOG = []


def p(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    LOG.append(line)


def enter(driver):
    ds = list(listDevices(driver, True))
    if any(isinstance(d, SonySenserDevice) for d in ds):
        raise RuntimeError("已在服务模式 —— 请先拔电池/拔插回 MSC")
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]
    if not msc:
        raise RuntimeError("未找到 MSC 设备 (054C:0E0E) —— 请拔插一次 USB")
    p("[*] MSC 找到，认证 #1")
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
        raise RuntimeError("服务身份 054C:0336 未出现")
    p("[*] 认证 #2")
    a = SonySenserAuthDevice(dev.driver)
    a.start()
    a.authenticate()
    return dev


def check_hasp(dev):
    """HASP 服务令牌健康检查。

    为什么会加这个：早前日志只记「HASP 完成」，不记长度 ——
    返回 0 字节也会被当成完成。按 Sony 定义 HASP 固定 88 字节
    （pmca: SONY_PRODUCT_INFO_READ_HASP = (0, 0x001f)，走 pFunc 0x10），
    长度不等于 88 就说明这次会话没真正建立，后面的读取结果一律不可信。
    """
    try:
        hasp = SonySenserCamera(dev).readHasp()
        n = len(hasp) if hasp else 0
        if n == 88:
            p("[+] HASP 88 B  ✅ 服务通道可用")
            return True
        p("[!] HASP 长度 %d（期望 88）—— 会话可能未完全建立" % n)
        return False
    except Exception as e:  # noqa: BLE001
        p("[!] HASP 读取异常: %r" % (e,))
        return False


def send(dev, cmd, payload, label):
    h = HDR.pack(category=CAT, command=cmd)
    res, data = dev.sendSenserPacket(PF_ADJ, h + payload)
    p("  %-34s plen=%-6d -> res=%-4s len=%s"
      % (label, len(payload), res, len(data) if data else 0))
    return res, data


def classify(data):
    if not data or len(data) <= 4:
        return "空 / 不存在"
    body = data[4:]
    if body[:4] == b"\x7fELF":
        return "ELF 载荷 (%d B)" % len(body)
    if body[:1] == b"\x89":
        return "PNG/图片 (%d B)" % len(body)
    head = body[:48]
    printable = sum(1 for c in head if 32 <= c < 127 or c in (9, 10, 13))
    if printable >= len(head) * 0.8:
        return "文本 (%d B): %r" % (len(body), bytes(body[:60]))
    return "二进制 (%d B) %s" % (len(body), body[:16].hex(" "))


def main():
    allow_4010 = "--allow-4010" in sys.argv

    p("=" * 78)
    p("Jiritsu 文件槽位只读核对 — FX30")
    p("模式: %s" % ("GET + 0x4010 空头探测" if allow_4010 else "纯读（GET_FILE only）"))
    p("=" * 78)

    results = {}
    try:
        with importDriver("libusb") as driver:
            dev = enter(driver)

            p("\n[-] HASP 健康检查（长度应为 88）")
            hasp_ok = check_hasp(dev)
            if not hasp_ok:
                p("    ⚠️ HASP 未达 88 B —— 后续读取结果需要打折扣看")

            p("\n[0] 版本自检")
            send(dev, CMD_GET_VERSION, b"", "GET_VERSION 0x400D")

            p("\n[1] 逐槽读回（0x4008，纯读）")
            for fid, name, note in SLOTS:
                res, data = send(dev, CMD_GET_FILE, bytes([0, fid, 0]),
                                 "GET file_id=%d (%s)" % (fid, name))
                results[fid] = (res, len(data) if data else 0, data)
                p("      判定: %s" % classify(data))
                p("      备注: %s" % note)

            if allow_4010:
                p("\n[2] 探 0x4010 是否响应（空头 plen=3，无正文）")
                res, data = send(dev, CMD_SET_FILE2, bytes([0, 0, 0]),
                                 "SET_FILE2 0x4010 fid=0 空头")
                p("      res=%s 返回=%s"
                  % (res, data[:8].hex(" ") if data else "无"))

            try:
                SonySenserAuthDevice(dev.driver).stop()
            except Exception:
                pass
    except Exception as e:
        p("[!] 异常: %s: %s" % (type(e).__name__, e))

    # ---------------- 判读 ----------------
    p("\n" + "=" * 78)
    p("判读")
    p("=" * 78)

    if not results:
        p("  无数据（认证或会话失败）")
    else:
        nonzero = {k: v for k, v in results.items() if v[1] > 4}
        p("  有内容的槽: %s"
          % (", ".join("file_id=%d=%dB" % (k, v[1]) for k, v in nonzero.items())
             or "无（全部 ≤4 字节）"))

        if 2 in results and results[2][1] > 4:
            p("  ★ file_id=2 非空 -> /tmp/jiritsu/libJit.so 里仍有载荷残留")
            p("    → 必须用 FILE_DELETE(0x4009/0x4012) 清理，否则跨重启反复 dlopen")
        elif 2 in results:
            p("  ✅ file_id=2 为空 -> libJit.so 槽干净")

        if 0 in results and results[0][1] > 4:
            p("  ★ file_id=0 非空 -> tmmc.jit 有内容（可能就是对方的『读取器配置』）")
        elif 0 in results:
            p("  ○ file_id=0 为空 -> tmmc.jit 不存在或未配置")

        if 3 in results and results[3][1] > 4:
            body = results[3][2][4:].decode("utf-8", "replace")
            if "PWNED" in body:
                p("  ★ file_id=3(jit.log) 含 PWNED -> 上次注入的代码确实执行过")

    p("\n  索引表核对：若 file_id=2 命中的是 ELF 或历史载荷，")
    p("  则 libJiritsu.so 0x1236C 跳转表的槽位映射成立；")
    p("  若对方所称 『file_id=0 = 执行结果』能在 0 槽读到日志文本，")
    p("  则说明其 libJit 会主动改写 tmmc.jit（覆盖配置表），而非常规用法。")

    p("\n  日志: probe_fileid_map.log")
    with open(os.path.join(HERE, "probe_fileid_map.log"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(LOG))


if __name__ == "__main__":
    main()
