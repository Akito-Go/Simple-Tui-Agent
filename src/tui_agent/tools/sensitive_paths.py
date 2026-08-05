"""敏感文件路径检测 — 防止凭证经只读工具进入 LLM / 提交日志"""

from pathlib import Path

# 精确匹配的敏感文件名（.env.example 等模板文件除外）
_SENSITIVE_EXACT_NAMES = frozenset({
    ".env",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
})

# 敏感文件后缀
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def check_sensitive_path(path: Path) -> str | None:
    """
    检查路径是否为敏感文件。

    Returns:
        若为敏感文件返回错误说明，否则返回 None
    """
    name = path.name

    if name == ".env.example":
        return None

    if name in _SENSITIVE_EXACT_NAMES:
        return f"敏感文件禁止读取: {name}"

    if name.startswith(".env.") and not name.endswith(".example"):
        return f"敏感文件禁止读取: {name}"

    lower = name.lower()
    if any(lower.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES):
        return f"敏感文件禁止读取: {name}"

    return None
