#!/usr/bin/env python3
"""issue.py - open three tailored issues asking for the missing baseline."""
import os
import subprocess
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GH = r"C:\Users\Administrator\tools\gh\bin\gh.exe"
API = "https://api.github.com"
REPO_URL = "https://github.com/t2r05/fx30-senser-map"

ISSUES = [
    (
        "Himpq/FireHydrant",
        "FX30 (Ver.6.00) 上 FileControl 与 MemoryDump 均返回 128 —— 与 A6700 的通道边界不同",
        f"""你好，感谢把 A6700 的内存访问方法整理成文档，`DEVICE_CHANNEL.md` 里 `libJit.so` 加载入口和 `/proc/self/maps` 基址定位那段对我们非常有用。

我在 **ILME-FX30（Ver.6.00）** 上做了同样的探索，得到的通道边界和 A6700 有明显差异：

| pFunc | 名称 | FX30 6.00 |
|---|---|---|
| `0x10` | ProductInfo | ✅ 可用（88 字节） |
| `0x40` | AdjustControl | ✅ 可用 |
| `0xff01` | FileControl | ❌ **全部 128** |
| `0xff03` | MemoryDump | ❌ **全部 128**（含 `0xFFFF0000`） |

`pFunc=0x40` 下扫了 `0x600–0x62F × cmd 1–16`，只有 `0x603 / 0x604 / 0x608 / 0x610 / 0x611` 有响应：

- `0x603 cmd5` → 2,253,564 字节完整备份（PMCA `print_backup` 解析出 25,737 个属性；`modelName` / `modelCode` / `serialNumber` / `recLimit` 四个锚点与 PMCA 定义完全一致）
- `0x603 cmd6` → 52 字节备份状态（含区域代号）
- `0x611 cmd1` → 2,097,220 字节事件日志（16 字节/条，含空槽）
- `0x604` → 三个常量（`00` / `00460007` / `0001`）

完整记录（含响应码语义、扫描表、以及所有已排除的死路）：{REPO_URL}

**想请教两点：**

1. 你在 A6700 上读取 `/usr/lib/appFw.so` 时，走的是哪个 pFunc 与 category/command？FX30 上 FileControl 完全不响应，是否说明这代 Cinema Line 分支裁掉了文件通道？
2. 若手上有一台 **FX3** 的同格式备份（哪怕只提供 `0x003c` 功能限制段，约 827 个枚举属性即可，不涉及机身隐私），可否分享一份做对比？目标是定位「驱动模式」对应的属性 ID —— FX3 与 A6700 都有连拍，FX30 与二者同 BIONZ XR 平台、同 26MP 传感器，怀疑该功能在 FX30 上只是入口被关闭。

打扰了，任何线索都有帮助。""",
    ),
    (
        "YuuLuo/a7c2-service-preload",
        "FX30 (Ver.6.00)：Jiritsu 文件命令缺失，pFunc 0xff01/0xff03 均返回 128",
        f"""你好，`PROTOCOL.md` 对我们帮助极大——尤其是「Jiritsu 请求使用 `pFunc=0x40`」这一条，直接解释了我们在别的机型上踩的坑。

我在 **ILME-FX30（Ver.6.00）** 上复现了完整会话：MSC(`054C:0E0E`) → Senser 认证（三轮，PMCA 的 `senserKeys` 有效）→ 重枚举为 `054C:0336` → 再认证 → 进入命令循环。会话本身稳定可复现。

**但文件与内存通道都不响应：**

| pFunc | FX30 6.00 |
|---|---|
| `0x10` ProductInfo | ✅ |
| `0x40` AdjustControl | ✅ |
| `0xff01` FileControl | ❌ 128 |
| `0xff03` MemoryDump | ❌ 128（含 `0xFFFF0000`） |

试过的路径全部 128，包括 `/usr/lib/appFw.so`、`/etc/ld.so.preload`、`/tmp/jiritsu` 等，所以不是路径问题，是接口层不响应。

`pFunc=0x40` 下 `0x600–0x62F × cmd 1–16` 只有 `0x603 / 0x604 / 0x608 / 0x610 / 0x611` 有响应（备份、常量、事件日志），**没有看到类似「select path / read / write」的命令组合**。

记录在此：{REPO_URL}

**想请教：**

1. 在 A7C II 2.01 上，Jiritsu 的「select 路径 → read / write → 回读」这一串，具体是 `pFunc=0x40` 下的哪几个 `category / command`？
2. 你记录里那句「selectors containing `/tmp/jiritsu/../..` were resolved beyond the intended directory」——这个 selector 是通过哪个命令提交的？

如果 FX30 确实裁掉了文件通道，那结论也很明确，我们就转硬件路线，不再空耗。感谢。""",
    ),
    (
        "xyzhangxin/sony-a6700-powerful",
        "A6700 的「固定范围读写」走的是哪条通道？FX30 上 FileControl/MemoryDump 均 128",
        f"""你好，A6700 项目里那句「免 Pico 的 USB 极简刷写通道 —— 固定范围读写已实机验证」我们一直在追。

我在 **ILME-FX30（Ver.6.00）** 上做到了纯 USB 会话（Zadig + libusbK，MSC 与 0336 两个设备都换驱动）：

- ✅ Senser 认证通过（PMCA 的 `senserKeys` 在 6.00 上仍有效）
- ✅ 切入服务模式 `054C:0336`
- ✅ `pFunc=0x40` 下可用命令已测绘
- ❌ `0xff01`(FileControl) 与 `0xff03`(MemoryDump) **全部返回 128**

已测绘的 `0x40` 命令（`0x600–0x62F × cmd 1–16`）：

| cat | cmd | 返回 |
|---|---|---|
| `0x603` | `0x05` | **2,253,564 字节完整备份**（2.25MB，`BK4` 头，25,737 个属性） |
| `0x603` | `0x06` | 52 字节（含区域代号） |
| `0x603` | `0x03` | 0（备份保存） |
| `0x611` | `0x01` | 2,097,220 字节事件日志 |
| `0x604` | `0x01/02/03` | 常量 |

属性 ID 布局与 PMCA 定义同构（`modelName`/`modelCode`/`serialNumber`/`recLimit` 四个锚点全对上）。

完整记录：{REPO_URL}

**想请教：「固定范围读写」是走 MemoryDump（按地址），还是走某条 Jiritsu 文件命令？** 你帖子里说的「固定范围」听起来像按地址，但我们在 FX30 上 MemoryDump 拿不到响应，所以想确认：

1. A6700 上 MemoryDump（`0xff03`）可用吗？还是你走了别的通道？
2. 如果是 Jiritsu 文件命令，`pFunc=0x40` 下对应的 `category/command` 是什么？

另外，如果你手上有 **FX3 或 A6700 的备份**（只需 `0x003c` 功能限制段），分享一下对我们定位「驱动模式」属性 ID 会有决定性帮助 —— FX30 与它们同平台，我们怀疑连拍只是入口被关闭。

任何线索都感谢。""",
    ),
]


def main():
    tk = subprocess.check_output([GH, "auth", "token"], text=True).strip()
    s = requests.Session()
    s.headers.update({
        "Authorization": "token " + tk,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    s.trust_env = False
    s.verify = False

    for repo, title, body in ISSUES:
        r = s.post(f"{API}/repos/{repo}/issues",
                   json={"title": title, "body": body}, timeout=45)
        if r.status_code in (200, 201):
            print(f"[+] {repo} -> {r.json()['html_url']}")
        else:
            print(f"[!] {repo} failed {r.status_code}: {r.text[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
