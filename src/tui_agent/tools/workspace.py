"""工作区沙箱 — 限制文件与 Shell 操作在项目根目录内"""

from pathlib import Path

_workspace_root: Path | None = None


def get_workspace_root() -> Path:
    """返回当前工作区根目录（默认为进程启动时的 cwd）"""
    global _workspace_root
    if _workspace_root is None:
        _workspace_root = Path.cwd().resolve()
    return _workspace_root


def set_workspace_root(root: Path) -> None:
    """设置工作区根目录（TUI 启动时绑定为项目目录）"""
    global _workspace_root
    _workspace_root = root.resolve()


def reset_workspace_root() -> None:
    """重置为惰性默认（测试用）"""
    global _workspace_root
    _workspace_root = None


def is_under_workspace(path: Path) -> bool:
    """判断绝对路径是否位于工作区内"""
    root = get_workspace_root()
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def resolve_in_workspace(path: str) -> tuple[Path | None, str | None]:
    """
    将用户路径解析为工作区内的绝对路径。

    Returns:
        (resolved_path, error_message) — 成功时 error 为 None
    """
    root = get_workspace_root()
    try:
        candidate = Path(path)
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    except OSError as exc:
        return None, f"路径无效: {exc}"

    if not is_under_workspace(resolved):
        return None, f"路径超出工作区范围: {path}（工作区: {root}）"
    return resolved, None
