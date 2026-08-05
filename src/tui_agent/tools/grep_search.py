"""内容搜索工具 (grep)"""

import re
from pathlib import Path

from .base import ToolBase, ToolResult, PermissionLevel
from .sensitive_paths import check_sensitive_path
from .workspace import is_under_workspace, resolve_in_workspace


class GrepSearchTool(ToolBase):
    name = "grep_search"
    description = "在文件中搜索匹配正则表达式的内容，返回文件路径、行号和行内容"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "正则表达式搜索模式",
            },
            "path": {
                "type": "string",
                "description": "搜索路径，默认为当前目录",
            },
        },
        "required": ["pattern"],
    }
    permission_level = PermissionLevel.READ

    async def execute(self, pattern: str, path: str = "./") -> ToolResult:
        try:
            regex = re.compile(pattern)
            search_path, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            assert search_path is not None
            results: list[str] = []

            if search_path.is_file():
                sensitive_err = check_sensitive_path(search_path)
                if sensitive_err:
                    return ToolResult.fail(sensitive_err)
                files = [search_path]
            elif search_path.is_dir():
                skip_dirs = {".git", "__pycache__", ".tui-agent", "node_modules", ".venv", "venv"}
                files = []
                for p in search_path.rglob("*"):
                    if p.is_file() and is_under_workspace(p) and not any(d in p.parts for d in skip_dirs):
                        if check_sensitive_path(p):
                            continue
                        files.append(p)
            else:
                return ToolResult.fail(f"路径不存在: {path}")

            for file_path in files:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        for line_no, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_no}: {line.rstrip()}")
                except (UnicodeDecodeError, PermissionError):
                    continue

            if not results:
                return ToolResult.ok("(无匹配结果)")

            total = len(results)
            shown = results[:200]
            output = "\n".join(shown)
            if total > len(shown):
                output += f"\n(共 {total} 条匹配，显示前 {len(shown)} 条)"
            return ToolResult.ok(output)
        except re.error as e:
            return ToolResult.fail(f"正则表达式错误: {e}")
        except Exception as e:
            return ToolResult.fail(f"Grep 搜索失败: {e}")
