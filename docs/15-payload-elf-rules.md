# 15 · dlopen 载荷的 ELF 结构规则

> **问题**：把自制的 `.so` 写进 `/tmp/jiritsu/libJit.so` 后，相机从 USB 消失、服务进程 `im.elf` 崩溃。
> **原因**：不是代码写错了，是 **ELF 结构不合法**。这一页把踩过的坑与已验证的结构列清楚。

核验日期：2026-10-24。数据来源：本项目 FX30 实机 + 反汇编，以及
[nolan2628/Sony-ZVE-10-Camtool](https://github.com/nolan2628/Sony-ZVE-10-Camtool) 在 ZV-E10 上公开的、可用的最小载荷（`build_payload_v2.py` + `README`）。

---

## 一、五条铁律

| # | 规则 | 违反后的症状 |
|---|---|---|
| 1 | **`.dynamic` 必须落在可写（RW）的 `PT_LOAD` 内** | 写文件即崩，相机从 USB 消失 |
| 2 | **必须有 `PT_GNU_STACK`** | 同上，进程在 `dlopen` 阶段死 |
| 3 | **`p_align` 要满足 `vaddr ≡ off (mod align)`** | `dlopen` 干净失败（返回 `0x10000000`） |
| 4 | **构造函数入口的指令集位必须与代码模式一致**（ARM32：Thumb `|1` / ARM `|0`） | CPU 用错模式解码，立即 SIGSEGV |
| 5 | **不要带 `PT_GNU_RELRO`** | `mprotect` 把 `.dynamic` 同页设只读，连带打掉同页 `.bss` |

### 为什么第 1 条是致命的

glibc 在 `dlopen` 时会往 `.dynamic` 段回写指针（`l_info` 表项、`DT_DEBUG` 等）。若该段被映射成只读，写即 SIGSEGV。ZV-E10 那边的原话：

> 「`.dynamic` 若落在只读段，glibc `dlopen` 往里写 `l_info`/`DT_DEBUG` 时 **SIGSEGV**，im.elf 当场死、相机从 USB 消失。10-17 那个 528B `libJit.so` 就是这个病，从来没成功过。」

### 为什么第 5 条容易被忽略

默认链接器会给 RW 段加 `PT_GNU_RELRO`。看着人畜无害，但 `_dl_protect_relro` 是按**页**做 `mprotect` 的：

```
ALIGN_DOWN(relro_vaddr, 4096) .. ALIGN_DOWN(relro_vaddr + relro_memsz, 4096)
```

只要 `.dynamic` 与 `.bss` 落在同一页（4 KB），整页变只读。**纯函数载荷（全栈变量 + rodata）不会踩；一旦用任何全局缓冲区就必崩** —— 这类 bug 在事后极难定位，因为「大部分时候是好的」。

---

## 二、已验证的最小结构

### ARM32（ZV-E10，440 B 载荷的实际布局）

```
ph0  PT_LOAD  R+X   : 0 .. code_end          （ELF 头 + hash/sym/str + 代码）
ph1  PT_LOAD  R+W   : code_end .. +0x38      （.dynamic，vaddr 偏移一页）
ph2  PT_DYNAMIC     : 指向 ph1
DT_INIT = ctor_vaddr | (thumb ? 1 : 0)
e_flags = 0x05000200
```

关键点：**`.dynamic` 单独占一页**（`dyn_vaddr = seg1_end + 0x1000`），保证与文件偏移同余。

### AArch64（本项目 FX30，2,064 B）

```
PHDR      off=0x040  vaddr=0x0040    filesz=0x188   R
LOAD      off=0x000  vaddr=0x00000   filesz=0x29c   R
LOAD      off=0x29c  vaddr=0x1029c   filesz=0x050   RX
LOAD      off=0x2f0  vaddr=0x202f0   filesz=0x0f8   RW   ← .dynamic 在此
DYNAMIC   off=0x2f8  vaddr=0x202f8   filesz=0x0f0   RW
GNU_STACK off=0      vaddr=0         memsz=0        RW
```

- 无 `PT_GNU_RELRO`
- RW 段 `memsz == filesz`（无 `.bss` 零填充）
- `vaddr - off = 0x20000`，`p_align = 0x10000` → 同余成立
- `DT_INIT_ARRAY = 0x202F0`，槽内是 `R_AARCH64_RELATIVE`，`addend = 0x1029C`

> **AArch64 没有 `e_flags` 的 EABI 约定**（`e_flags = 0` 是正常的）。ARM32 的 `0x05000200` 是 `EF_ARM_EABI_VER5 | soft-float`，AArch64 不需要。

---

## 三、`DT_INIT` 还是 `DT_INIT_ARRAY`

| | ZV-E10（ARM32 手写 ELF） | 本项目（AArch64 真实链接器） |
|---|---|---|
| 采用 | `DT_INIT` | `DT_INIT_ARRAY` |
| 理由 | 手拼 ELF 时 `INIT_ARRAY` 还要额外造 `R_ARM_RELATIVE`，多一处可错 | 链接器自动生成，重定位正确 |

两者 glibc **都支持**。要点不是选哪个，而是：

- 用 `DT_INIT` → 入口直接是代码地址（ARM32 记得带 Thumb 位）
- 用 `DT_INIT_ARRAY` → 数组槽**必须**有正确的 `RELATIVE` 重定位，否则 `dlopen` 跳到 0

本项目保留 `INIT_ARRAY`（已验证重定位正确）。**若实机失败，第一顺位回退到 `DT_INIT`**：

```bash
-Wl,-init,stage1_main        # 函数需去掉 static
```

---

## 四、本项目的构建命令

```bash
zig cc -target aarch64-linux-gnu \
       -shared -nostdlib -fPIC \
       -fno-stack-protector -O1 \
       -Wl,--strip-all \
       -Wl,-z,norelro \
       -o libJit_stage1.so stage1.c
```

逐项理由：

| 参数 | 作用 |
|---|---|
| `-shared` | `ET_DYN`，可被 `dlopen` |
| `-nostdlib` | 不链 libc —— 相机 libc 版本未知，链了会带 `DT_NEEDED` 直接失败 |
| `-fPIC` | `.so` 必需 |
| `-fno-stack-protector` | 无 libc 时 `__stack_chk_fail` 无处解析 |
| `-O1` | `-O2` 可能引入 `memcpy` 等 libc 符号 |
| `--strip-all` | 去调试段（4,736 B → 2,192 B） |
| **`-z norelro`** | **去掉 `PT_GNU_RELRO`（第 5 条铁律）** → 再降到 2,064 B |

---

## 五、症状 → 病因对照

| 写文件时返回 | 含义 | 处置 |
|---|---|---|
| `0` | 成功，`dlopen` 已执行 | 去看载荷的产出 |
| `0x10000000` | ELF 非法 / 空文件，`dlopen` 干净失败 | 检查结构（第 1–3 条） |
| 抛 USB 异常、相机消失 | 载荷在 `dlopen` 阶段崩，`im.elf` 死 | 等 30~40 s 相机自动重启；按第 1/2/4/5 条复查 |
| 读 `/tmp/jiritsu` 返回 **130** | nflasha6 被卸载 | 发 `0x4002`(MOUNT) 重挂 |

### 一个容易忽视的坑：dlopen 按名缓存

构造函数崩过一次后，**同一会话里再写任何库都命中缓存，构造函数不再执行**。所以「改了代码重新写一次」在同一个开机周期内通常是无效的 —— 必须等 `im.elf` 真正重启。

---

## 六、写进去之前先跑校验

`tools/offline/check_so.py`：

```bash
python check_so.py payload_src/libJit_stage1.so
```

检查项：`ET_DYN` / 段清单 / **`.dynamic` 是否在 RW 段** / `PT_GNU_STACK` / **是否存在 `PT_GNU_RELRO`（存在即警告）** / `DT_INIT_ARRAY` 重定位 / `p_align` 同余。

> 判定在 2026-10-24 反转过一次：**旧版把「缺 RELRO」当警告，现在把「有 RELRO」当警告**。原因见铁律第 5 条。

---

## 七、还有一条不属 ELF 但同级重要

**载荷必须极小**。相机只有 **128 MB** 内存，`MemFree` 常年 3~4 MB。
本项目 2,064 B、ZV-E10 生产载荷 440 B —— 都是这个数量级。
