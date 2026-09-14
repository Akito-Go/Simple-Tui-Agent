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
            "glob": {"type": "string", "description": "文件筛选，如 *.py 或 src/**/*.py（相对工作区）"},
            "ignore_case": {"type": "boolean", "description": "忽略大小写，默认 false"},
            "literal": {"type": "boolean", "description": "将 pattern 作为普通文本，默认 false"},
        },
        "required": ["pattern"],
    }
    permission_level = PermissionLevel.READ

    async def execute(self, pattern: str, path: str = ".", glob: str = "", ignore_case: bool = False, literal: bool = False) -> ToolResult:
        return await run_search("grep", pattern, path, options=dict(glob=glob, ignore_case=ignore_case, literal=literal))
