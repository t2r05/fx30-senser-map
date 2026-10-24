#!/usr/bin/env bash
# build_payload.sh — 用 zig 交叉编译 AArch64 共享对象（供相机 Jiritsu dlopen）
#
# 为什么用真实链接器而不是手拼 ELF：
#   手拼极易漏 PT_GNU_STACK 或 INIT_ARRAY 槽的 R_AARCH64_RELATIVE 重定位，
#   症状是「写文件的瞬间相机从 USB 消失」。真实链接器会自然产出正确结构。
#   本项目的失败史见 ../../docs/04-dead-ends.md，规则见 ../../docs/15-payload-elf-rules.md。
#
# 依赖：pip install ziglang   （或系统里已有 zig 在 PATH）
#
# 用法：
#   ./build_payload.sh stage1.c                     # -> libJit_stage1.so
#   ./build_payload.sh mystage.c out.so
#   ZIG=/path/to/zig ./build_payload.sh stage1.c
#
# 关键参数中只有 -Wl,-z,norelro 是「经验值」，其余是常规交叉编译选项。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$HERE/stage1.c}"
OUT="${2:-$HERE/libJit_stage1.so}"

# ---- 找 zig：$ZIG > PATH > python 包 ziglang
ZIG="${ZIG:-}"
if [ -z "$ZIG" ] && command -v zig >/dev/null 2>&1; then
  ZIG="$(command -v zig)"
fi
if [ -z "$ZIG" ]; then
  for PY in "$(command -v python3 || true)" "$(command -v python || true)"; do
    [ -z "$PY" ] && continue
    CAND="$("$PY" -c "import ziglang,os;print(os.path.join(os.path.dirname(ziglang.__file__),'zig' + ('.exe' if os.name=='nt' else '')))" 2>/dev/null || true)"
    if [ -n "$CAND" ] && [ -f "$CAND" ]; then ZIG="$CAND"; break; fi
  done
fi
if [ -z "$ZIG" ] || [ ! -f "$ZIG" ] && ! command -v "$ZIG" >/dev/null 2>&1; then
  echo "找不到 zig。先执行： pip install ziglang   或设置 ZIG=/path/to/zig" >&2
  exit 1
fi

echo "zig = $ZIG"
echo "src = $SRC"
echo "out = $OUT"

# -shared              : ET_DYN，可 dlopen
# -nostdlib            : 不链 libc（相机 libc 版本未知，链了会带 DT_NEEDED）
# -fPIC                : .so 必需
# -fno-stack-protector : 无 libc 时 __stack_chk_fail 无处解析
# -O1                  : -O2 可能引入 memcpy 等 libc 符号
# --strip-all          : 去掉调试段
# -z norelro           : ★ 去掉 PT_GNU_RELRO。否则 _dl_protect_relro 会把
#                        ALIGN_DOWN(.dynamic) 整页 mprotect 成只读，连带打掉
#                        同页 .bss —— 用全局缓冲区的载荷会 SIGSEGV。
"$ZIG" cc \
  -target aarch64-linux-gnu \
  -shared -nostdlib -fPIC \
  -fno-stack-protector \
  -O1 \
  -Wl,--strip-all \
  -Wl,-z,norelro \
  -o "$OUT" "$SRC"

echo
ls -la "$OUT"
sha256sum "$OUT" 2>/dev/null || shasum -a 256 "$OUT" 2>/dev/null || true

# ---- 结构自检
if [ -f "$HERE/check_so.py" ]; then
  PYCHK=""
  for PY in "${PYTHON:-}" "$(command -v python3 || true)" "$(command -v python || true)" \
            "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"; do
    [ -z "$PY" ] && continue
    if "$PY" -c "import elftools" 2>/dev/null; then PYCHK="$PY"; break; fi
  done
  if [ -n "$PYCHK" ]; then
    echo
    echo "=== 结构校验 ==="
    "$PYCHK" "$HERE/check_so.py" "$OUT"
  else
    echo "（跳过结构校验：需要 pyelftools）" >&2
  fi
fi
