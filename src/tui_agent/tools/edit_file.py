"""精确编辑：拒绝空匹配、歧义匹配与过期文件。"""

from .base import ToolBase, ToolResult, PermissionLevel
from .file_state import FileStateCache, atomic_write, read_bytes
from .workspace import resolve_in_workspace


class EditFileTool(ToolBase):
    name = "edit_file"
    description = "替换已读取文件中的唯一匹配字符串；多处匹配请提供更多上下文"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_string": {"type": "string", "description": "唯一匹配的旧内容"},
            "new_string": {"type": "string", "description": "替换内容"},
        },
        "required": ["path", "old_string", "new_string"],
    }
    permission_level = PermissionLevel.WRITE

    def __init__(self, state: FileStateCache | None = None):
        self.state = state

    async def execute(self, path: str, old_string: str, new_string: str) -> ToolResult:
        try:
            if not old_string:
                return ToolResult.fail("old_string 不能为空")
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            data = read_bytes(p)
            if self.state is not None:
                self.state.validate(p, data, old_string)
            content = data.decode("utf-8")
            count = content.count(old_string)
            if count != 1:
                return ToolResult.fail(
                    "未找到匹配内容"
                    if count == 0
                    else f"匹配到 {count} 处，请提供更多上下文以唯一定位"
                )
            new_content = content.replace(old_string, new_string, 1)
            atomic_write(p, new_content)
            if self.state is not None:
                previous = self.state.entries[p]
                position = content.index(old_string)
                delta = len(new_string) - len(old_string)
                regions = [
                    (
                        start + (delta if start > position else 0),
                        end + (delta if end > position else 0),
                    )
                    for start, end in previous.regions
                ]
                self.state.entries.pop(p)
                for start, end in regions:
                    self.state.record(
                        p, new_content.encode(), new_content[start:end], False, start
                    )
            return ToolResult.ok(f"已编辑文件: {path} (替换 1 处)")
        except (OSError, ValueError) as exc:
            return ToolResult.fail(f"编辑文件失败: {exc}")
