"""Glob 文件匹配工具"""

import glob as glob_module
from pathlib import Path

from .base import ToolBase, ToolResult, PermissionLevel
from .workspace import get_workspace_root, is_under_workspace, resolve_in_workspace


class GlobSearchTool(ToolBase):
    name = "glob_search"
    description = "使用 glob 模式匹配文件，返回匹配的文件路径列表"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob 匹配模式，如 **/*.py 或 src/**/*.ts",
            }
        },
        "required": ["pattern"],
    }
    permission_level = PermissionLevel.READ

    async def execute(self, pattern: str) -> ToolResult:
        try:
            root = get_workspace_root()
            pattern_path = Path(pattern)
            if pattern_path.is_absolute():
                search_pattern = str(pattern_path)
            else:
                search_pattern = str(root / pattern)

            matches = glob_module.glob(search_pattern, recursive=True, include_hidden=False)
            safe_matches = []
            for match in matches:
                resolved = Path(match).resolve()
                if is_under_workspace(resolved):
                    safe_matches.append(match)

            if not safe_matches:
                return ToolResult.ok("(无匹配文件)")

            safe_matches.sort()
            max_matches = 200
            if len(safe_matches) > max_matches:
                shown = safe_matches[:max_matches]
                return ToolResult.ok(
                    "\n".join(shown) + f"\n(共 {len(safe_matches)} 个匹配，显示前 {max_matches} 个)"
                )
            return ToolResult.ok("\n".join(safe_matches))
        except Exception as e:
            return ToolResult.fail(f"Glob 搜索失败: {e}")
