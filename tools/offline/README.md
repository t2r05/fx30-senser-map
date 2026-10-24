# 离线分析脚本

**纯静态分析**：只读 `appFw.so` 文件，不连接相机、不发送任何 USB 请求。

用途：从固件镜像里解出「设置名称 → 数字 id → 运行时 `.bss` 地址」这条链，以及做三机型对比。

## 依赖

```bash
pip install pyelftools capstone
```

## 前置：准备固件镜像

需要先解密并解包官方 `BODYDATA.DAT`（方法见 [`../../05-firmware-analysis.md`](../05-firmware-analysis.md)），
得到 `appFw.so`（FX30 6.00 为 36,542,024 字节 / 未 strip 前 79,032,104 字节）。

**所有脚本顶部都有一个 `FILES` 字典，需改成你自己的路径**：

```python
FILES = {
    'FX30':  'fw/out/.../nflasha15_unpacked/lib/appFw.so',
    'FX3':   'fw/fx3out/.../nflasha15_unpacked/lib/appFw.so',
    'A6700': 'fw/a6700out/.../nflasha15_unpacked/lib/appFw.so',
}
```

## 脚本

| 脚本 | 用途 | 文档 |
|---|---|---|
| `dump_bkid_table.py <机型> <关键字>` | 导出 `{name, id, meta}` 表（16 字节/项，约 25,167 条），按关键字过滤 | [11](../../11-drive-mode-ids.md) |
| `map_prop_table.py <机型> [--dump=0xID,…]` | 解析 `{id, attach, stub[8], meta}` 表（0x58 字节/项），输出 2,692 条 id | [12](../../12-property-accessor-table.md) |
| `prop_lookup.py <机型> 0xID,0xID,…` | 按 id 查记录，打印每个桩访问的 `.bss` 地址 | [12](../../12-property-accessor-table.md) |
| `desc_lookup.py <机型> 0xID,…` | 查描述符字段（三张表，`id <= 0x04B7` / `<= 0x1045` / `<= 0x1A3`） | [11 §1](../../11-drive-mode-ids.md) |
| `find_strptr.py <机型> <字符串>` | 找指向该字符串的 8 字节指针，dump 周边结构（这是找到 BKID 表的方法） | [11](../../11-drive-mode-ids.md) |
| `find_xref.py <机型> <字符串>` | 找 `adrp+add` 引用（对 BKID 字符串会得 0 处，属预期） | [11](../../11-drive-mode-ids.md) |
| `find_idseq.py` | 在 `.rodata`/`.data` 里找 `0x1A2 → 0x1A3` 连续序列（验证菜单列表是否漏项） | [11 §5](../../11-drive-mode-ids.md) |
| `scan_cmp_exact.py` | 统计全 `.text` 里 `cmp <reg>, #imm` 的立即数分布（对比哪些模式被特判） | [11 §4](../../11-drive-mode-ids.md) |
| `dis_range.py <机型> <lo> <hi>` | 反汇编指定 va 区间 | — |
| `bkid_drive_compare.py` | 四机型 `drive_mode` BKID **大小写不敏感**归一化对照，输出覆盖率矩阵与 CSV | [11 §二](../../docs/11-drive-mode-ids.md) |
| `find_prop_table.py` | 扫描 `.data.rel.ro` 里的「等距且严格递增 id 列」，**不预设 stride** 地定位属性访问器表 | [12](../../docs/12-property-accessor-table.md) |
| `unpack_a7c2.py <BODYDATA.DAT> <outdir>` | UFU 解析 → 提取 FDAT → 解密 → 提示后续 fwtool 命令 | [16](../../docs/16-firmware-unpack.md) |
| `decrypt_fdat_fast.py <src> <dst>` | 4 代加密 FDAT 的快速解密（48 MB/s，含 checksum/endFlag 全量校验） | [16 §四](../../docs/16-firmware-unpack.md) |

## 用法示例

```bash
# 1) 找连拍 BKID 的数字 id
python find_strptr.py FX30 "BKID_APP_setting_drive_mode_cont_shooting"
#   → 0x0414F7B8  0000002D000004B8    即 id = 0x04B8

# 2) 列出全部 drive_mode 相关条目
python dump_bkid_table.py FX30 drive_mode

# 3) 解出连拍 id 的运行时地址
python prop_lookup.py FX30 0x4B8,0x4BA,0x2AF

# 4) 四机型 id 对照（大小写不敏感，自动处理三种命名规范）
export FW_ROOT=/path/to/fx30_hack
python bkid_drive_compare.py --csv dm_compare.csv
python bkid_drive_compare.py --dump A7C2 | grep -i "HI_PLUS\|ELECTRIC"

# 5) 官方固件包解包（A7C2 起需要先解密）
export FWTOOL_ROOT=/path/to/fwtool.py
python unpack_a7c2.py "BODYDATA.DAT" ./a7c2out
```

## 三条容易踩的坑

1. **`adrp+add` 找不到字符串不等于它没被引用。** BKID 名称通过 `.data.rel.ro` 里的指针表索引，
   要搜「指向字符串的 8 字节指针」，不是搜指令。
2. **`adrp` 的立即数会让归一化签名失效。** 做指令级对齐时必须剥掉 `#0x…` 立即数，否则命中率只有 5% 量级。
3. **解析器不跨机型通用。** `map_prop_table.py` 的 0x58 结构只适用 FX30/FX3；
   A6700 / A7C2 的 `.data.rel.ro` 是另一种布局（同一解析器只索引到 0 条连续链）。
   未知布局先用 `find_prop_table.py` 扫 stride。
4. **BKID 名称大小写不统一。** FX30/FX3 是 `BKID_APP_setting_*`（小写），
   A7C2 是 `BKID_APP_SETTING_*`（全大写）。按大写关键词筛会漏掉 FX30 整族。用 `bkid_drive_compare.py`。
5. **官方固件包分明文与加密两代。** A7C2 2.01 起 FDAT 段是密文，需先解密才能交给 fwtool。
   见 [16-firmware-unpack](../../docs/16-firmware-unpack.md)。
