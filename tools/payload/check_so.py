#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_so.py — 校验一个 AArch64 共享对象是否具备「被相机 dlopen」的必要条件

背景
----
我们 10-23 手工构造 .so 连续失败（SET_FILE 时 GenericUsbException，Jiritsu 进程崩溃），
原因已定位为两处结构缺失：
    ① 缺 PT_GNU_STACK
    ② DT_INIT_ARRAY 指向的槽没有 R_AARCH64_RELATIVE 重定位（addend 不会随加载基址调整）

本脚本把这两条连同其他必要条件做成可自动判定的检查项。参考样本取相机上真实在用的
`libJiritsu.so`（2 段 LOAD / 有 PT_GNU_STACK / INIT_ARRAY 带 1 条 RELATIVE）。

用法
----
    python check_so.py payload_src/libJit_stage1.so
    python check_so.py payload_src/libJit_stage1.so --ref=p0_out/v3_UP_UP_usr_lib_libJiritsu.so.bin
"""
import sys
import os

from elftools.elf.elffile import ELFFile

R_AARCH64_RELATIVE = 1027
OK, BAD, WARN = "✅", "❌", "⚠️ "


def check(path, ref=None):
    fails = []
    warns = []
    with open(path, "rb") as f:
        e = ELFFile(f)
        size = os.path.getsize(path)
        print("文件: %s" % path)
        print("大小: %d 字节" % size)
        print("类型: %s / %s" % (e.header["e_type"], e.header["e_machine"]))
        print()

        # ---- 1. 基本类型
        print("=== 1. 基本属性 ===")
        if e.header["e_type"] != "ET_DYN":
            fails.append("e_type 不是 ET_DYN（dlopen 只接受共享对象）")
            print("  %s e_type = %s" % (BAD, e.header["e_type"]))
        else:
            print("  %s e_type = ET_DYN" % OK)
        if e.header["e_machine"] != "EM_AARCH64":
            fails.append("e_machine 不是 AArch64")
            print("  %s e_machine = %s" % (BAD, e.header["e_machine"]))
        else:
            print("  %s e_machine = EM_AARCH64" % OK)
        print("  %s 体积 %d B（Jiritsu SET_FILE 上限 25 MB，余量充足）"
              % (OK if size < 25 * 1024 * 1024 else BAD, size))

        # ---- 2. program headers
        print("\n=== 2. 程序头 ===")
        phs = list(e.iter_segments())
        types = [p["p_type"] for p in phs]
        loads = [p for p in phs if p["p_type"] == "PT_LOAD"]
        for p in phs:
            print("  %-18s off=0x%-8X vaddr=0x%-8X filesz=0x%-8X memsz=0x%-8X flags=%d"
                  % (p["p_type"], p["p_offset"], p["p_vaddr"], p["p_filesz"],
                     p["p_memsz"], p["p_flags"]))

        if len(loads) < 1:
            fails.append("没有 PT_LOAD")
            print("  %s 无 PT_LOAD" % BAD)
        else:
            print("  %s PT_LOAD 共 %d 段" % (OK, len(loads)))

        # 可执行段必须存在
        if not any(p["p_flags"] & 1 for p in loads):
            fails.append("没有可执行 PT_LOAD（PF_X）→ 代码无法运行")
            print("  %s 无可执行段（PF_X）" % BAD)
        else:
            print("  %s 存在可执行段（PF_X）" % OK)

        # W^X：不允许同一段同时 W 和 X
        wx = [p for p in loads if (p["p_flags"] & 2) and (p["p_flags"] & 1)]
        if wx:
            fails.append("存在 W+X 的 PT_LOAD（W^X 策略下会被拒或映射后无执行权限）")
            print("  %s 存在 W+X 段 —— 必须拆成 RW / RX 两段" % BAD)
        else:
            print("  %s 无 W+X 段（符合 W^X）" % OK)

        # ★ 关键 ①：PT_GNU_STACK
        if "PT_GNU_STACK" not in types:
            fails.append("缺 PT_GNU_STACK（10-23 崩溃原因之一）")
            print("  %s 缺 PT_GNU_STACK ← 10-23 崩溃原因之一" % BAD)
        else:
            st = [p for p in phs if p["p_type"] == "PT_GNU_STACK"][0]
            print("  %s PT_GNU_STACK 存在（flags=%d，%s栈）"
                  % (OK, st["p_flags"],
                     "可执行" if st["p_flags"] & 1 else "不可执行"))

        # 【2026-10-24 判定反转】依据 nolan2628/Sony-ZVE-10-Camtool：
        # 可用的 dlopen 载荷 libJit_exec.so(440B) 没有 PT_GNU_RELRO，只有 LOAD/LOAD/DYNAMIC。
        # RELRO 会让 _dl_protect_relro 把 ALIGN_DOWN(.dynamic) 整页 mprotect 成只读，
        # 连带打掉同页 .bss —— stage2 一用全局缓冲区就 SIGSEGV。
        # 因此「有 RELRO」现在是警告，「没有」才是期望状态。
        if "PT_GNU_RELRO" not in types:
            print("  %s 无 PT_GNU_RELRO（期望状态：.dynamic/.bss 保持可写）" % OK)
        else:
            warns.append("存在 PT_GNU_RELRO（会 mprotect 掉 .dynamic 同页，stage2 用全局变量会崩）")
            print("  %s 存在 PT_GNU_RELRO ← 应加 -Wl,-z,norelro" % WARN)

        # ---- 3. dynamic
        print("\n=== 3. 动态表 ===")
        dn = e.get_section_by_name(".dynamic")
        if dn is None:
            fails.append("无 .dynamic 段 → 不是有效的共享对象")
            print("  %s 无 .dynamic" % BAD)
            tags = {}
        else:
            tags = {}
            for t in dn.iter_tags():
                tags.setdefault(t.entry.d_tag, []).append(
                    t.entry.d_val if hasattr(t.entry, "d_val") else 0)
            for k in ("DT_NEEDED", "DT_INIT", "DT_FINI", "DT_INIT_ARRAY",
                      "DT_INIT_ARRAYSZ", "DT_RELA", "DT_RELASZ", "DT_RELACOUNT",
                      "DT_STRTAB", "DT_SYMTAB", "DT_HASH", "DT_GNU_HASH"):
                if k in tags:
                    vals = ", ".join(hex(v) for v in tags[k][:8])
                    print("  %-16s %s%s" % (k, vals,
                                            "  ×%d" % len(tags[k]) if len(tags[k]) > 1 else ""))
                else:
                    print("  %-16s (无)" % k)

            if "DT_INIT_ARRAY" not in tags and "DT_INIT" not in tags:
                fails.append("既无 DT_INIT 也无 DT_INIT_ARRAY → 模块不会执行任何代码")
                print("  %s 既无 DT_INIT 也无 DT_INIT_ARRAY" % BAD)

            # 符号表三件套
            for need in ("DT_STRTAB", "DT_SYMTAB"):
                if need not in tags:
                    fails.append("缺 %s（10-23 崩溃原因之二：glibc 会解引用）" % need)
                    print("  %s 缺 %s ← 10-23 崩溃原因之二" % (BAD, need))
            if "DT_HASH" not in tags and "DT_GNU_HASH" not in tags:
                fails.append("缺 DT_HASH / DT_GNU_HASH")
                print("  %s 缺 hash 表" % BAD)

        # ---- 4. ★ 关键 ②：DT_INIT_ARRAY 必须有 RELATIVE 重定位
        print("\n=== 4. 初始化数组的重定位（关键）===")
        ia = tags.get("DT_INIT_ARRAY", [None])[0]
        iasz = tags.get("DT_INIT_ARRAYSZ", [0])[0]
        if ia is None:
            print("  %s 无 DT_INIT_ARRAY（若有 DT_INIT 也可）" % WARN)
        else:
            print("  DT_INIT_ARRAY = 0x%X  size = 0x%X（%d 项）"
                  % (ia, iasz, iasz // 8 if iasz else 0))
            rel_rel = []
            rela = e.get_section_by_name(".rela.dyn")
            if rela is None:
                fails.append("有 DT_INIT_ARRAY 但无 .rela.dyn → 首地址不会随加载基址调整")
                print("  %s 无 .rela.dyn" % BAD)
            else:
                all_rel = list(rela.iter_relocations())
                for r in all_rel:
                    if r["r_info_type"] == R_AARCH64_RELATIVE:
                        rel_rel.append((r["r_offset"], r["r_addend"]))
                # INIT_ARRAY 区间覆盖检查
                hit = [(o, a) for o, a in rel_rel
                       if ia <= o < ia + max(iasz, 8)]
                if not hit:
                    fails.append("DT_INIT_ARRAY 槽位没有 R_AARCH64_RELATIVE 重定位"
                                 "（10-23 崩溃原因之三：加载后仍指向未调整的绝对地址）")
                    print("  %s INIT_ARRAY 区间内无 RELATIVE 重定位 ← 致命" % BAD)
                else:
                    for o, a in hit:
                        ok = 0 < a < 0x10000000
                        print("  %s 槽 0x%X -> R_AARCH64_RELATIVE addend=0x%X %s"
                              % (OK, o, a, "(指向 vaddr 空间)" if ok else "(addend 可疑)"))
                print("  %s .rela.dyn 共 %d 条重定位，其中 RELATIVE %d 条"
                      % (OK, len(all_rel), len(rel_rel)))

        # ---- 5. 段清单
        print("\n=== 5. 段清单 ===")
        secs = [s.name for s in e.iter_sections()]
        print("  " + ", ".join(n if n else "(null)" for n in secs))
        for need in (".text", ".dynsym", ".dynstr", ".init_array"):
            if need not in secs:
                warns.append("缺 %s 段" % need)
                print("  %s 缺 %s" % (WARN, need))

        # ---- 6. 与参考样本对比
        if ref and os.path.exists(ref):
            print("\n=== 6. 与参考样本对比 ===")
            with open(ref, "rb") as rf:
                re_ = ELFFile(rf)
                rtypes = set(p["p_type"] for p in re_.iter_segments())
                mytypes = set(types)
                print("  参考: %s" % ref)
                print("  参考有而本文件无: %s" % (sorted(rtypes - mytypes) or "无"))
                print("  本文件有而参考无: %s" % (sorted(mytypes - rtypes) or "无"))
                rg = re_.get_section_by_name(".dynamic")
                rtags = set(t.entry.d_tag for t in rg.iter_tags()) if rg else set()
                if "DT_NEEDED" in rtags and "DT_NEEDED" not in tags:
                    print("  (参考带 %d 个 DT_NEEDED 依赖；本文件 freestanding，正常)"
                          % sum(1 for t in rg.iter_tags() if t.entry.d_tag == "DT_NEEDED"))

    # ---- 汇总
    print("\n" + "=" * 56)
    if warns:
        print("警告 %d 项：" % len(warns))
        for w in warns:
            print("  - " + w)
    if fails:
        print("阻塞项 %d 条 —— 这个 .so 大概率无法 dlopen：" % len(fails))
        for x in fails:
            print("  - " + x)
        return 1
    print("结构检查全部通过。可以进入实机写入测试。")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    ref = None
    for a in sys.argv[2:]:
        if a.startswith("--ref="):
            ref = a.split("=", 1)[1]
    sys.exit(check(sys.argv[1], ref))
