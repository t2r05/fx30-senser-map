# TRAE 任务包 · 第六期：PRM 参数系统 / 菜单过滤逻辑 / restriction 机制

> 生成时间：2026-10-25
> 上游：`TRAE-PACK-4.md`（PDT 对齐，已完成）、`TRAE-PACK-5.md`（4 方向，部分完成）
> 本期目标：**锁定「驱动模式菜单为什么不列连拍」的真正判定点**，并寻找**不碰内存、只写 PDT** 的解法。

---

## 0. 全局边界（必须遵守）

| 禁止 | 说明 |
|---|---|
| **不连接相机** | 本期 100% 纯离线静态分析。相机端实验由我方执行 |
| **不运行任何 `probe_*.py`** | 那些会打开 USB 设备 |
| **不改 `fw/` 下任何文件** | 只读 |
| **不改 `audit/tasks/` 下既有 T11_* 脚本** | 要写新脚本就用 `T14_` 前缀 |
| **不 git commit / push** | 由我方统一提交 |
| **不下结论性判断** | 只回数字、地址、偏移、字节片段（≤32 字节）、统计结果 |
| **不输出大块固件二进制** | 允许标量值与短结构数组（如 `{6,7,4,0}`） |

Python 一律用绝对路径：

```
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe
```

工作目录：`F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack`

---

## 1. 已确证事实（不要重做，直接用）

### 1.1 隐藏连拍已完全打通（实机验证 3 次）

```
PDT 写 0x8EF80 = 0x01  (EXTERN_VAL_DRIVE_MODE 索引 = BURST)
PDT 写 0x91690 = 0x01  (DRIVE_MODE 索引 = CONT_SHOOTING)
→ 拔电池 ≥30s 冷启动 → 进入连拍，可正常连拍
```

- 必须**成对**写；只写一个字段会被固件回退
- 持久性矩阵已填满：已生效后热重启/冷启动/进菜单/切视频模式都保持；**只有手动修改驱动模式设置才掉回**
- 回滚：两字段写回 `0x00`

### 1.2 PDT 与 FX3 的对齐位移 = **−560（−0x230）**

`delta = off_FX3 − off_FX30`。关键区段相同率：

| FX30 区段 | delta | 相同率 |
|---|---|---|
| `0x8D000–0x8DFFF` | −604 | 98.34% |
| `0x8E000–0x8EFFF` | −560 | 99.27% |
| `0x8F000–0x8FFFF` | −560 | 100.00% |
| `0x90000–0x90FFF` | −560 | 100.00% |
| `0x91000–0x91FFF` | −560 | 97.27% |
| `0x92000–0x92FFF` | −560 | 100.00% |
| `0x93000–0x93FFF` | −560 | 99.49% |
| `0x99000–0x99FFF` | −560 | 100.00% |

> ⚠️ **同偏移读 ≠ 同一位置**。`FX3[0x91690]=0x0C` 曾经误导我们很久，它对齐后是 `FX30[0x918C0]`（也是 `0x0C`），不是差异。任何跨机型比较都必须先按 −560 对齐。

### 1.3 运行时 `.bss` 已打通（我方实机，供参考）

| 项 | 值 |
|---|---|
| 载荷宿主进程 | `/usr/bin/im.elf`（与 appFw.so **同进程**） |
| appFw.so 加载基址 | `0x7F40544000`（该平台**无 ASLR**，拔插后不变） |
| `.bss` vaddr / size | `0x04B6E738` / `0x0525B2C0`（82.4 MB，匿名 mmap） |
| 已读到的值 | `0x83461A4=6`、`0x83461A8=7`、`0x83461AC=4`、`0x831F82C=7`、`0x8230D78=0`、`0x8220844=0` |
| 已排除的靶点 | `0x8220844/0x8220845` 写 1 → **菜单无变化**（不是可见性开关） |

### 1.4 本期新查到的字符串锚点（appFw.so，**文件偏移**，非 vaddr）

`appFw.so` 大小 79,032,104 字节。

| 字符串 | 文件偏移 | 备注 |
|---|---|---|
| `PRM_shoot_set_registration_drive_mode_multi0` | 60486695 | multi1/2/3 步长 **0x2D**（45） |
| `PRM_shoot_set_registration_drive_mode_bracket_multi0` | 60486875 | 步长 0x35（53） |
| `PRM_shoot_set_registration_drive_mode_bracket_single0` | 60487087 | 步长 0x36（54） |
| `PRM_shoot_set_registration_drive_mode_available0` | 60488119 | available1/2/3 步长 **0x31**（49） |
| `VAL_shoot_set_registration_drive_mode_multi0_..._MULTI_HI_PLUS` | 60804177 | 同组还有 `_HI` / `_MID` / `_LOW` → **连拍速度四档** |
| `VAL_shoot_set_registration_drive_mode_available0_..._DISABLE` | 60863637 | |
| `VAL_shoot_set_registration_drive_mode_available0_..._ENABLE` | 60863728 | DISABLE/ENABLE 成对，步长≈91 |

restriction 族（文件偏移）：

| 字符串 | 文件偏移 |
|---|---|
| `PRM_HAITA_model_diff_apsc_restriction_imager_frame_rate_in_file_format_fhd` | 60472898 |
| `PRM_HAITA_model_diff_apsc_restriction_imager_frame_rate_in_file_format_4k` | 60472973 |
| `PRM_raw_output_framerate_restriction` | 60473463 |
| `PRM_HAITA_raw_output_framerate_restriction_setting_different_set_for_s_q_mv` | 60473500 |
| `PRM_HAITA_streaming_usb_speed_restriction` | 60476325 |
| `PRM_HAITA_file_format_4k_network_streaming_restriction` | 60477004 |
| `PRM_HAITA_file_format_xavc_hs_streaming_restriction` | 60477059 |
| `PRM_HAITA_file_format_xavc_hs_network_streaming_restriction` | 60477111 |

**重要**：`PRM_*` / `VAL_*` 就住在 `appFw.so` 里，但**不在 BKID 表里** —— 用 `dump_bkid_table.py FX30 streaming_usb_speed` 查是 **0 命中**。所以这是**同一二进制内的第二套命名/参数体系**，不要用 BKID 工具找它们。

### 1.5 已知的失败路线（别再踩）

| 路线 | 失败原因 |
|---|---|
| 扫 `0x83461A4/A8/AC` 的第三方内存引用 | 命中 9 处，**全在访问器桩自身**（`0x028C134C–0x028C14A8`），无第三方直接引用 |
| `T11_desc.py` 查 `0x04B6/0x04B8` | 只解出 `0x02AF`，其余未命中（描述符表只覆盖部分 id） |
| 用 `cont_shoot` 关键词搜菜单表 | **0 命中** |
| PDT 用差分法找「菜单列表」 | 菜单列表是**常量**，差分筛不到（方法论错误） |
| 写 `.bss` 0x8220844/845 = 1 | 菜单无变化，已排除 |
| 属性 id 数字直接当语义 | **id 空间会复用**：`0x0C30` 在 BKID 是 `registration_drive_mode0`，在 `0x015BFB44` 处配的却是闪光灯补偿字符串 |

---

## 2. 资产与工具

### 2.1 固件（只读）

```
fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so     ← 79,032,104 B（主战场）
fw/out/firmware.tar_unpacked/0110_backup/SYSIPSX-DSLR/LAX/CX96700_ALLLANG.bin         ← FX30 出厂设置 2,253,564 B
fw/fx3out/firmware.tar_unpacked/0110_backup/SYSIPSX-DSLR/ALCINA/CX94700_ALLLANG.bin   ← FX3  2,229,740 B
fw/a6700out/.../SYSIPSX-DSLR/DZ/CX89500_ALLLANG.bin                                   ← A6700 2,351,065 B
fw/a7c2out/.../SYSIPSX-DSLR/PP/CX89700_ALLLANG.bin                                    ← A7C2  2,390,264 B
```

### 2.2 现有工具（`audit/tasks/`）

`T11_arr.py` `T11_bl.py` `T11_cons.py` `T11_ctx.py` `T11_desc.py` `T11_dump.py`
`T11_iduse.py` `T11_menu.py` `T11_pair.py` `T11_prop.py` `T11_prop_vis.py` `T11_ptr.py`
`T11_ref.py` `T11_registry.py` `T11_strs.py` `T11_xaddr.py` `T11_xref.py` `T11_xscan.py`

（第五期新增的 `T13_pdt_align.py` / `T13_pdt_buckets.py` / `T13_pdt_cmp.py` / `T13_pdt_subshift.py` / `T13_pdt_const.py` 也可复用）

新脚本一律 `T14_` 前缀，产物写 `audit_raw/T14_*.txt`（同时复制一份到 `tmp01/`）。

### 2.3 快照

`dump/` 下 47 个 `.bin`，其中 **35 份** 尺寸 = 2,253,564（实机 PDT 转储）；其余为小文件，忽略。
其中 4 份是模式参照：`pdtl_single_m0/m1`、`pdtl_timer_m0/m1`、`pdtl_bracket_m0/m1`。

---

## 3. 任务（按价值排序，逐个回报）

### T1 ⭐⭐⭐ · PRM 参数系统的表结构与存储位置

**要回答的核心问题**：`PRM_shoot_set_registration_drive_mode_available0..3` 这个参数，
**它的值到底存在哪里**？分三种可能，结论不同则后续路径完全不同：

| 存储位置 | 后果 |
|---|---|
| `.bss`（运行时内存） | 只能 dlopen 写，重启即丢 |
| **PDT（设置区闪存）** | ✅ **可从 USB 直接写，永久生效，零风险** |
| 其他分区 / 未持久化 | 需要另找路径 |

**步骤**：

1. 找指向 `PRM_shoot_set_registration_drive_mode_available0`（文件偏移 60488119）的 **qword 指针**，从 `.rodata`/`.data.rel.ro` 里搜。
2. 顺着指针找到它所在的**表项**，dump 该表项前后（建议 ±0x60 字节，按 8 字节对齐打印成 `偏移: qword` 形式）。
3. 判断表项结构，典型形态可能是：
   ```
   { name_ptr, id(u16/u32), default_value, storage_ptr/offset, flags }
   ```
   把能确定的字段标出来，不能确定的标 `?`。
4. 对 **4 个 available**（偏移 60488119/60488168/60488217/60488266）和 **4 个 multi**（60486695/60486740/60486785/60486830）分别解，做成对照表：

   | 参数名 | 文件偏移 | 表项地址 | 解出的 id | 解出的存储地址/偏移 | 默认值 | 置信度 |
   |---|---|---|---|---|---|---|

5. **交叉验证**：已知 appFw BKID 里 `registration_drive_mode_available0..2` 的 `.bss` 是 `0x83461A4` / `0x83461A8` / `0x83461AC`。请判断：
   - PRM 的 available0..3 与 BKID 的 available0..3 是否**同一份存储**？
   - 若是，`available` 的 `VAL_..._DISABLE/ENABLE`（值应为 0/1）如何解释运行时读到的 `6 / 7 / 4`？
     （提示：`6=0b110`、`7=0b111`、`4=0b100`，可能是**位图**而非布尔；请只做数值/结构分析，不下语义结论）
   - 若不是，指出两者的存储地址各是多少。

6. 顺带解：`PRM_shoot_set_registration_drive_mode_multi0..3` 的存储位置与值域（`VAL_..._MULTI_HI_PLUS/HI/MID/LOW` → 应该是 4 档，值 0..3）。

**验收标准**：
- 给出 ≥8 个 PRM 的「名称 → 存储位置」映射表，每个都带文件偏移 + 解出的地址
- 明确回答「存储是否落在 PDT 覆盖的 2,253,564 字节范围内」
- 若表结构解不出，明说卡在哪一步、试过哪几种假设

---

### T2 ⭐⭐⭐ · 菜单项可见性的判定调用链

**背景**：上一期扫 `0x83461A4/A8/AC` 的第三方内存引用，命中 9 处**全在访问器桩自身**（`0x028C134C–0x028C14A8`）。这说明**访问器是通过函数指针/虚表被调用的**，直接搜内存引用找不到消费者。

**换思路**（三条并行，哪条通算哪条）：

**路线 A · 从访问器桩地址反查函数表**
1. 取这 9 处桩的**代码地址**（`0x028C13xx–0x028C14xx` 区间内的函数起点）。
2. 在 `appFw.so` 里搜包含这些地址的 **qword 数组**（即 vtable / dispatch table）。
3. 找到表之后，反查**谁引用这张表**（谁把表基址装进寄存器并 `bl`/`blr` 调用）。
4. 目标：拿到「读 available → 比较 → 分支」的那个函数，报出：
   - 函数地址
   - 它从哪个偏移读的
   - 它跟什么常量比较（比如 `cmp w0, #1` / `tst w0, #2`）
   - 分支走向（哪个分支是"显示"，哪个是"隐藏"）

**路线 B · 从菜单项构造入口向下追**
- 已知 `0x02AF = setting_menu_drive_mode`（`PRM` 对应的菜单项），其主值 `.bss` = `0x8230D78`。
- 找**读 `0x8230D78` 的函数**，看它的返回值怎么被消费（返回 0 是不是就等于"不显示"）。
- 用 `T11_xaddr.py` / `T11_xscan.py` 在 `.bss` 目标附近扩大窗口扫。

**路线 C · 从枚举表往下追**
- `EXTERN_VAL_DRIVE_MODE` 表基 `0x041A0550`（17 项）、`DRIVE_MODE` 表基 `0x041A28F0`。
- 找**遍历这两张表**的循环（典型形态：`add x, x, #4` 或 `#2` + `cmp` 上界 17），
  看循环体里是否跳过某些索引（跳过 = 隐藏）。
- 这是最有希望的一条：**"菜单不显示连拍"本质上就是"遍历时跳过了索引 0x01"**。

**验收标准**：
- 报出至少 1 条**完整调用链**：菜单构造 → 可见性判定 → 读取的字段 → 比较常量 → 分支地址
- 若三条路线都断，逐条说明断在哪（地址不存在 / 表找不到 / 反汇编对不上）

---

### T3 ⭐⭐ · restriction 机制：那个「功能被禁止」的弹窗

**背景**：用户在联机模式菜单里尝试改「联机速度」时，相机弹出「该功能被禁止」。固件里存在 `sequence_get_restriction_info` 一族，说明有统一的限制判定。

**任务**：

1. 定位 `sequence_get_restriction_info` 相关字符串 / 函数，dump 出它的实现。
2. 找**限制原因枚举表**（`RESTRICTION_REASON` / `VAL_*restriction*` 一族），列出全部原因项及其数值。
   已知存在的 VAL 前缀包括：
   `VAL_HAITA_model_diff_apsc_restriction_*`、`VAL_raw_output_framerate_restriction_*`、
   `VAL_HAITA_streaming_usb_speed_restriction_*`、`VAL_HAITA_file_format_4k_network_streaming_restriction*`
3. 回答：`PRM_HAITA_streaming_usb_speed_restriction`（文件偏移 60476325）的**值从哪来**？
   - 是 PDT 里的某个字段？还是由「线材/协议/分辨率」组合计算出来的？
   - 找它的赋值点（谁写了这个参数）。
4. **复核**：上期扫 `VAL_*restriction*` 没搜到任何 drive_mode 项。请用更宽的模式（含 `_restriction_`、`restrict_`、`inhibit_`、`prohibit_`、`not_available`、`unavailable`）再扫一遍，确认：
   - 有没有**任何**与 drive_mode / burst / cont_shoot 相关的限制项？
   - 若确实没有 → 明确回报"0 命中"，这是重要负面结论（说明 restriction 机制解不了菜单问题）。

**验收标准**：
- 限制原因枚举表（≥6 项，带值）
- 给出 `streaming_usb_speed_restriction` 的写入点地址或明确"未找到"
- 给出 drive_mode 相关性扫描的**命中数**（0 也要报）

---

### T4 ⭐⭐⭐ · PDT 里是否存在 available*/multi* 的持久化副本

**这条如果通了，收益最大** —— 意味着**不用 dlopen、不用改内存，直接从 USB 写就能让菜单出现连拍**。

**思路**：先按 T1 拿到 `available0..3` 和 `multi0..3` 的**默认值/合法值域**，再拿这些值去 PDT 里做结构搜索。

**步骤**：

1. 从 FX30 出厂备份（`CX96700_ALLLANG.bin`，2,253,564 B）里搜索「连续 4 字节，值都在 0..15，至少 3 个不同值，4 字节对齐」的块。
   注意上期 `T13_pdt_const.py` 已有类似能力，可复用。
2. 对每个候选块，做三重过滤：
   - (a) 在 **35 份实机快照**里**恒定**（排除实时状态）
   - (b) 与 FX3 按 **−560 对齐**后**不同**（说明是机型差异字段）
   - (c) 位置落在 PDT 全量可写范围 `[0, 2253564)`
3. 另外做**反向搜索**：已知运行时 `available0=6, available1=7, available2=4`，
   在 PDT 里搜 `06 07 04 ??`（含各种间隔）以及 `{6, 7, 4}` 的任意排列组合。
4. 对命中的候选，给出：

   | PDT 偏移 | 4 字节值 | 快照是否恒定 | FX3 对齐值 | 与哪个 PRM 对应 | 置信度 |

**验收标准**：
- 候选表（若 0 命中，报 0 并说明用了哪几种判据）
- 每个候选都标注「是否可直接由 USB 单字节写覆盖」

---

### T5 ⭐ · 承接：3 个 PDT 候选的语义归属

上期定位到 3 个「FX30 全 `0x00`、FX3 全 `0x01`」的 7 字节组，35 份快照全恒定，**尚未实机写入**：

| FX30 偏移 | 长度 | FX30 | FX3（对齐） |
|---|---|---|---|
| `0x91700–0x9170D` | 14 | `00`×14 | `01`×14 |
| `0x918B9–0x918BF` | 7 | `00`×7 | `01`×7 |
| `0x91E90–0x91E96` | 7 | `00`×7 | `01`×7 |

**任务**：用 T1/T4 的结论去**解释这个「7」和「14」**。
- 已知 PRM 里有 `available0..3`（4 槽）和 `multi0..3`（4 槽）、`bracket_multi0..3`、`bracket_single0..3`
- 7 与 4 对不上。请查：驱动模式的**可注册列表长度**是不是 7？
  （提示：`DRIVE_MODE` 表有 17 项，但菜单可能只列一个子集；找找有没有常量 `7` 出现在遍历上界里）
- 若 7 是某个遍历上界 → 这 3 组很可能就是「列表成员/可见性」数组，优先级上调

**验收标准**：给出「7 的可能来源」的 1–3 种假设 + 各自的地址证据，或明确"未找到与 7 相关的遍历上界"。

---

## 4. 回报格式（每个任务单独一段）

```
### 任务 N · <一句话结论>

**结论**（只描述数据，不做语义断言）

**数据**
| 表 | ... |

**证据**
- 脚本：audit/tasks/T14_xxx.py → audit_raw/T14_xxx.txt
- 关键偏移/地址：...

**置信度**：✅ 已确证 / 🟡 有证据但未闭环 / ⬜ 未完成

**排除的其它可能**
- 假设X：❌ 因为...
- 假设Y：❌ 因为...

**未完成部分**（如实写，不要凑）
```

---

## 5. 与前期任务的关系

| 期 | 内容 | 状态 |
|---|---|---|
| 第三期 | `.bss` 靶点定位（需 dlopen） | 部分完成，靶点 `0x8220844/845` 已**排除** |
| 第四期 | FX30↔FX3 PDT 对齐 | ✅ **完成**，`−560`，3 个候选已定位 |
| 第五期 | 4 方向（跨机型普查/消费者/字段地图/UI 资源） | 部分完成 |
| **第六期（本期）** | **PRM 参数体系 / 可见性调用链 / restriction / PDT 副本** | 待做 |

**本期最想要的结果**：T4 命中 ⇒ 直接 USB 写，收工；T2 命中 ⇒ 知道该改哪个字段，再用我方已有的 dlopen 能力定点写；T1 命中但落在 `.bss` ⇒ 只能 dlopen，且要解决"启动时缓存"问题。

---

## 6. 已知的「不要浪费时间」清单

1. **不要**再用差分法找菜单列表（它是常量，差分筛不到 —— 第五期已证）
2. **不要**再写 `0x8220844/845`（已实机排除）
3. **不要**用 `dump_bkid_table.py` 找 `PRM_*` / `VAL_*`（另一套命名空间，0 命中）
4. **不要**把属性 id 数字直接当语义（id 空间会复用，`0x0C30` 有反例）
5. **不要**在没对齐的情况下比较 FX30 / FX3 同偏移字节（必须 −560）
6. **不要**相信 `T11_desc.py` 对所有 id 都有效（只解出过 `0x02AF`）
