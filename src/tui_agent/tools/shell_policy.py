"""Shell 命令安全策略 — 黑名单拦截高危操作"""

from __future__ import annotations

import re

# 高危命令模式（命中即拒绝执行；与「本会话全部允许」无关）
_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 删除根 / 家目录
    (
        re.compile(
            r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+/\s*($|;|&|\|)"
        ),
        "禁止删除根目录 (rm -rf /)",
    ),
    (
        re.compile(
            r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+/\*"
        ),
        "禁止删除根目录内容 (rm -rf /*)",
    ),
    (
        re.compile(
            r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+"
            r"(~|/Users/|/home/|\$HOME|\$\{HOME\})"
        ),
        "禁止递归删除家目录",
    ),
    (re.compile(r"\bsudo\s+rm\b"), "禁止 sudo rm"),
    # 资源耗尽 / 系统破坏
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"), "禁止 fork bomb"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "禁止格式化磁盘 (mkfs)"),
    (re.compile(r"\bdd\b[^|&;\n]*\bof=/dev/"), "禁止向块设备写入 (dd of=/dev/...)"),
    (re.compile(r">\s*/dev/sd[a-z]\d*"), "禁止重定向写入磁盘设备"),
    (re.compile(r"\btee\b[^|&;\n]*/dev/sd[a-z]"), "禁止 tee 写入磁盘设备"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"), "禁止关机/重启命令"),
    (re.compile(r"\b(diskutil\s+erase|format-volume)\b", re.I), "禁止磁盘擦除命令"),
    (re.compile(r"\bkill\s+(-9\s+)?-1\b"), "禁止 kill -1（终止所有进程）"),
    # 远程脚本执行 / 反弹壳
    (re.compile(r"\b(curl|wget)\b[^|&;\n]*\|\s*(ba)?sh\b"), "禁止管道执行远程脚本 (curl|sh)"),
    (re.compile(r"\b(curl|wget)\b[^|&;\n]*\|\s*python[23]?\b"), "禁止管道执行远程 Python"),
    (re.compile(r"\$\(\s*(curl|wget)\b"), "禁止命令替换下载执行 $(curl ...)"),
    (re.compile(r"`\s*(curl|wget)\b"), "禁止命令替换下载执行 `curl ...`"),
    (re.compile(r"\beval\s+\$\(\s*(curl|wget)\b"), "禁止 eval 远程脚本"),
    (re.compile(r"\bbase64\b[^|&;\n]*\|\s*(ba)?sh\b"), "禁止 base64|sh 解码执行"),
    (re.compile(r"/dev/tcp/"), "禁止 /dev/tcp 反弹连接"),
    (re.compile(r"\bnc\b[^|&;\n]*\s-e\b"), "禁止 netcat -e 反弹壳"),
    (re.compile(r"\bncat\b[^|&;\n]*\s--exec\b"), "禁止 ncat --exec"),
    (re.compile(r"\bbash\s+-i\b"), "禁止交互式反弹 bash -i"),
    # 权限 / 敏感路径篡改
    (re.compile(r"\bchmod\s+(-R\s+)?777\s+/"), "禁止对根路径 chmod 777"),
    (re.compile(r"\bchown\s+(-R\s+)?[^|&;\n]+\s+/($|\s)"), "禁止对根路径 chown"),
    (re.compile(r":\s*>\s*/etc/"), "禁止清空 /etc 下文件"),
    (re.compile(r">\s*/etc/(passwd|shadow|sudoers)\b"), "禁止覆写系统认证文件"),
    (re.compile(r"\btee\b[^|&;\n]*/etc/(passwd|shadow|sudoers)\b"), "禁止 tee 写入系统认证文件"),
    (re.compile(r"\b(find|xargs)\b[^|&;\n]*\s-delete\b[^|&;\n]*/\s*($|;|&|\|)"), "禁止 find -delete 根路径"),
]


def check_shell_command(command: str) -> str | None:
    """
    检查命令是否命中黑名单。

    Returns:
        拒绝原因；允许执行时返回 None。
    """
    text = (command or "").strip()
    if not text:
        return "命令不能为空"

    for pattern, reason in _BLOCKED_PATTERNS:
        if pattern.search(text):
            return f"命令被安全策略拦截: {reason}"

    return None
