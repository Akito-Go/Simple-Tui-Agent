"""有界正则搜索，敏感文件与工作区检查统一执行。"""

from .base import ToolBase, ToolResult, PermissionLevel
from .search import run_search


class GrepSearchTool(ToolBase):
    name = "grep_search"
    description = (
        "搜索文本文件的正则匹配；跳过依赖、构建目录、敏感及大文件，最多返回 200 条"
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "正则表达式"},
            "path": {"type": "string", "description": "搜索文件或目录，默认工作区"},
        },
        "required": ["pattern"],
    }
    permission_level = PermissionLevel.READ

    async def execute(self, pattern: str, path: str = ".") -> ToolResult:
        return await run_search("grep", pattern, path)
