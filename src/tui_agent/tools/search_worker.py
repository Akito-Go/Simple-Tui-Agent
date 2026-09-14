"""隔离搜索工作进程：正则耗时过长时可由调用方安全终止。"""

import json
import fnmatch
from functools import lru_cache
import os
from pathlib import Path
import re
import sys

from .sensitive_paths import check_sensitive_path

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".tui-agent",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}


def files_under(path: Path):
    if path.is_file():
        yield path
        return
    for directory, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in SKIP_DIRS and not Path(directory, d).is_symlink()
        )
        for name in sorted(files):
            yield Path(directory, name)


def glob_matches(relative: str, pattern: str) -> bool:
    """按路径段实现 ** 的零层/多层语义，普通 * 不跨目录。"""
    parts, patterns = relative.split("/"), pattern.split("/")

    @lru_cache(maxsize=None)
    def match(i: int, j: int) -> bool:
        if j == len(patterns):
            return i == len(parts)
        if patterns[j] == "**":
            return match(i, j + 1) or (
                i < len(parts) and not parts[i].startswith(".") and match(i + 1, j)
            )
        return (
            i < len(parts)
            and (not parts[i].startswith(".") or patterns[j].startswith("."))
            and fnmatch.fnmatchcase(parts[i], patterns[j])
            and match(i + 1, j + 1)
        )

    return match(0, 0)


def search(root: Path, mode: str, pattern: str, path: Path, options: dict | None = None) -> dict:
    options = options or {}
    regex = re.compile(re.escape(pattern) if options.get("literal") else pattern,
                       re.IGNORECASE if options.get("ignore_case") else 0) if mode == "grep" else None
    results = []
    size = 0
    limited = False
    for index, candidate in enumerate(files_under(path)):
        if index >= 10_000:
            limited = True
            break
        target = candidate.resolve()
        if not target.is_relative_to(root) or check_sensitive_path(candidate):
            continue
        if mode == "glob":
            relative = candidate.relative_to(root).as_posix()
            if not glob_matches(relative, pattern):
                continue
            matches = [str(candidate)]
        else:
            file_glob = options.get("glob", "")
            relative = candidate.relative_to(root).as_posix()
            if file_glob and not glob_matches(relative if "/" in file_glob else candidate.name, file_glob):
                continue
            try:
                if target.stat().st_size > 2_000_000:
                    continue
                with target.open("rb") as handle:
                    data = handle.read(2_000_001)
                if len(data) > 2_000_000:
                    continue
                if b"\x00" in data:
                    continue
                lines = data.decode("utf-8").splitlines()
                matches = (
                    f"{candidate}:{i}: {line[:2000]}"
                    for i, line in enumerate(lines, 1)
                    if regex.search(line)
                )
            except (OSError, UnicodeError):
                continue
        for match in matches:
            results.append(match)
            size += len(match)
            if len(results) >= 200 or size >= 30_000:
                limited = True
                break
        if limited:
            break
    output = "\n".join(results) or "(无匹配结果)"
    if limited:
        output += "\n(达到搜索预算，结果已截断；请缩小路径或模式)"
    return {"success": True, "output": output}


if __name__ == "__main__":
    root, mode, pattern, path, options = json.loads(sys.stdin.read())
    try:
        result = search(Path(root), mode, pattern, Path(path), options)
    except (OSError, ValueError, re.error) as exc:
        result = {"success": False, "output": "", "error": f"搜索失败: {exc}"}
    print(json.dumps(result, ensure_ascii=False))
