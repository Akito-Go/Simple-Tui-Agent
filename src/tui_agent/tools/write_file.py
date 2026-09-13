"""文件写入：已读状态校验与原子替换。"""

from .base import ToolBase, ToolResult, PermissionLevel
from .file_state import FileStateCache, atomic_write, read_bytes
from .workspace import resolve_in_workspace


class WriteFileTool(ToolBase):
    name = "write_file"
    description = "创建或覆盖文本文件；覆盖现有文件前需完整读取，外部修改后需重新读取"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "完整文件内容"},
        },
        "required": ["path", "content"],
    }
    permission_level = PermissionLevel.WRITE

    def __init__(self, state: FileStateCache | None = None):
        self.state = state

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            exists = p.exists()
            if exists and self.state is not None:
                self.state.validate(p, read_bytes(p))
            atomic_write(p, content)
            if self.state is not None:
                self.state.record(p, content.encode(), content, True)
            return ToolResult.ok(f"已{'覆盖' if exists else '创建'}文件: {path}")
        except (OSError, ValueError) as exc:
            return ToolResult.fail(f"写入文件失败: {exc}")
