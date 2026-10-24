/* stage1.c — 最小 AArch64 共享对象（-shared -nostdlib，无 libc）
 * 目的：验证「真实链接器产出的 .so 能否被相机 dlopen」
 * 第一步只做一个可判定动作：往 /mnt/PRIVATE/ 写一行标记。
 * 不依赖 libc，全部裸系统调用。
 */
typedef unsigned long u64;
typedef long i64;

#define SYS_write 64
#define SYS_openat 56
#define SYS_close 57
#define SYS_getpid 172

#define AT_FDCWD (-100)
#define O_WRONLY_CREAT_TRUNC 0x241

static inline i64 sc3(i64 n, i64 a, i64 b, i64 c) {
  register i64 x0 __asm__("x0") = a;
  register i64 x1 __asm__("x1") = b;
  register i64 x2 __asm__("x2") = c;
  register i64 x8 __asm__("x8") = n;
  __asm__ volatile("svc #0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x8) : "memory");
  return x0;
}

static inline i64 sys_openat(i64 dfd, const char *p, i64 fl, i64 mode) {
  register i64 x0 __asm__("x0") = dfd;
  register i64 x1 __asm__("x1") = (i64)p;
  register i64 x2 __asm__("x2") = fl;
  register i64 x3 __asm__("x3") = mode;
  register i64 x8 __asm__("x8") = SYS_openat;
  __asm__ volatile("svc #0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x8) : "memory");
  return x0;
}

static u64 slen(const char *s) { u64 n = 0; while (s[n]) n++; return n; }

__attribute__((constructor)) static void stage1_main(void) {
  const char *path = "/mnt/PRIVATE/STAGE1.txt";
  const char *tag  = "STAGE1-BUILT-BY-ZIG\n";
  i64 fd = sys_openat(AT_FDCWD, path, O_WRONLY_CREAT_TRUNC, 0644);
  if (fd >= 0) {
    sc3(SYS_write, fd, (i64)tag, (i64)slen(tag));
    sc3(SYS_close, fd, 0, 0);
  }
}
