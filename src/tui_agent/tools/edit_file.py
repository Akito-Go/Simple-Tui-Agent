"""文件编辑工具 — 字符串查找替换"""

from pathlib import Path

from .base import ToolBase, ToolResult, PermissionLevel
from .workspace import resolve_in_workspace


class EditFileTool(ToolBase):
    name = "edit_file"
    description = "在文件中查找并替换指定字符串"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
            "old_string": {
                "type": "string",
                "description": "要替换的旧字符串",
            },
            "new_string": {
                "type": "string",
                "description": "替换后的新字符串",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }
    permission_level = PermissionLevel.WRITE

    async def execute(self, path: str, old_string: str, new_string: str) -> ToolResult:
        try:
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            assert p is not None
            if not p.exists():
                return ToolResult.fail(f"文件不存在: {path}")
            if not p.is_file():
                return ToolResult.fail(f"路径不是文件: {path}")

            with open(p, "r", encoding="utf-8") as f:
                content = f.read()

            if old_string not in content:
                return ToolResult.fail(f"未找到匹配内容: {old_string[:50]}...")

            # 只替换第一次出现
            new_content = content.replace(old_string, new_string, 1)

            with open(p, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult.ok(f"已编辑文件: {path} (替换 1 处)")
        except Exception as e:
            return ToolResult.fail(f"编辑文件失败: {e}")
