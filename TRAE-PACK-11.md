# TRAE 任务包 · 第十一期：从「菜单值字符串」反查菜单选项枚举表

> 2026-10-25
> 上游：第十期（加密器 / ext4 / id 绑定）已全部完成
> 本期目标：**换切入角度** —— 不再从代码找，改为**从菜单值字符串反查引用它的表**

---

## 0. 全局边界

| 禁止 | 说明 |
|---|---|
| 不连接相机 | 纯离线 |
| 不改 `fw/` 下任何文件 | 只读；要写就复制到 `tmp01/` |
| 新脚本 `T21_` 前缀 | 放 `内部脚本（未公开）` |
| 不 git | 我方统一提交 |
| 不下结论 | 只回地址、偏移、表结构、计数 |
| 候选 > 100 立刻收窄 | 并说明收窄依据 |

Python：`$PY`
工作目录：`$REPO`

---

## 1. 已确证事实（直接用）

### 1.1 四机型 appFw.so 都已解出（明文，可直接分析）

| 机型 | 路径 | 大小 |
|---|---|---|
| **FX30** | `fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so` | 79,032,104 |
| **FX3** | `fw/fx3out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so` | 79,015,712 |
| A6700 | `fw/a6700out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so` | 89,027,992 |
| A7C2 | `fw/a7c2out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so` | 99,960,744 |

### 1.2 我方预检数据（不要重做）

**id 出现次数（u32 LE 全文件计数）**

| 机型 | `0x273`(连拍) | `0x271`(单张) | `0x192` | `0x1A3` | `0x0C30` |
|---|---|---|---|---|---|
| FX30 | **212** | 1737 | 156 | 16581 | 40 |
| FX3 | **212** | 1757 | 156 | 16581 | 40 |
| A6700 | 504 | 210 | 455 | 184 | 115 |
| A7C2 | 2092 | 552 | 2271 | 276 | 36 |

**FX30↔FX3 全文件分段相同率（delta=0）**：`0-16MB` 78.82%、`16-32MB` 36.27%、`32-48MB` 8.27%、`48-64MB` 43.21%、`64MB+` 57.88%；前 64 KB 最佳位移仅 31.49%。

⇒ **跨机型全量差分信噪比太低，不要做**（这是本期的前提结论）。

**关键字符串（FX30 与 FX3 完全一致）**

| 关键词 | FX30 | FX3 |
|---|---|---|
| `CONT_SHOOTING` | 3 | 3 |
| `DRIVE_MODE` | 7 | 7 |
| `BURST` | 4 | 4 |
| `burst` | 2 | 2 |

⇒ **不是字符串资源缺失**。

### 1.3 靶点字符串清单（FX30，`.rodata`，off == vaddr）

| 文件偏移 | 字符串 |
|---|---|
| `0x2FA4A68` | `DRIVE_MODE_CONT_SHOOTING_WITHOUT_OPTION` |
| `0x2FB4636` | `RECALL_SHOOT_SET_DRIVE_MODE_CONT_SHOOTING` |
| `0x2FB4660` | `RECALL_SHOOT_SET_DRIVE_MODE_CONT_SHOOTING_HI_PLUS` |
| `0x2FB4692` | `RECALL_SHOOT_SET_DRIVE_MODE_CONT_SHOOTING_HI` |
| `0x2FB46BF` | `RECALL_SHOOT_SET_DRIVE_MODE_CONT_SHOOTING_MID` |
| `0x2FB46ED` | `RECALL_SHOOT_SET_DRIVE_MODE_CONT_SHOOTING_LO` |
| `0x2FB6C0B` | `DRIVE_MODE_CONT_SHOOTING_LOW` |
| `0x2FB6C28` | `DRIVE_MODE_CONT_SHOOTING_LIMITED_HI` |
| `0x2FB6C4C` | `DRIVE_MODE_CONT_SHOOTING_LIMITED_MID` |
| `0x2FB6C71` | `DRIVE_MODE_CONT_SHOOTING_LIMITED_LOW` |
| **`0x3AA6535`** | **`VAL_setting_menu_drive_mode_DRIVE_MODE_CONT_SHOOTING`** ← **最关键** |
| `0x3AA66E6` | `VAL_setting_menu_drive_mode_DRIVE_MODE_CONT_SHOOTING_LIMITED` |
| `0x3AC97BF` | `VAL_setting_drive_mode_cont_shooting_..._OPTION_H` |
| `0x3AC9854` | 同上 `_OPTION_M` |
| `0x3AC989D` | 同上 `_OPTION_L` |
| `0x3C20D8F` | `DRIVE_MODE_CONT_SHOOTING_LIMITED_OPTION_HI` |
| `0x3C20DBA` | `..._OPTION_MID` |
| `0x3C20DE6` | `..._OPTION_LOW` |

### 1.4 已排除（不要再走）

| 路线 | 结论 |
|---|---|
| 选项池 `0x3202FC4` | 6 条目，0 引用 / 0 重定位，死数据 |
| `0x484F500` 表（408 槽） | 在 `.data`，304 非空 / 104 空；对象 16B `{ptr,id}`，**不含任何 PRM id（连 0x271 都不含）** |
| `.bss` 的 available/multi | 8 个回调**全返回 1**；`.bss` 槽无 `str` 写入点 |
| 0x02CF 键空间 | 用于 T1 属性注册表；本任务的绑定表用 **`0x00010000\|id`** |
| 布局资源 `LayoutMaster_Menu.uxc` | 3,636 B，仅坐标模板，不含菜单 id |

---

## 2. 任务

### T1 ⭐⭐⭐ 从 `VAL_setting_menu_drive_mode_*` 反查「菜单选项枚举表」

**思路**：这些字符串是"菜单项取值"的名字，必然被一张**枚举表**引用（表项通常是 `{name_ptr, value}`）。

**步骤**：

1. 取 `0x3AA6535`（连拍菜单值）等 1.3 表中的偏移，换算成 vaddr（`.rodata` off==va）
2. 全文件搜指向该 vaddr 的 **8 字节指针**（对齐 + 非对齐各一遍）
3. 对每个命中点，dump 前后 `±0x40`，识别表结构（建议同时按 8/16/24/32 四种步长试读）
4. 解出该表的**全部条目**：每一项的 `{字符串指针, 数值}`
5. **关键判据**：把这张表的全部"数值"列出来，看是否包含 `0x271`(单张) 与 `0x273`(连拍)

**产出**：

| 表基址 | 条目数 | 步长 | 每项结构 | 数值列（全部） | 是否含 0x271 / 0x273 |
|---|---|---|---|---|---|

**为什么这条最有希望**：`VAL_*` 是"菜单可选项的取值名"，它能直接告诉我们"菜单允许哪些值"。

---

### T2 ⭐⭐⭐ 在 FX3 上做同一件事，逐项对比

**步骤**：

1. 在 FX3 的 appFw.so 里定位同名同内容的字符串（前缀相同，偏移会不同）
2. 重复 T1 的步骤，得到 FX3 的那张表
3. 与 FX30 的表做**逐项对比**：

| 项 | FX30 | FX3 | 差异 |
|---|---|---|---|
| 表基址 | | | |
| 条目数 | | | |
| 是否含 0x273 | | | |
| 数值列 | | | |

**判据**：
- 若 FX30 的表**不含** 0x273 而 FX3 **含** ⇒ **这就是根因**，直接给"要加什么"的偏移
- 若两者都含 ⇒ 说明枚举没问题，问题在"显示列表"（转 T3）
- 若表结构完全不同 ⇒ 说明两机型走不同机制，需另行分析

---

### T3 ⭐⭐ 定位「菜单项的显示列表」（换判据）

**新判据**：显示列表的表项里应当**同时**能对应到「单张」与「连拍」。

**方法**：
1. 找出所有"含 0x271 且含 0x273"的**小范围结构**（±0x100 窗口内两者共存）
2. 对每个候选：dump 周围 0x200，判断是否 24B/项的定义表
3. 与 FX3 的同位置对照

**收窄要求**：候选 > 100 时，先按"窗口内同时含两者"过滤，再按"表长度 ≥ 8 项"过滤。

---

### T4 ⭐ `DRIVE_MODE_CONT_SHOOTING_WITHOUT_OPTION` 的语义

`WITHOUT_OPTION`（无选项）= 没有速度档的连拍。这个名字暗示存在**两种连拍形态**：
- 带速度档（`OPTION_H/M/L`）
- 不带速度档（`WITHOUT_OPTION`）

**任务**：找 `0x2FA4A68` 的引用（指针 + 代码中的 adrp/字符串地址使用），判断这个变体在什么条件下被选用。
**产出**：引用点清单 + 使用条件（若有明显常量比较就列出）。

---

## 3. 优先级与顺序

```
T1（FX30 枚举表） → T2（FX3 对照） → T3（显示列表） → T4（WITHOUT_OPTION）
```

T1+T2 是**同一条链路**，必须连着做；单独做 T1 价值不大。

---

## 4. 回报格式

```
### 任务 TN · <一句话结论>

**数据**（表：基址 / 条目数 / 步长 / 结构 / 数值列）

**证据**
- 脚本：内部脚本（未公开） → audit_raw/T21_xxx.txt
- 关键地址与偏移：

**置信度**：✅ / 🟡 / ⬜

**排除的其它可能**
- 假设X：❌ 因为…

**未完成部分**（如实写）
```

---

## 5. 绝对不要做

1. **不要**做 FX30↔FX3 全文件差分（分段相同率 8%–78%，信噪比太低，我方已试过）
2. **不要**再查选项池 `0x3202FC4`（已确认死数据）
3. **不要**再查 `0x484F500` 表里的 PRM id（已确认不含）
4. **不要**用 `0x02CF0000|id` 当唯一键前缀（还有 `0x00010000|id`）
5. **不要**改 `fw/` 下任何文件
6. **不要**下"这样就能改固件"的结论 —— 实机验证由我方执行
