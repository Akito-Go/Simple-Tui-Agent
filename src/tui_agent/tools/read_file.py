"""文件读取工具"""

from pathlib import Path

from .base import ToolBase, ToolResult, PermissionLevel
from .sensitive_paths import check_sensitive_path
from .workspace import resolve_in_workspace


class ReadFileTool(ToolBase):
    name = "read_file"
    description = "读取文件内容，支持指定行范围"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号 (1-based)，可选",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号 (1-based，包含)，可选",
            },
        },
        "required": ["path"],
    }
    permission_level = PermissionLevel.READ

    async def execute(
        self, path: str, start_line: int | None = None, end_line: int | None = None
    ) -> ToolResult:
        try:
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            assert p is not None
            if not p.exists():
                return ToolResult.fail(f"文件不存在: {path}")
            if not p.is_file():
                return ToolResult.fail(f"路径不是文件: {path}")

            sensitive_err = check_sensitive_path(p)
            if sensitive_err:
                return ToolResult.fail(sensitive_err)

            with open(p, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if start_line is not None or end_line is not None:
                start = (start_line or 1) - 1
                end = end_line if end_line is not None else len(lines)
                lines = lines[start:end]

            total_lines = len(lines)
            max_lines = 500
            truncated = total_lines > max_lines
            if truncated:
                lines = lines[:max_lines]

            # 添加行号
            numbered = []
            base = (start_line or 1)
            for i, line in enumerate(lines):
                numbered.append(f"{base + i:4d} | {line.rstrip()}")

            output = "\n".join(numbered)
            if truncated:
                output += f"\n(共 {total_lines} 行，显示前 {max_lines} 行)"
            return ToolResult.ok(output)
        except UnicodeDecodeError:
            return ToolResult.fail(f"无法以文本方式读取文件: {path}")
        except Exception as e:
            return ToolResult.fail(f"读取文件失败: {e}")
