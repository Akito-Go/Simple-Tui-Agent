"""文件写入工具"""

from pathlib import Path

from .base import ToolBase, ToolResult, PermissionLevel
from .workspace import resolve_in_workspace


class WriteFileTool(ToolBase):
    name = "write_file"
    description = "创建或覆盖文件，写入指定内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容",
            },
        },
        "required": ["path", "content"],
    }
    permission_level = PermissionLevel.WRITE

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            assert p is not None
            # 确保父目录存在
            p.parent.mkdir(parents=True, exist_ok=True)

            is_new = not p.exists()
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)

            action = "创建" if is_new else "覆盖"
            lines = content.count("\n") + 1
            return ToolResult.ok(f"已{action}文件: {path} ({lines} 行)")
        except PermissionError as e:
            return ToolResult.fail(f"权限不足: {e}")
        except Exception as e:
            return ToolResult.fail(f"写入文件失败: {e}")
