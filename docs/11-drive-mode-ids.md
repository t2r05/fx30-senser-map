# 驱动模式的 ID 体系：名称 → 数字（三机型对照）

> 本文解决一个此前卡住很久的问题：**`BKID_APP_setting_*` 这类名称，怎么变成能读写的数字 ID？**
> 全部结论来自 `appFw.so` 的离线静态分析（FX30 6.00 / FX3 / A6700 2.00），无实机写入。

---

## 一、命名表：16 字节/项，约 25,167 条

`BKID_APP_setting_drive_mode_cont_shooting` 这个字符串在 `.text` 里 **`adrp+add` 引用 0 处**——它不作为代码字面量被直接引用。改搜「指向该字符串的 8 字节指针」，在 `.data.rel.ro` 命中：

```
0x0414F7A8  0000002A000004B7
0x0414F7B0  0000000003BD195F   ← name_ptr（指向 .rodata 里的字符串）
0x0414F7B8  0000002D000004B8   ← id = 0x04B8
```

表结构：

```c
struct bkid_entry {   // 16 字节
    const char *name;   // +0x00
    uint32_t    id;     // +0x08
    uint32_t    meta;   // +0x0C
};
```

全表约 **25,167 条**。扫描脚本：`dump_bkid_table.py <机型> <关键字>`。

### 顺手解释一个老谜团

描述符访问器 `0x1DBCEE0` 把 id 空间切成三段（`id <= 0x04B7` / `<= 0x1045` / `<= 0x1A3`）。
**第一段上界 `0x04B7` 正好是 BKID 表里紧邻连拍的前一项**，连拍 `0x04B8` 刚好越界。

⇒ BKID id 与描述符 id **共用同一套编号空间**，不是两套体系。

> 与本仓库早期记录的「`BKID = 1208`」完全一致：`1208 = 0x4B8`。
> 受限版 `1210 = 0x4BA`。两条独立路径算出同一个数。

---

## 二、三机型 id 对照

| 用途 | FX30 (6.00) | FX3 | A6700 (2.00) | **A7C2 (2.01)** |
|---|---|---|---|---|
| `setting_menu_drive_mode` | `0x02AF` | `0x02AF` | `0x02B4` | — |
| `drive_mode_dial_hi_plus_in_electric_shutter` | **无** | **无** | **`0x12D5`** | **`0x12D1`** |
| `..._dial_hi_in_electric_shutter` | `0x02B1` | `0x02B1` | `0x02B6` | `0x02B6` |
| `..._dial_mid_in_electric_shutter` | `0x02B3` | `0x02B3` | `0x02B8` | `0x02B8` |
| `..._dial_lo_in_electric_shutter` | `0x02B5` | `0x02B5` | `0x02BA` | `0x02BA` |
| `setting_drive_mode_cont_shooting` | **`0x04B8`** | **`0x04B8`** | `0x04B9` | `0x04B9` |
| `..._cont_shooting_limited` | `0x04BA` | `0x04BA` | `0x04BB` | `0x04BB` |
| `setting_drive_mode_self_timer` | `0x04BE` | `0x04BE` | `0x04BF` | `0x04BF` |
| `shoot_set_registration_drive_mode_available0/1/2/3` | `0x0C2C`/`2D`/`2E`/`33` | 同左 | `0x0BE4`/`E5`/`E6`/`EB` | `0x0BE8`/`E9`/`EA`/`EF` |
| `shoot_set_registration_drive_mode0/1/2/3` | `0x0C30`/`31`/`32`/`3B` | 同左 | `0x0BE8`…`0x12F4` | 同 A6700 附近 |

**FX30 与 FX3 逐位相同**；A6700 / A7C2 是另一套编号，并多出 `HI_PLUS` 一档。

### ⚠️ 位移不是统一的「+5」（2026-10-24 修正）

早期本文写「A6700 整体位移」，**不准确**。四机型实测下来是**分段位移**：

| 区段 | FX30 → A6700/A7C2 | 证据 |
|---|---|---|
| `0x02B1` 族（电子快门拨盘位） | **+5** | `02B1→02B6`、`02B3→02B8`、`02B5→02BA` |
| `0x04B8` 族（驱动模式设置项） | **+1** | `04B8→04B9`、`04BA→04BB`、`04BE→04BF` |
| `0x0BE4` 族（注册可用槽） | A7C2 比 A6700 **+4** | `0BE4→0BE8` |
| `0x12D5`（HI_PLUS 设置项） | A7C2 比 A6700 **−4** | `12D5→12D1` |

**读法**：第二代在 `0x02B1` 与 `0x04B8` 之间**插入了 4 个新 id**（所以 02B1 族被推后 5 位、
04B8 族只被推后 1 位），之后又发生了一次重排 —— A7C2 在 `0x0BE4` 处多了 4 个、在 `0x12D1` 处少了 4 个。

⇒ **不要用单一偏移量做跨机型 id 换算**，必须逐键对照。工具见
[`tools/offline/bkid_drive_compare.py`](../tools/offline/bkid_drive_compare.py)。

各机型含 `drive_mode` 的 BKID 条目：FX30/FX3 **273 条**、A6700 **300 条**、A7C2 **504 条**（大小写不敏感匹配）。
FX30 与 FX3 的独占条目均为 **0**。

---

## 三、三代「隐藏」的建模方式根本不同

这是本文最重要的结论。找「连拍的支持开关」一直找不到，原因是 **FX30 那一代没有能力位**。

> **2026-10-24 修正**：早期这里写的是「两代」，A7C2 2.01 解包后确认是 **三代**。
> A7C2 同时具备前两代的痕迹，并新增 `EXPANDED_OPTIONS` 与 `NON_LIMITED` 两个抽象层。

| | 第一代 FX30 / FX3 | 第二代 A6700 (2.00) | **第三代 A7C2 (2.01)** |
|---|---|---|---|
| 机制 | **枚举 + 受限降级** | **限制原因枚举** | 限制原因 + **扩展选项 + 非受限标记** |
| 关键常量 | `DRIVE_MODE_CONT_SHOOTING` → `_CONT_SHOOTING_**LIMITED**_HI/MID/LOW` | `DRIVE_MODE_**LIMIT**_CONT_SHOOTING_*` | 上述两者 **+** `DRIVE_MODE_**EXPANDED_OPTIONS**_LIMIT_CONT_SHOOTING_*` **+** `DRIVE_MODE_**NON_LIMITED**` |
| 命名语义 | `_LIMITED` 是**后缀** = 受限的**模式值** | `LIMIT_` 是**前缀** = 限制**原因**枚举 | 再加一层「扩展选项」描述可选集合 |
| 用户可见 | 菜单始终可选中，运行时自动降级 | 弹 `CAUTION_ID_FACTOR_CAM_SET_DRIVE_MODE_*_MSG` | 同上，且选项集可动态扩展 |
| 拨盘层 | 无 | `DRIVE_MODE_DIAL_POS_*` | 同左 |

第三代新增层的条数（大小写不敏感统计）：

| 建模层 | FX30 | FX3 | A6700 | A7C2 |
|---|---|---|---|---|
| `REGISTRATION_DRIVE_MODE_*` | 33 | 33 | 34 | 34 |
| `EXPANDED_OPTIONS_*` | **0** | **0** | **0** | **26** |
| `NON_LIMITED` | **0** | **0** | **0** | **1** |
| `LIMIT_CONT_SHOOTING_HI_PLUS/HI/MID/LO` | **0** | **0** | **0** | **4** |

A7C2 的限速四档 id：

```
SETTING_DRIVE_MODE_LIMIT_CONT_SHOOTING_HI_PLUS = 0x13FB
SETTING_DRIVE_MODE_LIMIT_CONT_SHOOTING_HI      = 0x13FD
SETTING_DRIVE_MODE_LIMIT_CONT_SHOOTING_MID     = 0x13FF
SETTING_DRIVE_MODE_LIMIT_CONT_SHOOTING_LO      = 0x1401
SETTING_DRIVE_MODE_LIMIT_CONT_SHOOTING         = 0x19DF
```

⇒ **FX30 6.00（2025 年固件）仍然没有这一层**，不是版本老，是 **Cinema Line 分支没走这条抽象**。

A6700 独有的 `DRIVE_MODE_*` 常量（`LIMIT_*` / `DIAL_POS_*` / `CAUTION_ID_*`）**FX30 与 FX3 一条都没有**。

### 3.1 FX30 缺的是「设置项的消费者」，不是功能

| 机型 | `DRIVE_MODE_CONT_SHOOTING_OPTION_HI_PLUS`（选项枚举） | `dial_hi_plus_in_electric_shutter`（设置项） |
|---|---|---|
| FX30 | ✅ 有（`0x0001`） | ❌ **没有** |
| FX3 | ✅ 有 | ❌ 没有 |
| A6700 | ✅ 有 | ✅ `0x12D5` |
| A7C2 | ✅ 有 | ✅ `0x12D1` |

FX30 的固件**认识** `HI_PLUS` 这个选项，但**没有**「电子快门 HI+ 拨盘位」这个设置项。

⇒ 把 A6700 的 `0x12D5` 写进 FX30 的 PDT **不会生效** —— FX30 里没有这个 id 的消费者。
这是「消费者不存在」，不是「值没写对」。

---

## 四、`cmp #imm` 精确分布（`.text` 全量）

| 立即数 | FX30 | FX3 | A6700 |
|---|---|---|---|
| `0x1A2` 单张 | **0** | **0** | 2 |
| `0x1A3` 连拍 | **6** | **6** | 2 |
| `0x1A4` 自拍定时 | **0** | **0** | 1 |
| `0x1A5` | 21 | 21 | 3 |
| `0x1AB` 连拍受限 | **1** | **1** | 2 |

**FX30/FX3 对单张和自拍定时零特判，唯独连拍被显式判断 6 处。** A6700 四个模式对称——因为连拍已拆成 HI_PLUS/HI/MID/LO 四个普通枚举成员。

`0x1A3` 的 6 处中，`0x1DBCF4C` 是描述符访问器的表范围上界（`id <= 0x1A3`），不算特判。其余三处连在一起的，反汇编为「若驱动模式 == 连拍，则上报事件 `0x13F7`」，也不是门控。

---

## 五、数据层也排除了「列表漏项」

如果菜单是 id 数组，FX30 里应该出现 `0x1A2 → 0x1A4` 跳过 `0x1A3` 的序列。实测 `.rodata` 里 `0x1A2 → 0x1A3` 连续序列：

| 机型 | 命中数 |
|---|---|
| FX30 | **3** |
| FX3 | **3** |
| A6700 | 4 |

⇒ **菜单列表没有漏掉连拍。** 数据层是完整的。

---

## 六、其余排除项

| 检验 | 结果 |
|---|---|
| `.text` 里 `cx96701` / `cx94701` / `cx89501` 型号串 | **0 命中** → 机型识别不走字符串 |
| 整个 `nflasha15` 树里型号串 | **0 命中** → 由 CP 芯片侧提供，appFw 只认数字 ID |
| FX30 独有 `DRIVE_MODE` 常量 | **0 条** |
| FX30 独有 `AVAILABLE`/`LIMIT`/`ENABLE` 类常量 | **0 条**（FX30/FX3 各 948，A6700 1142） |
| `fx30` 与 `fx3` 的 `.dynsym` | 801 vs 800，**FX3 独有 0 个**，FX30 多的 1 个是 `AiDictionaryIF::GetInstance()` |

**FX3 有连拍、FX30 没有，但 FX3 零独有导出符号** ⇒ 不存在「连拍专属模块」，连拍不体现在任何 API 上。

---

## 七、`.rodata` 里的枚举名（值即 id）

`diff3_wb/registry_FX30.tsv`（843 条，FX30/FX3/A6700 三份**零差异**）：

| id | 名称 |
|---|---|
| `0x272` | `DRIVE_MODE_1_IMAGE_SHOOTING`（单张） |
| `0x273` | `DRIVE_MODE_CONT_SHOOTING`（连拍） |
| `0x274` / `0x275` / `0x276` / `0x277` | 其余驱动模式 |
| `0x278` | `DRIVE_MODE_SELF_TIMER`（自拍定时） |
| `0x284` | 自拍定时变体 |
| `0x286`–`0x291` | 连拍速度档 |

**注册表 843 条在 FX30 与 FX3 之间零差异**（同 ID 但名称不同：0 条；双方独有 ID：0 条）。

---

## 八、由本文推出的下一步

| 结论 | 指向 |
|---|---|
| FX30 ≡ FX3（名称/常量/注册表/符号全同），`.text` 反而**大** 11,128 字节 | 连拍**不是功能缺失** |
| 指令级双侧对称差分：A 独有 19.41% / B 独有 19.38%，净差 10,848 ≈ `.text` 尺寸差 | 是**函数级重排**，同一批代码搬家，不是逐函数改写 |
| 无任何「开关」常量、无独有符号、无缺项 | 门控是**运行时读某个值后分支** |

⇒ 目标从「找能力位」改为「**找运行时那个值的存放地址**」，见 [`12-property-accessor-table.md`](12-property-accessor-table.md)。
