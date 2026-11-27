# CREDITS · 借鉴与致谢

> 本项目大量站在他人工作上。本页区分「用了什么 / 没用什么 / 我们回馈了什么」，避免把别人的成果写成自己的。
> 只列公开仓库与公开 issue；不含任何人的私信、固件或机身信息。

## 一、6.00 open gate（2026-11-27）

| 来源 | 我们用了什么 | 没有用什么 | 回馈 |
|---|---|---|---|
| **ArcaneLantern** · [fx30-open-gate-test](https://github.com/ArcaneLantern/fx30-open-gate-test) | kit v2 的 sensor / output / screen / encoder design、guard 机制、runner、README 里的传感器时序（1680/1990 line pairs、9.4577 µs） | 没有把他的 6.01 地址硬套到 6.00；没有改他的任何现有步骤 | issue **#13**（全量测试报告）、PR **#14**（`contrib/fx30-6.00-pal/`） |
| **@resaviews**（A6700 移植作者，经 ArcaneLantern 的 [a6700-open-gate-test](https://github.com/ArcaneLantern/a6700-open-gate-test) 转发） | **p50 描述符组**（height 2560、`UseCore=2`、level 153→180）与 50p 模式；我们按 −0xf90 映射到 FX30 | 没有用他的 5.76K / playback fix；没有冒充 A6700 结果 | PR #14 的 `expected_mp_ogfile50p_fx30_relink.h` 明确署名；本页 |
| **Kwitglasses** · issue [#4](https://github.com/ArcaneLantern/fx30-open-gate-test/issues/4) | 6.00 机身的 `expected_mp_ogfile2560_hs_s_fx30_relink.h`（libmpr 位移思路）；「6.00 不是 relink 6.01」的判据 | 没有照抄他的 25p-only 站点；我们扩到 50p | 在 #4 回复确认；PR #14 署名 |
| **irobin-netizen (#10) / josuemorenoquintero4-wq (#11) / ae-stardust (#12) / ultimabeat (#8) / rashadhokan (#9)** | 现象与未决问题：HS 重启、热、电力开关、坏点、屏幕 | 没有用他们的 dump 或机身数据 | #13 逐项回答；#10/#11 交叉链接 |

## 二、连拍与菜单层（2026-10-24 ~ 11-22）

| 来源 | 我们用了什么 | 没有用什么 | 说明 |
|---|---|---|---|
| **Himpq/FireHydrant** | **三层模型**（菜单准入 / 支持层 / 计算基准）、「菜单可见 ≠ 可用」、运行期补丁 COW、拔电池而非仅开关电源 | 没有他的地址（他刻意不给），也没有照抄 A6700 的偏移 | 方法论来源；我们的 7 字节 appFw 补丁是独立定位 |
| **xyzhangxin/sony-a6700-powerful**（Powerful6700） | A6700 2.00 `FEATURES.md` 的已公开解锁偏移，作为**已知答案的校准尺**；A6700 四档连拍枚举作结构对照 | 没有用他的 USB/Pico 写入链；没有用他的成品代码 | 校准，不是移植 |
| **lzh2016zzz/a7cr-fl23-research** | 「产品标志 + 选择能力 + 初始值」三步模板（带 offset）的思路 | **它的 column 模型没有迁移到 FX30**（我方 42 号文档已作废该线索） | 模板启发；结论是否定的，也记录在案 |
| **nolan2628/Sony-ZVE-10-Camtool** | 载荷 ELF 铁律（两段 LOAD、`-O1`、禁 UNDEF 弱符号、`dc civac`/`ic ivau`） | 没有用它的 ZV-E10 地址 | 构建规则来源 |
| **ma1co/Sony-PMCA-RE** | Senser / Jiritsu 协议、`print_backup`、`fwtool.py` 基础 | — | 所有服务模式工作的底座 |
| **Lincan19540/fx30-firmware-research** | 「HASP 服务令牌」术语、双句柄坑 | 没有用它的封闭阶段内容 | 术语修正 |

## 三、社区测试者（现象来源）

- #8 ultimabeat：电源开关、冻结、Movie dump
- #9 rashadhokan：电源开关只重置传感器侧
- #10 irobin-netizen：HS 重启（我们据此定位 50p 描述符缺失）
- #11 josuemorenoquintero4-wq：<10 min 升温（我们用 11m46s 数据回答）
- #12 ae-stardust：坏点、电力开关、待测项

## 四、我们明确没有做的

- 没有把任何人的仓库整体 fork 成自己的成果；PR 只放 `contrib/`，不改上游现有文件。
- 没有把「社区方法」写成「我们的原创」；本页与各文档的首段都标了来源。
- 没有公开任何人的 dump、机身信息或密钥。

## 五、如何引用本项目

- 仓库：<https://github.com/t2r05/fx30-senser-map>
- open gate 6.00 结果：`docs/21-FX30-6.00-open-gate-三档全通-2026-11-27.md`
- 社区报告：issue #13；贡献：PR #14
