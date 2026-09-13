"""有界文件读取与已读状态记录。"""

import asyncio

from .base import ToolBase, ToolResult, PermissionLevel
from .file_state import FileStateCache, read_bytes
from .sensitive_paths import check_sensitive_path
from .workspace import resolve_in_workspace


class ReadFileTool(ToolBase):
    name = "read_file"
    description = "读取工作区文本文件，支持行范围或 char_offset 字符游标；最多 500 行、28000 字符，修改前必须读取"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "start_line": {"type": "integer", "description": "起始行号（1-based）"},
            "char_offset": {
                "type": "integer",
                "description": "从 0 开始的字符偏移；用于续读，不能同时指定行范围",
            },
            "end_line": {"type": "integer", "description": "结束行号（包含）"},
        },
        "required": ["path"],
    }
    permission_level = PermissionLevel.READ

    def __init__(self, state: FileStateCache | None = None):
        self.state = state

    async def execute(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        char_offset: int | None = None,
    ) -> ToolResult:
        # I/O 在工作线程中执行；取消后不发布已读状态。
        try:
            if char_offset is not None and (
                char_offset < 0 or start_line is not None or end_line is not None
            ):
                return ToolResult.fail("char_offset 必须 >= 0，且不能与行范围同时使用")
            start = start_line if start_line is not None else 1
            if start < 1 or (end_line is not None and end_line < start):
                return ToolResult.fail(
                    "行范围无效：起始行必须 >= 1，结束行不得小于起始行"
                )
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            sensitive = check_sensitive_path(p)
            if sensitive:
                return ToolResult.fail(sensitive)
            data = await asyncio.to_thread(read_bytes, p)
            text = data.decode("utf-8")
            lines = text.splitlines(keepends=True)
            offset = (
                min(char_offset, len(text))
                if char_offset is not None
                else sum(map(len, lines[: start - 1]))
            )
            if char_offset is not None:
                start = len(text[:offset].splitlines()) + (
                    not text[:offset] or text[:offset].endswith(("\n", "\r"))
                )
                chosen = text[offset:].splitlines(keepends=True)[:500]
            else:
                chosen = lines[start - 1 : min(end_line or len(lines), start + 499)]
            visible = ""
            numbered = []
            remaining = 28_000
            for index, line in enumerate(chosen, start):
                remaining -= len(f"{index:4d} | ") + 1
                if len(line) > remaining:
                    prefix = line[: max(0, remaining)]
                    if prefix:
                        visible += prefix
                        numbered.append(f"{index:4d} | {prefix.rstrip()} …[本行已截断]")
                    break
                remaining -= len(line)
                visible += line
                numbered.append(f"{index:4d} | {line.rstrip()}")
            full = offset == 0 and visible == text
            if self.state is not None:
                self.state.record(p, data, visible, full, offset)
            output = "\n".join(numbered)
            if offset + len(visible) < len(text):
                output += f"\n(共 {len(lines)} 行；本次显示 {len(numbered)} 行，续读请指定 char_offset={offset + len(visible)}；文件变化后请从头读取)"
            return ToolResult.ok(output)
        except (OSError, ValueError) as exc:
            return ToolResult.fail(f"读取文件失败: {exc}")
