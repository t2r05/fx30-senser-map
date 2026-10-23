# 06 · 相关开源项目目录

> 本项目研究过程中**参考 / 对照 / 邻近的其他作者开源项目**汇总。仅列项目名、仓库与一句话定位，便于溯源与逐个学习。
> **不含任何固件内容、备份数据或机身唯一信息。**

核验日期：2026-10-23。

## 目录

| # | 项目名 | 仓库 | 类别 | 一句话定位 |
|---|--------|------|------|-----------|
| 1 | **Powerful6700** | [xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) | 主线 · A6700 | A6700 功能解锁（USB 直连 + Pico 双路线） |
| 2 | **A7C2-FL23 / A7C2 Tools** | [QAQLeonard/a7c2-fl23-research](https://github.com/QAQLeonard/a7c2-fl23-research) | 主线 · A7C II | 创意外观 / 快门声 / 竖屏工具（v3.0.0） |
| 3 | **a7c2-service-preload** | [YuuLuo/a7c2-service-preload](https://github.com/YuuLuo/a7c2-service-preload) | 上游 · 机理 | A7C II 服务模式预加载与代码执行链路 |
| 4 | **ILCE-7M4-RE** | [DavidBuchanan314/ILCE-7M4-RE](https://github.com/DavidBuchanan314/ILCE-7M4-RE) | 上游 · 逆向 | A7M4 逆向笔记（bootrom / serial boot） |
| 5 | **Sony-PMCA-RE** | [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) | 上游 · 基础库 | Sony 服务协议基础实现（Senser / print_backup / fwtool） |
| 6 | **FireHydrant** | [Himpq/FireHydrant](https://github.com/Himpq/FireHydrant) | 相关 · 内存 | A6700 内存访问方法 |
| 7 | **Recipe Lab** | [voxivoid/recipe-lab-sony-pmca](https://github.com/voxivoid/recipe-lab-sony-pmca) | 相关 · 生态 | 基于 PMCA 的创意外观 App |

## 说明

### 主线（同代机型的可用成品）

- **Powerful6700**（A6700 2.00，0.1.0.dev33 测试版）：当前版本**普通 USB 直连、无需 Pico**，勾选解锁 + **冷重载**（关机 → 拔电池 → 等 10s → 插电池 → 开机）生效；开放 FTP / 关机快门帘 / 灵活曝光 / 电子快门声。仓库另保留 **Pico 路线**（冷启动引导 → Fastboot → 读已知范围备份）。
- **A7C2-FL23 / A7C2 Tools**（A7C II 2.01，v3.0.0）：经 USB 服务模式写入固件程序与设置，同样需**冷重载**；基于 Sony-PMCA-RE + `fwtool.py` + a7c2-service-preload。

### 上游（上述项目所依赖 / 借鉴）

- **a7c2-service-preload**：记录从 USB 服务会话到**一次性 root 代码执行**的完整链路（Jiritsu 文件命令 + 路径穿越 + `/etc/ld.so.preload`）。理解「写通道」的关键文档；**注意其为临时 RCE，不永久关闭签名校验**。
- **ILCE-7M4-RE**：A7M4 逆向笔记（含 bootrom / serial boot 思路），Powerful6700 明确参考。
- **Sony-PMCA-RE**：本项目与上述项目共同的基础——认证帧、Senser 协议、`print_backup`、`fwtool.py`。

## 对本项目（FX30）的意义

早期本项目仅测了 `0xff01`（FileControl）返回 `128`，据此判断「无写通道」。但上述项目显示：同代机型的实际写入**并不依赖 `0xff01`**，而走 **Jiritsu 文件命令 + 路径穿越**等另一套命令面；且改完都需要**冷重载**才从 NV 加载。

因此本项目的「无写通道」结论**需在 FX30 上重新验证 Jiritsu 命令面**，而非固守单一命令的返回码。（详见 [`04-dead-ends.md`](04-dead-ends.md) 与 README「与其他机型研究的差异」。）

---

*仅项目索引，不含固件内容。各项目版权与许可归原作者所有。*
