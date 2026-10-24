# payload/ — dlopen 载荷构建与结构校验

配套文档：[`docs/15-payload-elf-rules.md`](../../docs/15-payload-elf-rules.md)

## 这是什么

把一个小 `.so` 写进 `/tmp/jiritsu/libJit.so`，相机服务进程就会 `dlopen` 它并执行构造函数。
本目录只有**构建**与**校验**工具，**没有**任何写入型脚本。

## 为什么这么讲究

写进去的 `.so` 结构不合法时，症状不是「报错」，而是**相机从 USB 消失** ——
服务进程 `im.elf` 在 `dlopen` 阶段崩溃。这类失败没有任何日志，只能靠结构预检避免。

## 文件

| 文件 | 作用 |
|---|---|
| `stage1.c` | 最小参考载荷。纯系统调用，无 libc，只做一件事：往 SD 卡写一行标记 |
| `build_payload.sh` | 用 zig 交叉编译成 AArch64 `.so`，编译完自动跑结构校验 |
| `check_so.py` | ELF 结构校验器（需要 `pyelftools`） |

## 用法

```bash
pip install ziglang pyelftools
./build_payload.sh                    # -> libJit_stage1.so（2,064 B）
./build_payload.sh mystage.c out.so   # 指定源与输出
python check_so.py libJit_stage1.so   # 单独校验
```

## `stage1.c` 做的事

```c
__attribute__((constructor)) static void stage1_main(void) {
  const char *path = "/mnt/PRIVATE/STAGE1.txt";
  ...
}
```

构造函数往 SD 卡根目录写一行 `STAGE1-BUILT-BY-ZIG`。
**可判定的成功标志**：文件出现 = 代码真的执行了；文件不出现 = 没执行。

用 SD 卡而不是内部路径，是因为 SD 卡挂载点能被 PC 直接看到，不需要再走 USB 会话读回。

## 五条铁律（详见 docs/15）

1. `.dynamic` 必须在**可写** `PT_LOAD` 内
2. 必须有 `PT_GNU_STACK`
3. `vaddr ≡ off (mod p_align)`
4. 构造函数入口的指令集位必须与代码模式一致（ARM32）
5. **不要带 `PT_GNU_RELRO`** —— 这条由 `-Wl,-z,norelro` 保证

`check_so.py` 会逐条检查。全绿再往相机里写。

## 注意

- 载荷必须极小（相机只有 128 MB 内存）。
- `dlopen` **按名缓存**：构造函数崩过一次，同一开机周期内再写任何库都不执行，必须等 `im.elf` 重启（约 30~40 s 自动重启）。
- 写进去的文件在 flash 分区，**跨重启保留**。测完必须显式删除，且删后要发 `0x4002`(MOUNT) 重挂分区。
