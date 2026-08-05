"""Shell 命令执行工具"""

import asyncio

from .base import ToolBase, ToolResult, PermissionLevel
from .workspace import get_workspace_root, resolve_in_workspace


class ShellExecTool(ToolBase):
    name = "shell_exec"
    description = "执行非交互式 Shell 命令（不支持需要终端输入的程序），返回 stdout、stderr 和退出码"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录，默认为当前目录",
            },
        },
        "required": ["command"],
    }
    permission_level = PermissionLevel.SHELL

    async def execute(self, command: str, cwd: str | None = None) -> ToolResult:
        try:
            if cwd is None:
                cwd_path = get_workspace_root()
            else:
                cwd_path, err = resolve_in_workspace(cwd)
                if err:
                    return ToolResult.fail(err)
                assert cwd_path is not None
                if not cwd_path.is_dir():
                    return ToolResult.fail(f"工作目录不是目录: {cwd}")

            process = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd_path),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=60
            )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            output_parts = []
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(f"[stderr]\n{stderr_str}")

            output = "\n".join(output_parts) if output_parts else "(无输出)"

            if process.returncode != 0:
                return ToolResult(
                    success=True,  # 命令执行了，即使退出码非零
                    output=f"[退出码: {process.returncode}]\n{output}",
                )

            return ToolResult.ok(output)
        except asyncio.TimeoutError:
            return ToolResult.fail("命令执行超时 (60s)")
        except Exception as e:
            return ToolResult.fail(f"命令执行失败: {e}")
