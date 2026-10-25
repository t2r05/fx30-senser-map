# TRAE 任务包 · 第十期：加密器 / ext4 改写 / id 绑定

> 2026-10-25
> 上游：第七期（fdat 格式）、第八期（pack_fdat / crc32 / 分区顺序）、第九期（回调族）
> 本期目标：补齐整条重打包链路的**最后三个工程缺口**

---

## 0. 全局边界

| 禁止 | 说明 |
|---|---|
| 不连接相机 | 本期 100% 纯离线 |
| 不运行 `probe_*.py` | 会打开 USB |
| **不改 `fw/` 下任何文件** | 一切操作在 `tmp01/` 副本上 |
| 新脚本 `T20_` 前缀 | 放 `audit/tasks/` |
| 不 git commit / push | 我方统一提交 |
| 不下结论 | 只回数字、地址、字节、比对结果 |
| 单次中间文件 ≤ 2 GB | 磁盘余量有限 |

Python：`C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
工作目录：`F:\Ai\WorkBuddy\2026-10-20-22-22-33\fx30_hack`

---

## 1. 已确证事实（直接用，不要重做）

### 1.1 fdat 容器

```
fdat = [512 B header] + [updater.img 1,253,376 B] + [firmware.tar 901,823,488 B]
原包 sha256 = cf203c1384d90e3621cb30830123105b347d84690f00fe4d86973942debcecdc
零改动重打包后 sha256 与上完全相同（已验证）
```

header 关键字段：

| 偏移 | 含义 |
|---|---|
| `0x000` | magic `"UDTRFIRM"` |
| `0x008` | `crc32(header[0x00C:0x200])` |
| `0x024` | 机型 ID `0x11030082` |
| `0x030` | tar 起始偏移 = 512 + updater 大小 |
| `0x034` | tar 大小 |
| `0x048` | updater.img 大小 |

tar = POSIX ustar，142 条目；`.sum` 在 tar 内，是纯文本 CSV，第 2 字段 = **zlib CRC32**。

### 1.2 分区镜像

`0700_part_image/dev/nflasha15` = **明文 ext4**（`53ef` 命中 `0x438`，前 64 KB 仅 120 种字节）。
`part_image.sum` 的 size 字段是**分区容量**（600,584,192），实际文件 599,682,048。

`nflasha3` / `nflasha8` 是 FAT。**没有分区镜像被加密。**

### 1.3 fdat 外壳加密（本期 T1 的依据）

`fw/fwtool/fwtool/sony/fdat.py`：

```python
class Crypter:
    def packBlock(self, data): return data
    def encryptBlock(self, data): return data
    def _crypt(self, file, blockSize, cryptFunc): ...   # 已有分块框架
    def encrypt(self, file):
        return self._crypt(file, self._encryptBlockSize,
                           lambda data: self.encryptBlock(self.packBlock(data)))

class BlockCrypter(Crypter):
    def packBlock(self, data):        # ← 已实现
        sizeAndEndFlag = len(data)
        if self.isLastBlock: sizeAndEndFlag |= 0x8000
        data = dump16le(sizeAndEndFlag) + data + b'\xff' * (self._decryptBlockSize - 4 - len(data))
        return dump16le(self._calcSum(data)) + data

class AesCbcCrypter(AesCrypter):
    def encrypt(self, file):
        raise Exception('Encryption not supported')   # ← 唯一缺口
```

密钥：`fw/fwtool/fwtool/sony/constants.py` 的 `key_aes`、`key_cxd90057_k8`（公开）。
`_crypters['CXD90057_k8'] = AesCbcCrypter(key_aes, key_cxd90057_k8)`。

解密结构（`fw/decrypt_fdat_fast.py` 注释 + 代码）：

```
文件末 0x110 字节：倒数 0x110..0x100 处是 16 字节 IV
(size - 0x110) 必须是 1024 的整数倍
第 1 个 1024 B 块：前 512 走 AES-ECB(key_aes)，后 512 走 AES-CBC(key2)
第 2..N 块：全部 AES-CBC(key2)，CBC 状态跨块连续
每块明文 1024 B：[0:2] checksum(u16le)=sum(u16le of data[2:])&0xffff
                  [2:4] sizeAndEndFlag（bit15=末块，bit0-14=有效长度）
                  [4:4+size] 数据，其余 0xFF 填充
```

### 1.4 回调族（本期 T3 的依据）

- 全 `.text` 有 **98,041** 个 `mov w0,#imm ; ret` 两指令函数（值分布 `1`:63,166、`0`:34,145…）
- 描述符数组：基址 **`0x102B780`**、步长 **24**，条目 `{A(.text 回调), B(.got 槽), 0x403}`，抽样 1600/1600 第三字段 = `0x403`
- 关系：`A(k) == .got[B(k-1)]`（错一位）
- 8 个 PRM 对应的记录：

| 参数 | 注册表索引 | 记录@ | B = .got 槽 | 槽内回调 |
|---|---|---|---|---|
| available0 | 789 | `0x1030178` | `0x47B8278` | `0x1C0AF7C`(→1) |
| available1 | 790 | `0x1030190` | `0x47B8280` | `0x18965D8`(→1) |
| available2 | 791 | `0x10301A8` | `0x47B8288` | `0x1906AD8`(→1) |
| available3 | 792 | `0x10301C0` | `0x47B8290` | `0x1A41F14`(→1) |
| multi0 | 1568 | `0x1034A80` | `0x47B9AD0` | `0x1860104`(→1) |
| multi1 | 1569 | `0x1034A98` | `0x47B9AD8` | **`0x199F744`(→0)** |
| multi2 | 1570 | `0x1034AB0` | `0x47B9AE0` | `0x174C1DC`(非2指令) |
| multi3 | 1571 | `0x1034AC8` | `0x47B9AE8` | `0x18330D4`(→1) |

- **记录 ±0x60 内 `0x02CFxxxx` 键命中 = 0 / 13,090** ⇒ id 绑定未知

### 1.5 已有工具

- `audit/tasks/T18_pack_fdat.py` —— 打包器（`--list` / `--verify` / `--replace`），零改动 sha256 验收通过
- `fw/decrypt_fdat_fast.py` —— 快速解密（numpy 批量 CBC，1.3 GB 约 15 秒）
- `fw/fwtool/` —— 上游工具（unpack only）
- `tmp01/updater_unpacked/` —— 升级程序（SquashFS 已解，58 文件，含 `uc_crc32sum.elf`）

---

## 2. 任务

### T1 ⭐⭐⭐ 加密器（P0，整条链路的最后一环）

**目标**：把明文 `fdat` 加密回官方 `FirmwareData.dat` 格式。

**步骤**：

1. **先解出尾部 `0x110` 的确切布局**
   - 取原包 `fw/out/firmware.fdat`（明文）与其对应的加密原件的尾部对比 —— 若加密原件已不可得，就只用明文包的尾部（注意：明文包尾部 0x110 是**明文字段**，加密件尾部另行分析）
   - 说明：解密时 `iv = file[size-0x110 : size-0x100]`，即 IV 在尾部偏移 `+0x00`
   - 剩下的 `0x100` 字节是什么？逐字段列出（u32/ASCII），能识别的标注，其余标 `?`
2. **实现 `encryptBlock`**（约 20 行）

   先看清楚内部属性名（**已核验**）：

   ```python
   class AesCrypter(BlockCrypter):
       def __init__(self, key):
           super().__init__(1024)
           self._cipher = AES.new(key, AES.MODE_ECB)     # ← ECB，key = key_aes
       def encryptBlock(self, data):
           return self._cipher.encrypt(data)
   ```

   `AesCbcCrypter.__init__` 里 `self._key = key2`（CBC 用的 key），`self._cipher` 继承自父类（ECB/key_aes）。

   ```python
   def encryptBlock(self, data):
       if self.isFirstBlock:
           self._cipher2 = AES.new(self._key, AES.MODE_CBC, self._iv)
           return self._cipher.encrypt(data[:512]) + self._cipher2.encrypt(data[512:])
       return self._cipher2.encrypt(data)
   ```

   **可参照的现成范例**：`DoubleAesCrypter.encryptBlock` 已实现同类逻辑（也是首块特殊处理），
   其写法是「先对后 512 加密，再拼回首 512 明文，最后交给父类 ECB」——思路可借鉴：
3. **实现 `encrypt()`**：写主体 + 追加尾部 `0x110`（IV + 其余字段）
4. **封装 `T20_encrypt_fdat.py`**
   ```
   --src <明文 fdat> --out <加密 dat> [--iv <hex32>] [--eof0x110 <原包尾部文件>]
   ```

**验收（硬）**：

| 验收 | 判据 |
|---|---|
| **A 往返无损** | `encrypt(fdat) → decrypt → sha256` **必须等于原 fdat 的 sha256** `cf203c13…debcecdc` |
| **B 二次一致** | 用**固定 IV** 加密两次 → 两次输出 sha256 相同（证明无隐藏随机量） |
| **C 不写 fw/** | 全部在 `tmp01/fdat_rebuild/` 下 |

⚠️ 若尾部 `0x100` 含未知字段，先**原样复制原包该字段**（不要自己造），保证往返一致。

---

### T2 ⭐⭐ ext4 内替换文件（改 `appFw.so` 的手段）

**目标**：对明文 ext4 镜像 `nflasha15` 做「替换一个文件内容」，产出能用的镜像。

**步骤**：

1. 确认工具可用性：本机是否有 `debugfs` / `e2fsprogs` / WSL？
   - 有 → 用 `debugfs -w` 的 `write`/`rm` 完成
   - 没有 → 评估纯 Python 方案（读 superblock / inode / block bitmap，原地改写）
2. **优先做「原地等长替换」**：新文件长度 ≤ 原文件，直接写占用的块，不改 inode 的 size 以外的元数据（若变短需更新 i_size 与 block bitmap）
3. 输出工具 `T20_ext4_replace.py`：
   ```
   --image <nflasha15> --path /lib/appFw.so --new <本地文件> --out <新镜像>
   ```

**验收**：

| 验收 | 判据 |
|---|---|
| A 零改动 | 不替换任何文件时，输出镜像 sha256 == 输入 |
| B 等长替换 | 替换为同长度内容后，`debugfs`/`e2fsck -fn` 检查通过；用 `debugfs dump` 取回内容 == 新文件 |
| C 变长替换 | 换成更短内容时，镜像仍可正常读取（`e2fsck -fn` 无 error） |

---

### T3 ⭐ id ↔ 回调 的绑定（承接第九期缺口）

**已知**：描述符数组记录内**没有 id 字段**，附近 `0x02CFxxxx` 键 0 命中。

**新方法：从 `.got` 槽的代码引用反查**

1. 对 8 个 `.got` 槽（`0x47B8278 / 280 / 288 / 290`、`0x47B9AD0 / D8 / E0 / E8`）
2. 扫 `adrp xM, #0x47B8000/#0x47B9000` + `ldr xN, [xM, #disp]`（含 `page±0x1000`、`add/mov` 别名）
3. 对每个读取点，**向前后各 20 条指令**找：
   - 立即数 `0x0C2C`–`0x0C33`（属性 id）
   - 立即数 `0x02CF0000|id` 形式的 key
   - 或 `mov w?, #0x2cf ; movk` 组合
4. 产出：`got 槽 → 读取函数 → 附近常量` 表

**验收**：给出 8 个槽的读取点数与常量命中数；若全 0，明确回报「绑定纯靠数组下标，位置假设无法独立证实」。

---

## 3. 优先级与执行顺序

```
T1（加密器）  ← 唯一 blocker，其它都可以并行但先做这个
T2（ext4）    ← 第二优先，不带它就没法改 appFw.so
T3（id 绑定） ← 第三，只影响「改哪个回调」的精度，不影响链路打通
```

每做完一个先回报，再进下一个。

---

## 4. 回报格式

```
### 任务 TN · <一句话结论>

**数据**（表）

**证据**
- 脚本：audit/tasks/T20_xxx.py → audit_raw/T20_xxx.txt
- 关键地址/偏移：
- 比对结果（sha256 / e2fsck / 计数）

**置信度**：✅ / 🟡 / ⬜

**排除的其它可能**
- 假设X：❌ 因为…

**未完成部分**（如实写）
```

---

## 5. 绝对不要做的事

1. **不要**修改 `fw/` 下的任何文件（含 `fw/out/firmware.fdat`）—— 全部复制到 `tmp01/`
2. **不要**在加密器里引入随机 IV 而不告知 —— 会导致往返不一致
3. **不要**假设尾部 `0x100` 是零 —— 必须对照原包实际字节
4. **不要**用 `dd`/`truncate` 大面积改写 600 MB 镜像后直接报告成功 —— 必须跑 `e2fsck -fn`
5. **不要**提交超过 2 GB 的中间文件
6. **不要**下"这样就能刷机"之类的结论 —— 实机验证由我方执行
