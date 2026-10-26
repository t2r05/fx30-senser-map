#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_menu_flags.py — 试验「菜单可见性标志」：把 FX3 有、FX30 无的 3 个 7 字节组改成 0x01

===== 写操作（设置区 PDT，不碰固件）=====

## 背景：来自 FX30↔FX3 PDT 对齐（见 16-FX30-FX3-PDT对齐结果.md）

用 `delta = -560` 对齐两机型出厂备份后，发现 142 个差异字节，其中 84 字节构成
**12 个「7 字节等值组」**。最强的 3 组同时满足 4 个条件：

    · 长度 7（与驱动模式菜单项数量量级吻合）
    · 每项 1 字节，值域 {0,1}（典型布尔开关）
    · **FX3 全是 0x01，FX30 全是 0x00**（方向与「FX3 有连拍菜单、FX30 没有」一致）
    · 35 份实拍快照里**全部恒定**（是静态能力表，不是用户设置）

| 偏移区间 | 长度 | FX30 | FX3 |
|---|---|---|---|
| `0x91700–0x9170D` | 14 | `0x00`×14 | `0x01`×14 |
| `0x918B9–0x918BF` | 7  | `0x00`×7  | `0x01`×7  |
| `0x91E90–0x91E96` | 7  | `0x00`×7  | `0x01`×7  |

## 但必须清醒（不要过度期待）

FX30 是**全 0**、FX3 是**全 1**，不是混合值。若真是「7 个模式的可见性」，
那 FX30 全 0 意味着连单张/自拍定时都不可见 —— 与事实矛盾。
⇒ 也可能是**连拍专属的 7 个子项**，或**根本无关的另一组设置**。
**形状像 ≠ 就是它**（教训 #47/#49）。本实验就是去证伪/证实。

## 实验设计

**一次改全部 3 组**（28 字节 → `0x01`），冷启动看菜单是否多出「连拍」：
- 变了 → 二分法定位是哪一组
- 没变 → 转下一批候选（`0x91754` 的 `0x03` 组、`0x91715` 的 21 字节组）

## 用法

    python probe_menu_flags.py --probe          # 只读，看当前 28 字节的值
    python probe_menu_flags.py --apply          # 写入 3 组 = 0x01
    python probe_menu_flags.py --revert         # 恢复成 0x00
    python probe_menu_flags.py --apply --only=1 # 只写第 1 组（0x91700，14B）

## 安全

* 🟡 写设置区（`0x603/4` 全量写 + `0x603/3` save），**不碰固件分区**
* 每次写入前自动落完整快照 `dump/menuflags_before_<时间戳>.bin`（2.25 MB）
* 回滚：`--revert`，或写回上面的快照
* 最坏情况：某些设置项异常 → 相机「恢复出厂设置」可解
* 这些是**静态常量表**，我们从未写过；固件可能在启动时校验/归一
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

PFUNC_ADJ = SonySenserCamera.SONY_PFUNC_AdjustControl
HDR = SonySenserCamera.CommandHeader
OUT = os.path.join(HERE, "dump")

# 3 个候选组：(起始偏移, 长度, 目标值, 说明)
GROUPS = [
    (0x91700, 14, 0x01, "组1: 2×7 项, FX3 全 0x01"),
    (0x918B9, 7,  0x01, "组2: 7 项,   FX3 全 0x01"),
    (0x91E90, 7,  0x01, "组3: 7 项,   FX3 全 0x01"),
]

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
        raise RuntimeError("未找到 MSC 设备 - 相机 USB 设为「海量存储器」并拔插")
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


def read_fw_version(dev):
    """GET_VERSION (0x400D) —— 读固件版本。Ver 6.00 = `06 00 00 10`。
    6.01 封堵 PDT 直写（内容校验返 129），本脚本只对 6.00 有效，非 6.00 中止。"""
    h = HDR.pack(category=0x400D, command=0)
    try:
        res, data = dev.sendSenserPacket(PFUNC_ADJ, h)
    except Exception as e:
        p("[!] GET_VERSION 读取异常: %r" % (e,))
        return None
    if res != 0 or not data:
        p("[!] GET_VERSION 失败 res=%s data=%r" % (res, data))
        return None
    p("[*] GET_VERSION (0x400D) -> res=%s len=%d  %s"
      % (res, len(data), data.hex(" ")))
    return data


def read_mem1(dev, tag):
    h = HDR.pack(category=0x603, command=5)
    res, data = dev.sendSenserPacket(PFUNC_ADJ, h + b"\x01")
    if res != 0 or not data:
        p("  [!] 读失败 res=%s" % res)
        return None
    if tag:
        path = os.path.join(OUT, "menuflags_%s.bin" % tag)
        with open(path, "wb") as f:
            f.write(data)
        p("  [+] 快照 -> %s" % os.path.basename(path))
    return data


def write_pdt(dev, blob):
    h = HDR.pack(category=0x603, command=4)
    t0 = time.time()
    try:
        res, _ = dev.sendSenserPacket(PFUNC_ADJ, h + (0).to_bytes(4, "little") + blob)
    except Exception as e:
        p("  [!] 写异常 %s" % type(e).__name__)
        return None
    p("  [<] 写 res=%s  %.1fs" % (res, time.time() - t0))
    return res


def save_pdt(dev):
    h = HDR.pack(category=0x603, command=3)
    try:
        res, _ = dev.sendSenserPacket(PFUNC_ADJ, h + (0).to_bytes(2, "little"))
    except Exception as e:
        p("  [!] save 异常 %s" % type(e).__name__)
        return None
    p("  [*] save res=%s" % res)
    return res


def show(blob, tag):
    p("\n  [%s] 3 个候选组的当前值：" % tag)
    for off, ln, tgt, desc in GROUPS:
        vals = blob[off:off + ln]
        uniq = sorted(set(vals))
        p("    0x%06X +%-2d  %-24s  = %s   (distinct=%s)"
          % (off, ln, desc, vals.hex(" "),
             ",".join("0x%02X" % v for v in uniq)))


def main():
    mode = None
    only = None
    for a in sys.argv[1:]:
        if a in ("--probe", "--apply", "--revert"):
            mode = a
        elif a.startswith("--only="):
            only = int(a.split("=", 1)[1])
    if mode is None:
        p("用法: probe_menu_flags.py --probe | --apply | --revert [--only=N]")
        p("  组号 N: 1=0x91700(14B) 2=0x918B9(7B) 3=0x91E90(7B)")
        return 2

    target = 0x01 if mode == "--apply" else 0x00
    groups = GROUPS
    if only is not None:
        if not (1 <= only <= len(GROUPS)):
            p("[!] --only 只能是 1..%d" % len(GROUPS))
            return 2
        groups = [GROUPS[only - 1]]

    p("=" * 80)
    p("菜单可见性标志试验 —— %s（目标值 0x%02X）" % (mode, target))
    p("=" * 80)
    for off, ln, _, desc in groups:
        p("  0x%06X +%-2d -> 0x%02X   %s" % (off, ln, target, desc))

    stamp = time.strftime("%m%d_%H%M%S")
    try:
        with importDriver("libusb") as driver:
            dev = enter(driver)
            if not check_hasp(dev):
                p("[!] 中止")
                return

            # 版本闸门：只对 Ver 6.00 有效，6.01 已封堵 PDT 直写
            ver = read_fw_version(dev)
            if ver is None or len(ver) < 2 or not (ver[0] == 0x06 and ver[1] == 0x00):
                p("[!] 固件版本非 6.00（读到 %s）—— 中止，避免误写。"
                  % (ver.hex(" ") if ver else "读取失败"))
                return

            p("\n--- 1. 读当前 PDT ---")
            blob = read_mem1(dev, "before_" + stamp)
            if blob is None:
                raise RuntimeError("读失败")
            show(blob, "BEFORE")

            # 同时打印已知模式字段，确认状态
            p("\n  已知模式字段: 0x8EF80=0x%02X  0x91690=0x%02X"
              % (blob[0x8EF80], blob[0x91690]))

            if mode == "--probe":
                p("\n--- 只读模式：到此为止 ---")
                return 0

            p("\n--- 2. 打补丁 ---")
            patched = bytearray(blob)
            changed = 0
            for off, ln, _, desc in groups:
                for k in range(ln):
                    o = off + k
                    if patched[o] != target:
                        patched[o] = target
                        changed += 1
                p("  0x%06X+%-2d -> 0x%02X ×%d" % (off, ln, target, ln))
            if changed == 0:
                p("  已是目标值，无需写入")
                return 0
            p("  共改 %d 字节" % changed)

            p("\n--- 3. 写回 + save ---")
            if write_pdt(dev, bytes(patched)) is None:
                raise RuntimeError("写失败")
            save_pdt(dev)
            time.sleep(1.0)

            p("\n--- 4. 读回验证 ---")
            after = read_mem1(dev, "after_" + stamp)
            if after:
                show(after, "AFTER")
                ok = True
                for off, ln, _, desc in groups:
                    got = after[off:off + ln]
                    good = all(v == target for v in got)
                    ok = ok and good
                    p("    0x%06X %s" % (off, "★ 已生效" if good else "!! 未生效"))
                n = min(len(blob), len(after))
                diffs = [i for i in range(n) if blob[i] != after[i]]
                p("\n  整体差异 %d 字节: %s"
                  % (len(diffs), ", ".join("0x%X" % i for i in diffs[:30])))

                p("\n" + "=" * 80)
                p("下一步（人工）")
                p("=" * 80)
                p("  1. 拔 USB -> 拔电池 >=30 秒 -> 装回开机（必须冷启动）")
                p("  2. 看驱动模式菜单：是否**多出「连拍」以外的选项**，或连拍是否变成")
                p("     菜单里可选（不再是隐藏模式）")
                p("  3. 记录菜单前后变化，回报")
                p("  4. 回滚： python probe_menu_flags.py --revert")
                p("=" * 80)

            try:
                SonySenserAuthDevice(dev.driver).stop()
            except Exception:
                pass
    except Exception as e:
        import traceback
        p("[!] %r" % (e,))
        p(traceback.format_exc())
    finally:
        with open(os.path.join(HERE, "probe_menu_flags.log"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n")
        p("\n日志: probe_menu_flags.log")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
