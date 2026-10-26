# 任务包 · 第三期 · 「让隐藏连拍在菜单里显示出来」（只读静态，4 项）

> 发给执行方即可。全部为**只读静态分析**，不接相机、不改 `fw/`、不联网。
> **第二期任务包（`TRAE-PACK-2.md`）已交付**；本期是它的续集，
> 目标从「解释已有事实」转向「**找出下一个可动手的靶点**」。
>
> ⚠️ **本期所有工具脚本已由我方验证可跑**（见 §2 命令清单），
> 你可以直接用，不必重写。**新建脚本请放 `内部脚本（未公开）`，文件名带 `T12_` 前缀。**

---

## 0. 一句话目标

FX30 上**隐藏连拍已经开启成功**（写入设置区两个字节即可，冷启动后能连拍），
**但驱动模式菜单里不显示「连拍」这一项**。

**本期任务：定位菜单可见性的判定依据，并给出「改哪个靶点能让菜单显示连拍」的候选清单。**

---

## 1. 已确证的事实（不要重做，不要质疑）

### 1.1 连拍写入配方（实机验证通过）

```bash
python probe_drive_write.py 0x8EF80=0x01 0x91690=0x01
# → 拔电池 ≥30 秒冷启动 → 相机进入连拍，能正常连拍
# → 但菜单里不显示「连拍」，手动切换菜单即掉回
```

回滚：`python probe_drive_write.py 0x8EF80=0x00 0x91690=0x00`

### 1.2 设置区两个偏移的语义（本项目最重要的一条）

`0x8EF80` / `0x91690` 存的不是属性 id，而是**两张枚举表的 0-based 位置索引**：

| 偏移 | 枚举表 | 表基 vaddr | `0x00` | `0x01` | `0x02` | `0x05` | `0x08` | `0x09` | `0x0C` |
|---|---|---|---|---|---|---|---|---|---|
| `0x8EF80` | `EXTERN_VAL_DRIVE_MODE_*` | `0x41A0550` | SINGLE | **BURST** | BRACKET | RAW_BURST | SINGLE_SELF_2S | BURST_SELF_10S | SINGLE_SELF_5S |
| `0x91690` | `DRIVE_MODE_*` | `0x41A28F0` | 1_IMAGE_SHOOTING | **CONT_SHOOTING** | CONT_SHOOTING_LIMITED | SELF_TIMER | CONT_BRACKET | BRACKET_SINGLE | DRO_ADV_BRACKET |

枚举表结构（`.data.rel.ro`，16 字节/项）：

```c
struct enum_item { char *name; uint32_t id; uint16_t code; };
```

验证强度：12 份带标签快照（`dump/pdtl_{single,timer,bracket}_m1.bin`）**100% 自洽**；
27 份全量快照取值集合（`0x8EF80` ∈ {0,1,2,8,12}，`0x91690` ∈ {0,5,9}）全落在表索引范围内。

### 1.3 必须成对写

两字段是**同一设置的两层表示**，只写一个固件会回退。
反证：成对写入后，**固件自己把第三字段 `0x08DC14` 从 `0xCE` 联动改成 `0xCF`**。

### 1.4 已排除的路线（不要重走）

| 路线 | 排除依据 |
|---|---|
| `0x603/1` 读 BKID id | `cat=0x0603/cmd=0x0001` 下 BKID 族全部 `res=129` |
| 「payload 首字节是 namespace」 | `cat=0x1001/cmd=0x603` 对**任何** id（含边界）返回固定 `01 02 00 10`，是 ack 不是属性值 |
| 改 `.bss` 运行时内存 | 需要 dlopen 载荷；PDT 侧已能达成同样效果，先不碰 |

### 1.5 关键 BKID id（已从注册表解出）

| id | 名字 | 推测角色 |
|---|---|---|
| `0x02AF` | `setting_menu_drive_mode` | 菜单项本体 |
| `0x0272` | `DRIVE_MODE_1_IMAGE_SHOOTING` | 单张 |
| `0x0273` | `DRIVE_MODE_CONT_SHOOTING` | **连拍** |
| `0x04B6` | (drive_mode 邻项) | — |
| `0x04B8` | `setting_drive_mode_cont_shooting` | 连拍设置 |
| `0x04BA` | `cont_shooting_limited` | 连拍限张 |
| `0x0C30`–`0x0C32` | `registration_drive_mode0..2` | **注册项** |
| `0x0C33` | `registration_drive_mode3` | 注册项 |
| `0x0C2C`–`0x0C2E` | `registration_drive_mode_available0..2` | **可用性标志** ⭐ |
| `0x0C3B` | `registration_drive_mode_available3` | 可用性标志 ⭐ |
| `0x02B1`/`0x02B3`/`0x02B5` | `dial_hi/mid/lo_in_electric_shutter` | 连拍速度档 |

⭐ **`registration_drive_mode_available*` 是头号嫌疑** —— 每个 drive mode 一个
「可用」标志，菜单过滤极可能读它。

---

## 2. 环境 + 已验证命令清单

### 2.1 环境自检（先跑这行，通不过就停下回报）

```bash
cd $REPO
PY="/path/to/python3.11"
"$PY" -c "import elftools, capstone; print('deps OK')"
```

缺依赖**停下回报**，不要自行安装。

### 2.2 固件路径

```
fw/out/firmware.tar_unpacked/0700_part_image/dev/nflasha15_unpacked/lib/appFw.so
```

（FX30，79 MB，ELF64 AArch64）

### 2.3 已验证可跑的命令（直接复制用）

**① 解出任意属性 id 的 `.bss` 目标地址（10 个访问器桩全解）**

```bash
cd <内部脚本目录，未公开>
PY="/path/to/python3.11"

"$PY" T11_prop_vis.py ids 0x2AF,0x272,0x273,0x4B6,0x4B8,0x4BA,0x0C2C,0x0C2D,0x0C2E,0x0C33,0x0C30,0x0C31,0x0C32,0x0C3B
```

输出形如：

```
## id 0x0272  记录 0x0403C250  (10 个访问器)
   [0] 0x02878000  adrp x0, #0x8230000 ; ldr w0, [x0, #0xa14] ; ret
        -> bss: 0x8230A14(ldr)
   ...
```

**② 查 BKID 名字**

```bash
"$PY" T11_menu.py bkid --pat registration_drive_mode
"$PY" T11_menu.py bkid --name PRM_setting_menu_drive_mode
```

**③ 找「把 BKID id 当立即数传给框架函数」的消费者** ⭐ 关键

```bash
"$PY" T11_iduse.py 0x0C2C,0x0C2D,0x0C2E,0x0C33
"$PY" T11_iduse.py --ctx 0x0C2C
"$PY" T11_cons.py 0x0C2C,0x0C2D,0x0C2E,0x0C33
"$PY" T11_cons.py --full 0x0C2C
```

**④ 找引用某个 `.bss` 地址的代码**

```bash
"$PY" T11_xscan.py 0x8230A28,0x8230A2C --desc
"$PY" T11_prop_vis.py xref 0x8230A28,0x8230A2C
"$PY" T11_xscan.py xref --all
```

**⑤ 定位属性记录（表格非等距，不能按等距网格推）**

```bash
"$PY" T11_xref.py rec 0x0C2C,0x0C2D,0x0C2E,0x0C33
```

**⑥ 数据段里的 u32 序列 / 成对表 / 上下文**

```bash
"$PY" T11_arr.py 0x19,0x21,0x1D,0x21,0x16
"$PY" T11_arr.py --stride 16 0x19,0x21,0x1D
"$PY" T11_pair.py --find 0x02AF
"$PY" T11_ctx.py 0x02AF
"$PY" T11_dump.py 0x02F8D480 0x100
"$PY" T11_dump.py --q 0x04130F98 0x90
```

**⑦ 字符串 / 直接寻址 / 调用目标 / 反汇编**

```bash
"$PY" T11_strs.py "scr7140"
"$PY" T11_xaddr.py 0x03176008
"$PY" T11_ref.py 0x04130F98,0x041A28F0
"$PY" T11_bl.py 0x029675B4,0x029675EC
"$PY" T11_xref.py dis 0x401234 120
"$PY" T11_prop_vis.py func 0x401234
```

### 2.4 技术要点（务必按这个来，否则会踩坑）

* **`.data.rel.ro` 里的函数指针在文件内是 0**，必须解析 `.rela.dyn` 的
  `R_AARCH64_RELATIVE`（type 1027）用 `r_addend` 还原。
* **不要用 capstone 全量反汇编**（`.text` 约 2000 万条指令，太慢）。
  用 `T11_xscan.py` / `T11_xref.py` 的**裸位域解码 + 寄存器常量传播**。
* **AArch64 `adrp+add` 的 ±4GB 页内寻址**：`adrp` 给页基址（`pc & ~0xFFF` + imm），
  `add`/`ldr` 立即数要按指令语义还原，**不能直接搜立即数**。
* 属性记录网格**并非完全等距**（实测 `0x0C2E` 与 `0x0C30` 之间有 `0xB0` 缺口），
  要用 `T11_xref.py rec` 的扫描法，不要按等距网格推。

---

## 3. 任务清单

| # | 任务 | 命令入口 | 预计 |
|---|---|---|---|
| 1 | `registration_drive_mode_available*` 的 `.bss` 地址 + 谁在读 | `T11_prop_vis.py ids` + `T11_iduse.py` + `T11_cons.py` | 40 min |
| 2 | 菜单项构造链：谁决定「显示/隐藏某 drive mode」 | `T11_iduse.py` + `T11_xscan.py` + `T11_desc.py` | 60 min |
| 3 | `registration_drive_mode0..3` 与 `available0..3` 的配对关系 | `T11_prop_vis.py ids` + `T11_xscan.py` | 40 min |
| 4 | 连拍速度档 `dial_hi/mid/lo_in_electric_shutter` 的角色 | `T11_prop_vis.py ids` + `T11_iduse.py` | 30 min |

**按顺序做。每做完一个先回报，再做下一个。**

---

### 任务 1 · 可用性标志：地址 + 消费者 ⭐最高价值

**我方已解出的部分（你要在此基础上继续，不要重做）**：

`registration_drive_mode_available0..3` 的 `.bss` 地址**严格等距 `0x4`**：

| id | 名字 | 主 `.bss`（getter 读） | setter 读 | setter 写 | 副本 A | 副本 B |
|---|---|---|---|---|---|---|
| `0x0C2C` | `available0` | `0x83461A4` | `0x83462A4` | `0x8346290` | `0x894BF4C` | `0x8220C64` / `0x8220D64` |
| `0x0C2D` | `available1` | `0x83461A8` | `0x83462B8` | `0x83462A4` | `0x894BF60` | `0x8220C68` / `0x8220D78` |
| `0x0C2E` | `available2` | `0x83461AC` | `0x83462CC` | `0x83462B8` | `0x894BF74` | `0x8220C6C` / `0x8220D8C` |
| `0x0C33` | `available3` | `0x8346300` | `0x8346360` | `0x83462FC` | `0x894BFA8` | `0x8220DC0` / `0x8220E30` |

⚠️ **注意 `0x0C33` 不在同一等距序列里**：
`0x83461A4 → 0x83461A8 → 0x83461AC` 步长 `0x4`，
但下一个是 `0x8346300`（差 `0x150`），中间还有 `0x83462A4/A8/AC`、`0x83462BC`、
`0x8346290/294` 等另一组连续地址。
⇒ **「available3」很可能属于另一组注册项**（`0x0C33` 是 `registration_drive_mode3`
的 available 标志，而 `0x0C30`–`0x0C32` 是 `registration_drive_mode0..2` 的）。
**你要验证这个分组假设**（见任务 3）。

**你要回答**：

1. `0x0C2C`–`0x0C33` 各自的 `.bss` 地址是否与上表一致？
   **独立复核一遍**（用 `T11_prop_vis.py ids`），并补全我未列出的访问器槽。
2. 四个地址是否相邻（像数组）？**已确认 3 个等距、1 个脱离**，请找出分组规则。
3. **谁在读这些 `.bss`**？
   - 走 `T11_xscan.py` 找对 `.bss` 地址的直接 `ldr`/`str` 引用；
   - 走 `T11_iduse.py` / `T11_cons.py` 找「把 id 当立即数传给框架函数」的消费者。
   - **两条路都要走** —— 属性访问器表是**模板**，运行时框架按 id 查表调用桩，
     所以消费者**不一定**体现为对 `.bss` 的直接引用。
   - 已验证命令示例：`T11_iduse.py 0x0C2C,0x0C2D` → **命中 68 处**。
4. 对每个消费者，给出：**所在函数起止 vaddr** + **反汇编片段**，
   并判断它是在**读**可用性（`ldr` + `cmp` + 分支）还是在**写**。

**关于 `T11_cons.py` 的已知局限**（我方已修一处，仍有残留）：

- `func_start` 探测已修正序言掩码（`0x7FC07FFF` → `0xFFC07FFF`），
  现在能正确回溯到 `stp x29,x30` 序言。
- **但 leaf 函数（无序言）仍会把命中地址本身当作 `func_start`** ——
  这是**正常现象**，不是 bug。判断时以反汇编为准。
- `后续分支` / `比较` 计数常为 0，因为框架调用是「取 id → 查表 → 调桩」，
  真正的比较发生在**被调用的桩里**。**别据此认为「没有分支」** ——
  要顺着 `T11_bl.py` 追进桩函数里看。

**验收**：

- 4 个 id 的 `.bss` 地址表（≥1 条反汇编证据）
- 至少 1 个消费者的函数边界 + 反汇编；**若找不到任何消费者，明确说「此路不通」并给出排除依据**

**反面判据**：若发现 `available*` 的 `.bss` 地址与 `0x0272`/`0x0273`（drive mode 本体）
的 `.bss` 地址（已知 `0x8230A14`–`0x8230A2C` 段）**完全不在同一区段**，
那么「可用性标志决定菜单显示」这个假设**不成立** —— 回报并排除。

---

### 任务 2 · 菜单项构造链

**已知**：

- FX30 `.rodata` 里有 `0x1A2 → 0x1A3` 这样的 drive mode **菜单项 id 序列**，共 3 处。
- `T11_desc.py` 能 dump「功能 id → 80 字节描述符」，描述符表 3 张：
  表1 上界 `0x1A3` 全局 `0x477B5A0`；表2 上界 `0x4B7` 全局 `0x4783120`；
  表3 上界 `0x1045` 全局 `0x46FAB70`。

**你要回答**：

1. 用 `T11_desc.py 0x02AF 0x04B6 0x04B8 ...` dump 这些 id 的描述符，
   **描述符里有没有「可见性 / 可用性 / capability」字段**？
   把 80 字节按 u32 展开，逐字段说明。
2. `0x1A2`/`0x1A3` 这类**菜单项 id** 与**属性 id**（`0x02AF` 等）是**同一套编号**吗？
   用 `T11_desc.py --range 0x1A0 0x1A8` 和 `T11_ctx.py 0x1A2` 对照。
3. 找到**引用描述符表的菜单构造函数**（用 `T11_xaddr.py` 找表头 `0x477B5A0` 的引用，
   再用 `T11_bl.py` 追调用者），在其反汇编里找**过滤分支**：
   - 分支条件读的是哪个地址？
   - 那个地址对应哪个 id / 哪个 `.bss`？

**验收**：

- 描述符 80 字节的字段拆解（哪些字段是 flag、哪些是 id）
- 菜单构造函数 vaddr + 过滤分支反汇编 ≥2 条
- **明确指出「菜单可见性由什么决定」**，或明确说「未找到，此路不通」

---

### 任务 3 · `registration_drive_mode0..3` ↔ `available0..3` 的配对

**你要回答**：

1. `0x0C30`–`0x0C33`（`registration_drive_mode0..3`）的 `.bss` 地址。
2. 它们与 `available0..3`（`0x0C2C`–`0x0C33`）的地址**是不是交错排列**？
   （例如 `avail0, reg0, avail1, reg1, ...`）
   **画一张地址-名字对照表**。
3. `registration_drive_mode*` 里存的**值**是什么语义？
   - 用 `T11_xscan.py` 找谁写它；
   - 用 `T11_bl.py` 追它的生产者函数；
   - 判断它是不是**「当前选中的 drive mode 序号」**（若是，
     那 `0x8EF80` 的枚举索引与它的关系就清楚了）。
4. **关键**：如果 `registration_drive_mode*` 就是当前模式，
   那菜单显示连拍需要满足什么条件？
   —— 是 `available*` 里对应项为 1？还是 `registration_drive_mode*` 匹配某个值？

**验收**：

- 地址-名字对照表（含交错关系）
- `registration_drive_mode*` 的语义判定（✅确证 / 🟡推测，附反汇编）
- **一句话回答「菜单显示连拍的条件是什么」**

---

### 任务 4 · 连拍速度档

**你要回答**：

1. `0x02B1`/`0x02B3`/`0x02B5`（`dial_hi/mid/lo_in_electric_shutter`）的 `.bss` 地址。
2. 它们和 `0x0273`（`DRIVE_MODE_CONT_SHOOTING`）的 `.bss` 地址**是否相邻**？
   （相邻 ⇒ 同一结构体里的不同字段 ⇒ 速度档属于连拍模式的一部分）
3. 谁读它们？给出反汇编。
4. 附带：FX30 固件里 `customFps_Elec_*` **零命中**（A6700 有）。
   用 `T11_strs.py "customFps"` 和 `T11_strs.py "Elec"` 确认，
   并报告 FX30 里**最接近的替代命名**是什么。

**验收**：3 个 id 的 `.bss` 地址 + 相邻性判定 + 消费者反汇编。

---

## 4. 回报格式（每条照抄这个结构）

```
### 任务 N · <一句话结论>

**结论**：（是什么 / 不是什么）

**地址**：
| 名字 | id | .bss 地址 | 记录 vaddr |
|---|---|---|---|
| ... | ... | ... | ... |

**证据**：
（反汇编片段 ≥2 条，或数据表片段。给出 vaddr + 指令原文）

**置信度**：✅确证 / 🟡推测 / ⬜未找到

**排除的其它可能**：（你试过但排除的路径）
```

最后必须给这张总表：

**「要让菜单显示连拍，最可能需要改什么」**

| 候选靶点 | 类型 | 能否从 USB 侧写到 | 证据强度 | 备注 |
|---|---|---|---|---|
| 例：`0x8230A28` | `.bss` u32 | ❌ 需 dlopen 载荷 | 🟡 | ... |
| 例：PDT `0x8EF80` | 设置区字节 | ✅ 可写 | ✅ | 已验证有效但菜单不显示 |

**如果某条线索走不通，明确写「此路不通」并给出排除依据** ——
这本身就是有价值的结论，**不要硬凑**。

---

## 5. 全局禁止

- ❌ 不要连接相机、不要运行任何 `probe_*.py`
- ❌ 不要修改 / 删除 `fw/` 下任何文件
- ❌ 不要修改 `内部脚本（未公开）` 下**既有**脚本（发现 bug 就回报，不要自己改判据）
  —— 新建脚本放 `内部脚本（未公开）` 下，文件名带 `T12_` 前缀
- ❌ 不要 git commit / push
- ❌ 不要下结论性判断（如「说明 A7C2 与 FX30 同源」）—— 只回数字和反汇编证据
- ❌ 不要输出固件二进制片段或备份数据

---

## 6. 预期结果对照（用于自检，**不是**让你下结论）

| 任务 | 期望产出 | 备注 |
|---|---|---|
| 1 | 4 个 available id 的 `.bss` 地址 + 消费者 | 若「消费者」找不到，说明要走 id-immediate 路线（`T11_iduse.py`） |
| 2 | 描述符字段拆解 + 菜单构造函数 | 若描述符里没有 flag 字段，说明可见性不在描述符里，转任务 1/3 |
| 3 | 地址对照表 + `registration_drive_mode*` 语义 | 若地址交错 ⇒ 是数组 ⇒ 与索引制对应 |
| 4 | 3 个速度档 id 的地址 + 相邻性 | 若与 `0x0273` 不相邻 ⇒ 速度档与连拍模式是两套东西 |

**关于「菜单里显示」的现实预期**（先说清楚，避免你走错方向）：

菜单显示很可能**不是**由设置区字节决定，而是由**固件内部的可用性注册表**决定
（`registration_drive_mode_available*` 那一族）。
如果确认是 `.bss` 侧的标志，那**从 USB 侧改不了** —— 需要走 dlopen 载荷写内存。
但**这一步由我方来做**，你只负责**定位靶点 + 给出地址**。

⇒ **你的交付物是「靶点坐标」，不是「可用的写入脚本」。**

---

## 7. 与前两期的关系

| 期 | 状态 | 说明 |
|---|---|---|
| 第一期（`TRAE-PACK.md`） | ✅ 已完成 | 跨机型指令级对齐、符号 diff |
| 第二期（`TRAE-PACK-2.md`） | 任务 1–4 待做，任务 5 已可结案 | 任务 5（`.bss` ↔ PDT `0x8EF80` 映射）**答案已给出**：PDT 是真值源，两个偏移存的是枚举表位置索引 |
| **本期（`TRAE-PACK-3.md`）** | 🔄 进行中 | 菜单可见性定位 |
