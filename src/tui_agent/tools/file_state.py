"""每个工具注册表独立的已读状态与原子写入。"""

import difflib
import hashlib
import os
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .workspace import resolve_in_workspace

MAX_FILE_BYTES = 2_000_000


def read_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(
            f"文件超过 {MAX_FILE_BYTES} 字节读取上限，请使用搜索定位或拆分文件"
        )
    return data


@dataclass
class ReadState:
    digest: bytes
    regions: list[tuple[int, int]]
    full: bool


class FileStateCache:
    def __init__(self):
        self.entries: OrderedDict[Path, ReadState] = OrderedDict()

    def clear(self):
        self.entries.clear()

    def record(
        self, path: Path, data: bytes, visible: str, full: bool, offset: int = 0
    ):
        digest = hashlib.sha256(data).digest()
        previous = self.entries.get(path)
        regions = (
            list(previous.regions) if previous and previous.digest == digest else []
        )
        total = len(data.decode("utf-8"))
        regions.append((0, total) if full else (offset, offset + len(visible)))
        merged = []
        for start, end in sorted(regions):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        self.entries[path] = ReadState(digest, merged, merged == [(0, total)])
        self.entries.move_to_end(path)
        while len(self.entries) > 100:
            self.entries.popitem(last=False)

    def validate(self, path: Path, data: bytes, old_string: str | None = None):
        state = self.entries.get(path)
        if state is None:
            raise ValueError("修改现有文件前请先使用 read_file 读取")
        if state.digest != hashlib.sha256(data).digest():
            raise ValueError("文件在上次读取后发生变化，请重新读取再修改")
        if old_string is None and not state.full:
            raise ValueError(
                "覆盖前需要读取完整文件；已读取部分可使用 edit_file 精确修改"
            )
        text = data.decode("utf-8")
        if old_string is not None and not any(
            old_string in text[start:end] for start, end in state.regions
        ):
            raise ValueError("待替换内容不在已读取范围内，请先读取对应部分")


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else None
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def preview_change(name: str, arguments: dict) -> str:
    path, error = resolve_in_workspace(arguments["path"])
    if error or path is None:
        return error or "路径无效"
    try:
        old = read_bytes(path).decode("utf-8") if path.exists() else ""
        new = (
            arguments["content"]
            if name == "write_file"
            else old.replace(arguments["old_string"], arguments["new_string"], 1)
        )
        diff = "\n".join(
            difflib.unified_diff(
                old.splitlines(),
                new.splitlines(),
                fromfile=str(path),
                tofile=str(path),
                lineterm="",
            )
        )
        from .output import truncate

        return truncate(diff or f"文件无变化: {path}", 2400)
    except (OSError, ValueError, UnicodeError) as exc:
        return f"文件: {path}\n无法预览: {exc}"
