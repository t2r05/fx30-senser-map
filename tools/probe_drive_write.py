#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_drive_write.py — 驱动模式双写实验（写操作）

===== 会写相机设置区 =====
· 目标：设置区（PDT）2.25 MB，只改指定的几个字节，不碰固件分区
· 每次写前自动落一份 before 快照，可原样写回

## 为什么要「双写」—— 关键发现（2026-10-24 离线判定）

`0x8EF80` 与 `0x91690` **不是**属性 id，而是两张枚举表的**位置索引（0-based）**：

| 观测标签 | 0x8EF80 | -> EXTERN_VAL_DRIVE_MODE[idx] | 0x91690 | -> DRIVE_MODE[idx] |
|---|---|---|---|---|
| single  | 0x00 | idx0  SINGLE           | 0x00 | idx0  1_IMAGE_SHOOTING   |
| timer   | 0x08 | idx8  SINGLE_SELF_2S   | 0x05 | idx5  SELF_TIMER         |
| bracket | 0x02 | idx2  BRACKET          | 0x09 | idx9  BRACKET_SINGLE    |

全部 12 份带标签快照 100% 自洽，无一例外。

**这解释了 10-24 那次「写了没生效」的负结果**：
`patch_after_08.bin` 里 `0x8EF80=0x08` 但 `0x91690=0x00` —— 只写了外层索引、
内层索引没跟上，两字段不一致 ⇒ 固件回退成单张。
（`check_083439.bin` 里固件后来自己把 `0x91690` 补成了 `0x05`，说明固件认得
  `0x8EF80` 的值，只是需要时间/或需要匹配的第二个字段。）

⇒ **必须两个字段一起写，且保持配对。**

## 连拍候选值

| 目标 | 0x8EF80 (EXTERN idx) | 0x91690 (INT idx) | 备注 |
|---|---|---|---|
| 单张 | 0x00 | 0x00 | 回滚用 |
| **连拍** | **0x01** (BURST) | **0x01** (CONT_SHOOTING) | 首测 |
| 连拍(限张) | 0x02 (BRACKET) | 0x02 (CONT_SHOOTING_LIMITED) | 已实测=包围 |
| 速度优先连拍 | 0x04 (SPEED_PRIOR_BURST) | 0x03 (SPD_PRIORITY_CONT) | 配对待验 |

⚠️ **不要写 `0x08DC14` / `0x07A640`** —— 早期以为是「随模式变化的第三字段」，
后续复现证明是**运行时噪声**：同一模式（`0x8EF80=0x00`）下 `0x8DC14` 实测出
9 个不同取值（`0x16`/`0x39`/`0x47`/`0x6A`/`0x72`/`0x79`/`0xD2`/`0xDA`/`0xDF`），
且第二次写入时它完全没变。它们不是模式的函数，写了也没用。
（`m0` 读法下 `0x8DC14` 恒为 `0xDA`，只有 `m1` 才读到变化值。）

## 用法（最简：三条命令走天下）

    python probe_drive_write.py --burst     # 开启连拍
    python probe_drive_write.py --single    # 回滚单张
    python probe_drive_write.py --probe     # 只看当前状态（不写）

预设一览（⚠️ 只有 burst / single 经实机验证，其余为按表推测）：

| 预设 | 0x8EF80 | 0x91690 | 含义 | 验证 |
|---|---|---|---|---|
| `--single`  | `0x00` | `0x00` | 单张 SINGLE / 1_IMAGE_SHOOTING | ✅ 已验证（回滚用） |
| `--burst`   | `0x01` | `0x01` | **连拍** BURST / CONT_SHOOTING | ✅ 已验证 |
| `--bracket` | `0x02` | `0x09` | 包围曝光 BRACKET / BRACKET_SINGLE | 🟡 实测过，未验证写入 |
| `--timer2`  | `0x08` | `0x05` | 自拍定时 2 秒 SINGLE_SELF_2S / SELF_TIMER | ✅ 实测过 |
| `--timer5`  | `0x0C` | `0x05` | 自拍定时 5 秒 | 🟡 推测 |
| `--timer10` | `0x07` | `0x05` | 自拍定时 10 秒 | 🟡 推测 |

也可以手动指定任意偏移：

    python probe_drive_write.py 0x8EF80=0x01 0x91690=0x01
    python probe_drive_write.py 0x8EF80=0x01 0x91690=0x01 --dry-run

## 完整流程（4 步）

    1. 相机 USB 模式设为「海量存储器」并插好线
    2. python probe_drive_write.py --burst
    3. 拔 USB 线 -> 取电池 ≥30 秒 -> 装回开机
    4. 看菜单：显示「连拍」；按住快门验证

ℹ️ **第 3 步推荐拔电池冷启动**（三次成功均如此）。用户实测**关机再开机也能保持**，
热重启**不会**清除改动 —— 早期文档说「会把改动吃掉」已被推翻（教训 #43）。
「写入后首次生效是否必须冷启动」尚未验证，稳妥起见仍建议拔电池。

⚠️ **只有「修改驱动模式设置」才掉回**。进菜单浏览、切视频模式录视频、
关机重启都**没事**（用户实测）。掉了重新跑一次 `--burst` 即可。

⚠️ **连拍是隐藏模式**：菜单里不显示该选项 ⇒ **没法更换拍照模式**。
想换单张/自拍定时/包围曝光，一选就掉回且回不去（要重刷），速度档也调不了。
让菜单正常显示连拍是当前正在攻的方向。
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

LOG = []

# ---- 常用模式预设：不用记十六进制 ----
# 值 = (0x8EF80, 0x91690)，即两张枚举表的位置索引
# ⚠️ 只有 BURST / SINGLE 经实机验证；其余为按表推测，未验证
PRESETS = {
    "burst":  (0x01, 0x01, "连拍 BURST / CONT_SHOOTING ✅已验证"),
    "single": (0x00, 0x00, "单张 SINGLE / 1_IMAGE_SHOOTING ✅已验证（回滚用）"),
    "bracket": (0x02, 0x09, "包围曝光 BRACKET / BRACKET_SINGLE 🟡实测过，未验证写入"),
    "timer2": (0x08, 0x05, "自拍定时 2 秒 SINGLE_SELF_2S / SELF_TIMER ✅实测过"),
    "timer5": (0x0C, 0x05, "自拍定时 5 秒 SINGLE_SELF_5S / SELF_TIMER 🟡推测"),
    "timer10": (0x07, 0x05, "自拍定时 10 秒 SINGLE_SELF_10S / SELF_TIMER 🟡推测"),
}

EXT = ['SINGLE', 'BURST', 'BRACKET', 'REMOTE', 'SPEED_PRIOR_BURST',
       'RAW_BURST', 'SINGLE_BRACKET', 'SINGLE_SELF_10S', 'SINGLE_SELF_2S',
       'BURST_SELF_10S', 'INVALID', 'SINGLE_SELF_3S', 'SINGLE_SELF_5S',
       'BURST_SELF_2S', 'BURST_SELF_5S', 'BOL_BURST', 'SPOT_BURST']
INT = ['1_IMAGE_SHOOTING', 'CONT_SHOOTING', 'CONT_SHOOTING_LIMITED',
       'SPD_PRIORITY_CONT', 'SINGLE_BURST_SHOOTING', 'SELF_TIMER',
       'SELF_PORTRAIT', 'CONT_SELF_TIMER', 'CONT_BRACKET', 'BRACKET_SINGLE',
       'FOCUS_BRACKET', 'WHITE_BALANCE_BRACKET', 'DRO_ADV_BRACKET',
       'LOW_PASS_FILTER_BRACKET', 'REMOTE_CDR', 'BURST_SHOOTING',
       'MOTION_SHOT']


def p(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    LOG.append(line)


def enter(driver):
    ds = list(listDevices(driver, True))
    # 上一次会话故意没调 stop()，相机会停留在服务身份（054C:0336）。
    # 这里直接复用：省一次手动切 USB 模式，不必断电重启。
    svc = [d for d in ds if isinstance(d, SonySenserDevice)]
    if svc:
        p("[*] 检测到已处于服务模式（上次会话未 stop）—— 直接复用，第 2 阶段认证")
        dev = svc[0]
        a = SonySenserAuthDevice(dev.driver)
        a.start()
        a.authenticate()
        return dev
    msc = [d for d in ds if isinstance(d, SonyMscExtCmdDevice)]
    if not msc:
        raise RuntimeError("未找到 MSC 设备 - 检查 USB=海量存储器 / 重新插拔")
    p("[*] MSC 已找到，第 1 阶段认证")
    a = SonySenserAuthDevice(msc[0].driver)
    a.start()
    a.authenticate()
    p("[*] 等待服务身份")
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
    """HASP 服务令牌健康检查 —— 长度必须 88 字节，否则本次会话不可信。"""
    try:
        hasp = SonySenserCamera(dev).readHasp()
        n = len(hasp) if hasp else 0
        if n == 88:
            p("[+] HASP 88 B  [OK] 服务通道可用")
            return True
        p("[!] HASP 长度 %d（期望 88）—— 会话可能未完全建立，结果不可信" % n)
        return False
    except Exception as e:
        p("[!] HASP 读取异常: %r" % (e,))
        return False


def read_fw_version(dev):
    """GET_VERSION (0x400D) —— 读固件版本。Ver 6.00 = `06 00 00 10`。

    6.01 固件给 PDT 直写加了内容校验（改任何字段返回 129），本脚本只对
    6.00 有效。因此任何写操作前必须先读版本，非 6.00 一律中止，绝不冒险。
    """
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


def read_mem1(dev, tag, stamp=""):
    h = HDR.pack(category=0x603, command=5)
    res, data = dev.sendSenserPacket(PFUNC_ADJ, h + b"\x01")
    if res != 0 or not data:
        p("  [!] 读 %s 失败 res=%s" % (tag, res))
        return None
    # 快照带时间戳，避免覆盖历史回滚材料（教训：回滚材料被覆盖就没法还原了）
    path = os.path.join(OUT, "drive_%s%s.bin" % (tag, stamp))
    with open(path, "wb") as f:
        f.write(data)
    p("  [+] 读 %-14s %d 字节 -> %s" % (tag, len(data), os.path.basename(path)))
    return data


def write_pdt(dev, blob, protect=0):
    h = HDR.pack(category=0x603, command=4)
    payload = protect.to_bytes(4, "little") + blob
    t0 = time.time()
    try:
        res, data = dev.sendSenserPacket(PFUNC_ADJ, h + payload)
    except Exception as e:
        p("  [!] 写异常: %s" % type(e).__name__)
        return None
    p("  [<] 写 res=%-4s 耗时 %.1fs" % (res, time.time() - t0))
    return res


def save_pdt(dev, subsystem=0):
    h = HDR.pack(category=0x603, command=3)
    try:
        res, _ = dev.sendSenserPacket(PFUNC_ADJ, h + subsystem.to_bytes(2, "little"))
    except Exception as e:
        p("  [!] save 异常: %s" % type(e).__name__)
        return None
    p("  [*] save -> res=%s" % res)
    return res


def show_state(blob, tag):
    if not blob:
        return
    e = blob[0x8EF80]
    i = blob[0x91690]
    p("  [%s] 0x8EF80=0x%02X -> %-20s | 0x91690=0x%02X -> %s"
      % (tag, e, EXT[e] if e < len(EXT) else '?',
         i, INT[i] if i < len(INT) else '?'))
    # 注意：0x08DC14 / 0x07A640 是运行时噪声，同一模式下取值可变，
    # 不可作为模式判据，更不要手写。此处仅作参考打印。
    p("       0x08DC14=0x%02X（噪声字段，仅供参考，勿用作判据）" % blob[0x08DC14])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    probe = "--probe" in sys.argv      # 纯只读：只看当前状态，不写
    preset = None
    for k in PRESETS:
        if ("--" + k) in sys.argv:
            preset = k
            break

    if not args and not probe and not preset:
        p("=" * 84)
        p("FX30 驱动模式写入 —— 用法")
        p("=" * 84)
        p("  最常用（不用记十六进制）：")
        p("    python probe_drive_write.py --burst     # 开启连拍")
        p("    python probe_drive_write.py --single    # 回滚单张")
        p("    python probe_drive_write.py --probe     # 只看当前状态（不写）")
        p("")
        p("  可用预设：")
        for k, (a, b, desc) in PRESETS.items():
            p("    --%-9s 0x8EF80=0x%02X 0x91690=0x%02X  %s" % (k, a, b, desc))
        p("")
        p("  手动指定任意偏移：")
        p("    python probe_drive_write.py 0x8EF80=0x01 0x91690=0x01")
        p("    python probe_drive_write.py 0x8EF80=0x01 0x91690=0x01 --dry-run")
        return 2

    if preset:
        a, b, desc = PRESETS[preset]
        args = ["0x8EF80=0x%02X" % a, "0x91690=0x%02X" % b]
        p("[*] 使用预设 --%s：%s" % (preset, desc))

    edits = []
    for a in args:
        if "=" not in a:
            p("[!] 参数格式应为 偏移=值，得到 %r" % a)
            return 2
        off_s, val_s = a.split("=", 1)
        edits.append((int(off_s, 0), int(val_s, 0) & 0xFF))

    p("=" * 84)
    if probe:
        p("驱动模式状态读取（纯只读，不写任何数据）")
    else:
        p("驱动模式双写实验（%s）" % ("DRY-RUN 不落盘" if dry else "实际写入"))
    p("=" * 84)
    for off, val in edits:
        p("  0x%06X <- 0x%02X" % (off, val))
    if edits:
        if 0x8EF80 in [o for o, _ in edits] and 0x91690 in [o for o, _ in edits]:
            p("  [i] 两字段成对写入 —— 符合 10-24 判定结论")
        else:
            p("  [!] 只写了一个字段 —— 依据 10-24 结论，这很可能被固件回退！")

    # 快照统一带时间戳，永不覆盖历史
    STAMP = "_" + time.strftime("%m%d_%H%M%S")

    try:
        with importDriver("libusb") as driver:
            dev = enter(driver)
            if not check_hasp(dev):
                p("[!] HASP 校验失败 —— 中止本次会话")
                return

            # 版本闸门：只对 Ver 6.00 有效，6.01 已封堵 PDT 直写（内容校验返 129）
            ver = read_fw_version(dev)
            if ver is None or len(ver) < 2 or not (ver[0] == 0x06 and ver[1] == 0x00):
                p("[!] 固件版本非 6.00（读到 %s）—— 中止，避免误写。"
                  % (ver.hex(" ") if ver else "读取失败"))
                p("[!] 本配方仅 Ver 6.00 有效；6.01 会封堵 PDT 直写。")
                return

            p("\n--- 1. 读原始快照（回滚材料）---")
            blob = read_mem1(dev, "before", STAMP)
            if blob is None:
                raise RuntimeError("读失败，终止")
            show_state(blob, "BEFORE")

            if probe:
                p("\n--- 只读模式：到此为止，未写入任何数据 ---")
                return 0

            patched = bytearray(blob)
            changed = []
            for off, val in edits:
                old = patched[off]
                if old != val:
                    changed.append((off, old, val))
                    patched[off] = val
            if not changed:
                p("\n  目标字节已是目标值，无需写入。")
                return 0

            p("\n--- 2. 打补丁 ---")
            for off, old, val in changed:
                p("  0x%06X: 0x%02X -> 0x%02X" % (off, old, val))

            if dry:
                p("\n--- DRY-RUN：到此为止，不写入 ---")
                return 0

            p("\n--- 3. 写回 + 保存 ---")
            if write_pdt(dev, bytes(patched)) is None:
                raise RuntimeError("写失败")
            save_pdt(dev)
            time.sleep(1.0)

            p("\n--- 4. 读回验证 ---")
            after = read_mem1(dev, "after", STAMP)
            if after:
                show_state(after, "AFTER ")
                for off, old, val in changed:
                    got = after[off]
                    p("  0x%06X 读回 0x%02X  %s" % (off, got,
                      "★ 已生效" if got == val else "!! 未生效（固件拒绝/回写）"))
                n = min(len(blob), len(after))
                idx = [i for i in range(n) if blob[i] != after[i]]
                p("  整体差异字节数: %d" % len(idx))
                if idx:
                    p("  差异偏移: %s" % ", ".join("0x%X" % i for i in idx[:40]))

            p("\n" + "=" * 84)
            p("下一步（人工，必须冷启动）")
            p("=" * 84)
            p("  1. 拔 USB 线 -> **取电池 ≥30 秒** -> 装回开机（热重启会被 nflasha5 吃掉）")
            p("  2. 看驱动模式菜单：是否变成目标模式")
            p("  3. 实拍验证：是否真能连拍")
            p("  4. 回滚： python probe_drive_write.py 0x8EF80=0x00 0x91690=0x00")
            p("     （或直接写回 dump/drive_before.bin）")

            # 故意不调用 stop()：stop 会让相机退出服务模式并重枚举回 PTP，
            # 下一次跑脚本就得再手动切一次 MSC。保持会话可让后续脚本直接复用。
            p("\n[*] 未调用 stop()，相机应仍保持 MSC/服务身份")
    except SystemExit:
        raise
    except Exception as e:
        p("[!] 终止: %s" % e)
    finally:
        logp = os.path.join(HERE, "probe_drive_write.log")
        with open(logp, "w", encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n")
        p("\n日志已存: %s" % logp)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
