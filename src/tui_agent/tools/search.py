"""有超时、可取消的搜索入口。"""

import asyncio
import json
import os
from pathlib import Path
import sys

from .base import ToolResult
from .sensitive_paths import check_sensitive_path
from .workspace import get_workspace_root, resolve_in_workspace


async def run_search(
    mode: str, pattern: str, path: str = ".", timeout: float = 5, *, options: dict | None = None
) -> ToolResult:
    target, error = resolve_in_workspace(path)
    if error:
        return ToolResult.fail(error)
    if not target.exists():
        return ToolResult.fail(f"路径不存在: {path}")
    if target.is_file():
        blocked = check_sensitive_path(target)
        if blocked:
            return ToolResult.fail(blocked)
    env = dict(os.environ)
    module_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = module_root + os.pathsep + env.get("PYTHONPATH", "")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tui_agent.tools.search_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        payload = json.dumps(
            [str(get_workspace_root()), mode, pattern, str(target), options or {}]
        ).encode()
        stdout, stderr = await asyncio.wait_for(process.communicate(payload), timeout)
        if process.returncode:
            return ToolResult.fail(
                f"搜索进程失败: {stderr.decode(errors='replace')[:1000]}"
            )
        return ToolResult(**json.loads(stdout))
    except asyncio.TimeoutError:
        return ToolResult.fail("搜索超时；请缩小范围或简化正则表达式")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
