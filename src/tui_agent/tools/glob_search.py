"""有界文件模式搜索。"""

from pathlib import Path

from .base import ToolBase, ToolResult, PermissionLevel
from .search import run_search
from .workspace import get_workspace_root


class GlobSearchTool(ToolBase):
    name = "glob_search"
    description = "使用 glob 模式搜索工作区文件，如 **/*.py；跳过依赖和构建目录"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob 文件模式"},
        },
        "required": ["pattern"],
    }
    permission_level = PermissionLevel.READ

    async def execute(self, pattern: str) -> ToolResult:
        candidate = Path(pattern)
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(get_workspace_root())
            except ValueError:
                return ToolResult.fail("模式超出工作区范围")
        if ".." in candidate.parts:
            return ToolResult.fail("模式超出工作区范围")
        return await run_search("glob", candidate.as_posix())
