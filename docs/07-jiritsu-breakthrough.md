# 07 · Jiritsu 写通道：从「不存在」修正为「未验证」

> 本文修正本仓库早期「FX30 没有写通道」的结论，并记录 2026-10-23 的离线固件分析结果。
> **不含固件二进制、不含完整 BKID 表、不含机身唯一信息。**

---

## 一、为什么要修正

早期结论的依据是两条实测：

| 早期证据 | 当时的推断 |
|---|---|
| `pFunc=0xff01`（FileControl）全部返回 `128` | 没有文件通道 |
| 扫描 `category 0x600–0x62F` 后写入「未覆盖 category < 0x600」 | 以为主要命令面已覆盖 |

对照社区同代机型的工作后发现：**Jiritsu 文件服务不走 `0xff01`，也不在 `0x600–0x62F`**。它位于：

```
pFunc    = 0x40  (AdjustControl)
category = 0x1001
command  = 0x4007 (SET_FILE) / 0x4010 (SET_FILE2)
payload  = [area, file_id, transfer_mode, data...]
```

这条命令面在 FX30 上**从未被探测过**。因此正确表述应为：

> **FX30 是否存在 Jiritsu 写通道，尚未验证。**

（`pFunc=0x40` 通道本身在 FX30 上是活的：`0x603/0x604/0x608/0x610/0x611` 均可响应。）

---

## 二、机制（三个上游项目一致）

公开工作 `YuuLuo/a7c2-service-preload`、`xyzhangxin/sony-a6700-powerful`、`Himpq/FireHydrant` 描述的是同一套链路：

```
USB MSC → Senser 两阶段认证 → 重枚举 054C:0336 → 服务身份认证
  → Jiritsu SET_FILE 写入 /tmp/jiritsu/libJit.so
  → 固件初始化 dlopen 该路径 → 模块构造函数以维护进程 root 执行
```

要点（来自上游文档）：

- `/tmp/jiritsu` 位于**专用 flash 分区**，写入的文件**跨重启保留**；
- `libJit.so` 也是固件自身要加载的路径，放入模块会**遮蔽原库**，用完必须移除；
- Jiritsu 路径前缀检查在主机侧完成，相机端不做规范化（绝对路径可越界读取）；
- **内存**修改作用于 appFw.so 的私有映射（COW），断电即消失；**文件**修改持久，失败则可能无法开机（需官方 SD 恢复包）；
- 推荐顺序：先内存验证行为，再考虑持久化写入。

---

## 三、FX30 已确认 / 未确认

| 项 | 状态 |
|---|---|
| `pFunc=0x40` 通道可达 | ✅ 已实测 |
| `category 0x1001` 是否存在 | ✅ **存在**（`0x4001`–`0x4012` 共 18 条命令） |
| `0x4007` SET_FILE 语义 | ✅ **已实测** |
| `0x4010` SET_FILE2 语义 | ⬜ 未实测（反汇编判定为「配合 `0x400F` 的按路径写」） |
| SET_FILE / libJit 注入 | ✅ **已实测，代码已执行** |
| 写入后冷重载生效 | ✅ 已实测 |

### 3.1 实机物证（FX30 Ver.6.00）

```
[0] GET_VERSION 0x400D              -> res=0  len=4   06 00 00 10
[1] SET_FILE 0x4007 plen=10,187     -> res=0  len=4   00 00 00 00
[2] GET_FILE 0x4008 [0,3,0]         -> res=0  len=20  b'PWNED-JITLOG-V4\n'
```

副作用文件由**自写的 ARM64 机器码**产生，不是主机侧回显 ⇒ 代码确实在相机 CPU 上执行。

因此上游那句「加载路径仅在 A6700 验证，其他机型仍需单独确认」可以更新为：
**FX30 Ver.6.00 与 A6700 在该链路上同构、可用。**

### 3.2 `file_id` 槽位表（`libJiritsu.so` 反汇编）

`get_jiritsu_area_filename()` @ `0x1236C`，跳转字节 `1C 00 13 16 19`，目标 `0x8F2C + byte*4`：

| `file_id` | 路径 |
|---|---|
| 0 | `/tmp/jiritsu/tmmc.jit` |
| 1 | `/tmp/jiritsu/DIAC.csv` |
| **2** | **`/tmp/jiritsu/libJit.so`** |
| 3 | `/tmp/jiritsu/jit.log` |
| 4 | `/tmp/jiritsu/history.txt` |

`file_id > 4` 时改走 `0x470AD8` 的 34 项查找表（16 B/项 `{u8 id, pad, u64 path_ptr}`）。

> `file_id = 2 → libJit.so` 与 A6700 项目 `packet_builder.py` 的 `file_id = 2` 完全一致 —— 跨机型互证。

### 3.3 ⚠️ 用完必须删（且删完要重挂）

`/tmp/jiritsu` 是 `/dev/nflasha6`（`nflasha6 = Jiritsu`，25 MB **flash 分区**）的真实挂载点，
**写入的文件跨重启保留，并会被固件反复 dlopen**。测试载荷用完必须用
`FILE_DELETE`（`0x4009` / `0x4012`）删除并读回确认。

> **2026-10-24 补充（来自 ZV-E10 同族实践）**：
> 删掉 `libJit.so` 会让 Jiritsu **卸载整个 nflasha6**，此后读 `/tmp/jiritsu` 返回 **130**。
> **130 表示「分区已卸载」，不是「文件不存在」** —— 本项目早期判断错了方向。
> 恢复办法：发 `0x4002`(MOUNT) 重新挂载，之后读写正常。
>
> 所以清理动作的正确顺序是：
> `FILE_DELETE` 删除 → 读回（此时可能 130）→ `0x4002` 重挂 → 再读回确认目录已空。

配套只读探测脚本：
- `fx30_hack/probe_jiritsu_1001.py` — 只发空 payload
- `fx30_hack/probe_fileid_map.py` — 逐槽 `GET_FILE` 读回，核对上面的槽位表

### 3.4 槽位表的第三方独立印证

ZV-E10 的清理脚本把下列路径硬编码为「**固件文件，永不删除**」：

```
tmmc.jit    DIAC.csv    jit.log    history.txt    ver.txt
```

对照上面解出的索引表：`file_id=0 → tmmc.jit`、`file_id=3 → jit.log` —— **完全对上**，
并补全了本表未知的 `DIAC.csv` / `history.txt` / `ver.txt` 三个固件文件。

这也回答了一个悬而未决的问题：`tmmc.jit` 本来就是固件自带文件，**不该被当作「结果槽」**。

---

## 四、离线固件分析（2026-10-23）

### 4.1 解包

`ma1co/fwtool.py` + **PR #52**（CXD90057 密钥）解包官方 `BODYDATA.DAT`，耗时 1m42s，产物：

```
0700_part_image/dev/nflasha15_unpacked/lib/appFw.so   79,032,104 字节
```

### 4.2 BKID 注册表

`appFw.so` 的 `.data.rel.ro`（`sh_addr - sh_offset = 0x10000`）中存在一张**名字↔ID 注册表**：

```
每条 16 字节: { u64 name_ptr, u32 id, u32 extra }
```

- 连续区间：虚拟地址 `0x414A940 .. 0x415B970`，共 **4,355 条**
- 连拍项：**`BKID_APP_setting_drive_mode_cont_shooting`，id = 1208**
  - 记录位置：文件偏移 `0x42B140` / 虚拟地址 `0x414F7B0`
- 限制版：`..._cont_shooting_limited`，id = 1210

### 4.3 以 BKID 为键的平行表（共发现 9 处）

| 位置（文件偏移） | 结构 | 含义 |
|---|---|---|
| `0x4097970` 附近 | `{u32 id, u32 0, u64 desc_ptr}`，16B stride | BKID → 描述符 |
| `0x3087FCC` | `{i32 id, i32 idx}`，8B stride | 稠密索引（`1208 → 1142`，即 `id − 66`） |
| `0x37EC238` | `{i32 id, i32 n}` | 1208 → 4（与其 4 档选项一致） |
| `0x380C09C` | `{i32 id, i32 off}` | 组内偏移（1207→0, 1208→1, 1209→2） |

`1208` 的描述符（`0x40DB870`）为：`{u32 base_strid = 0x0831F850, u32 count = 6, 后续 6 个连续 STRID}`。

> **关键判断**：以上都是**功能属性表**（名称、索引、选项描述），**不是「支持/不支持」开关**。扫描 `8 字节步长、值∈{0,1}` 的长数组只命中一段全 0 空白区，说明 FX30 的「单字节支持开关」不是稠密 0/1 数组。

---

## 五、下一步

| 优先级 | 动作 | 依赖 |
|---|---|---|
| **P0** | 运行 `probe_jiritsu_1001.py`：确认 `0x1001 / 0x4007 / 0x4010` 是否存在 | 相机 + 线 |
| **P1** | **差分定位支持位**：与 A6700 2.00 或 FX3 的 `appFw.so` 对齐结构，找出「FX30 为 00、有连拍机型为 01」的字节 | 另一机型固件（离线） |
| P2 | 若 SET_FILE 存在：自编译**只读** AArch64 模块，先用 `file_id ≠ 2` 验证传输 | 交叉编译 |
| P3 | 内存 patch 验证连拍（COW，断电即恢复） | P0–P2 成立 |
| P4 | 持久化写入（最后一步，需事先准备官方 SD 恢复包） | 全部成立 |

---

## 六、安全边界

- `probe_jiritsu_1001.py` 只发送空 payload（`size=4`），不含 `area/file_id/data`，**无法写入文件**；
- **绝不**在未准备恢复手段时用 `file_id=2` 发送真实数据——会覆盖固件自身的 `libJit.so`；
- Jiritsu 目录在 flash 分区，写入跨重启保留；
- 会话不可复用：冷启动 → 单次运行 → 干净退出 → 断电/拔插。

---

## 七、参考

- [YuuLuo/a7c2-service-preload](https://github.com/YuuLuo/a7c2-service-preload) — 认证时序与 Jiritsu→代码执行链路
- [xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) — Jiritsu 报文常量（`packet_builder.py`）
- [Himpq/FireHydrant](https://github.com/Himpq/FireHydrant) — 通道、libJit 加载、内存/文件两类修改
- [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py) + PR #52 — 固件解密

*仅方法与结论，不含固件内容。*
