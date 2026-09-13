"""本机非交互式 Shell；进程组取消、超时及有界输出。"""

import asyncio
import os
import signal

from .base import ToolBase, ToolResult, PermissionLevel
from .shell_policy import check_shell_command
from .workspace import get_workspace_root, resolve_in_workspace


class ShellExecTool(ToolBase):
    name = "shell_exec"
    description = "在本机执行非交互式 Shell，受当前用户系统权限约束；工作目录不构成系统沙箱。返回 stdout、stderr、退出码。"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell 命令"},
            "cwd": {"type": "string", "description": "工作区内的工作目录"},
        },
        "required": ["command"],
    }
    permission_level = PermissionLevel.SHELL
    timeout = 60
    max_output_bytes = 1_000_000

    async def _read(self, stream) -> bytes:
        chunks = bytearray()
        omitted = False
        while data := await stream.read(65536):
            remaining = self.max_output_bytes - len(chunks)
            chunks.extend(data[: max(0, remaining)])
            omitted |= len(data) > remaining
        if omitted:
            chunks.extend("\n[输出超过捕获上限，后续内容已丢弃]".encode())
        return bytes(chunks)

    async def _kill_tree(self, process) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.returncode is None:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), 5)
        try:
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            pass

    async def execute(self, command: str, cwd: str | None = None) -> ToolResult:
        blocked = check_shell_command(command)
        if blocked:
            return ToolResult.fail(blocked)
        cwd_path, err = resolve_in_workspace(cwd or str(get_workspace_root()))
        if err:
            return ToolResult.fail(err)
        if not cwd_path.is_dir():
            return ToolResult.fail(f"工作目录不是目录: {cwd}")
        process = None
        readers = []
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd_path),
                start_new_session=(os.name == "posix"),
            )
            readers = [
                asyncio.create_task(self._read(process.stdout)),
                asyncio.create_task(self._read(process.stderr)),
            ]
            try:
                stdout, stderr, _ = await asyncio.wait_for(
                    asyncio.gather(*readers, process.wait()),
                    self.timeout,
                )
            except asyncio.TimeoutError:
                await self._kill_tree(process)
                return ToolResult.fail(f"命令执行超时 ({self.timeout}s)，已终止进程树")
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            output = (
                "\n".join(
                    x
                    for x in (
                        stdout_text,
                        f"[stderr]\n{stderr_text}" if stderr_text else "",
                    )
                    if x
                )
                or "(无输出)"
            )
            if process.returncode:
                return ToolResult.fail(f"[退出码: {process.returncode}]\n{output}")
            return ToolResult.ok(output)
        except asyncio.CancelledError:
            if process is not None:
                await self._kill_tree(process)
            raise
        except Exception as exc:
            if process is not None:
                await self._kill_tree(process)
            return ToolResult.fail(f"命令执行失败: {exc}")
        finally:
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            if readers:
                await asyncio.gather(*readers, return_exceptions=True)
