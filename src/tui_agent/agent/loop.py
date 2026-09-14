"""Agent 运行时：任务状态、确认与统一工具执行。"""

import asyncio
import json
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import AsyncIterator

from .executor import ToolExecutor
from .types import (
    TextDelta,
    ToolCallStart,
    PermissionRequest,
    PermissionDenied,
    AgentFinished,
    AgentError,
    AgentEvent,
)
from ..llm.provider import LLMProvider
from ..tools.registry import ToolRegistry
from ..permissions.guard import PermissionGuard, ToolCall
from ..permissions.policy import PermissionDecision
from ..session.manager import SessionManager
from ..session.checkpoint import Checkpoint, RESUMABLE
from copy import deepcopy
from ..session.storage import save_session
from ..session.compressor import compress_if_needed, estimate_tokens


@dataclass
class RunState:
    turn_count: int = 0
    queued: list[dict] = field(default_factory=list)
    compression_failures: int = 0
    goal: str = ""
    phase: str = "就绪"
    completed_tools: int = 0
    total_tools: int = 0
    changed_files: list[str] = field(default_factory=list)


class AgentLoop:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        permission_guard: PermissionGuard,
        session: SessionManager,
        max_turns: int = 50,
        context_max_tokens: int = 32000,
    ):
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.permission_guard = permission_guard
        self.session = session
        self.max_turns = max_turns
        self.context_max_tokens = context_max_tokens
        self.state = RunState()
        self.executor = ToolExecutor(tool_registry, session)
        self._busy = False
        self.checkpoint = None

    def _save(self, status=None, phase=None):
        save_session(self.session)
        if self.checkpoint is not None:
            self.checkpoint.update(self.session, self.state, status, phase)

    def stop(self, reason: str = "用户取消了操作；如需执行，请重新发起任务") -> None:
        """终止当前批次，保证工具结果配对。调用方先取消运行中的 Task。"""
        self.session.close_pending_tools(reason)
        self.permission_guard.deny()
        self.state.queued.clear()
        if self.checkpoint and self.checkpoint.data["status"] in RESUMABLE:
            self._save("interrupted", "已停止")
        else:
            self._save()

    async def run(self, user_input: str, *, checkpoint: Checkpoint | None = None) -> AsyncIterator[AgentEvent]:
        if self._busy or self.permission_guard.pending_tool_call is not None:
            yield AgentError("已有任务运行或等待确认，请先停止当前任务")
            return
        self._busy = True
        self.checkpoint = checkpoint or Checkpoint.create(user_input)
        self.state = RunState(goal=self.checkpoint.data["goal"], phase="分析")
        file_state = getattr(self.tool_registry, "file_state", None)
        if file_state is not None:
            file_state.checkpoint = self.checkpoint
        self.session.close_pending_tools()
        self.session.add_user_message(user_input)
        try:
            self._save("running", "分析")
            async with aclosing(self._continue_loop()) as events:
                async for event in events:
                    yield event
        except asyncio.CancelledError:
            self.stop()
            raise
        except Exception:
            self.stop("工具执行异常，操作已终止")
            raise
        finally:
            self._busy = False
            if self.checkpoint and self.checkpoint.data["status"] == "running":
                self._save("interrupted", "已中断")

    async def resume(self, checkpoint_id: str) -> AsyncIterator[AgentEvent]:
        if self._busy or self.permission_guard.pending_tool_call is not None:
            yield AgentError("请先停止当前任务")
            return
        checkpoint = Checkpoint.load(checkpoint_id)
        if checkpoint.data["status"] not in RESUMABLE:
            raise ValueError("该任务已完成、已撤销或正在撤销，不能恢复")
        report = checkpoint.inspect_files()
        # 创建独立续接会话，保留旧日志，避免向旧会话追加重叠历史。
        session = SessionManager(model=self.session.model)
        session.messages = deepcopy(checkpoint.data["messages"])
        session.set_model(self.session.model)
        session._transcript = deepcopy(session.messages)
        session.turn_count = checkpoint.data.get("session_turn_count", 0)
        session.close_pending_tools("中断时未确认是否完成；先检查现状，不得直接重放")
        self.session = session
        self.executor.session = session
        self.permission_guard.reset_session_allow_all()
        state = getattr(self.tool_registry, "file_state", None)
        if state is not None:
            state.clear()
        prompt = (
            f"继续未完成任务，原始目标：{checkpoint.data['goal']}\n"
            f"中断阶段：{checkpoint.data['phase']}\n文件核对：\n"
            + ("\n".join(report) or "无已记录的文件写入")
            + "\n请先读取现状判断剩余工作；不得直接重放上次待确认操作或 Shell 命令。"
            "Shell 的外部副作用不在文件检查点覆盖范围内。"
        )
        continuation = Checkpoint.create(checkpoint.data["goal"])
        continuation.data["source_checkpoint"] = checkpoint_id
        try:
            async with aclosing(self.run(prompt, checkpoint=continuation)) as events:
                async for event in events:
                    yield event
        finally:
            if continuation.path.exists():
                checkpoint.data["status"] = "continued"
                checkpoint.save()

    async def continue_with_confirmation(
        self, confirmed: bool, allow_session: bool = False
    ) -> AsyncIterator[AgentEvent]:
        pending = self.permission_guard.pending_tool_call
        if self._busy or pending is None:
            yield AgentError("没有待确认的操作，或当前任务正在运行")
            return
        self._busy = True
        try:
            if confirmed:
                if allow_session:
                    self.permission_guard.enable_session_allow_all()
                self.permission_guard.confirm()
                yield ToolCallStart(pending.id, pending.name, pending.arguments)
                result = await self.executor.execute(pending)
                self._save("running", "执行工具")
                yield result
            else:
                self.permission_guard.deny()
                self.executor.record(pending, False, f"用户拒绝了 {pending.name} 操作")
                yield PermissionDenied(pending.id, pending.name)
            self._save("running", "分析")

            queued, self.state.queued = self.state.queued, []
            async for event in self._execute_tool_calls(queued):
                yield event
                if isinstance(event, PermissionRequest):
                    return
            async with aclosing(self._continue_loop()) as events:
                async for event in events:
                    yield event
        except asyncio.CancelledError:
            self.stop()
            raise
        except Exception:
            self.stop("工具执行异常，操作已终止")
            raise
        finally:
            self._busy = False
            if self.checkpoint and self.checkpoint.data["status"] == "running":
                self._save("interrupted", "已中断")

    async def _continue_loop(self) -> AsyncIterator[AgentEvent]:
        while self.state.turn_count < self.max_turns:
            self.state.turn_count += 1
            self.session.increment_turn()
            self._save("running", "分析")
            tools_schema = self.tool_registry.to_openai_schemas()
            # 工具定义也消耗输入预算，另留出回复空间。
            reserve = min(2048, self.context_max_tokens // 8)
            input_budget = max(
                1,
                self.context_max_tokens
                - reserve
                - estimate_tokens([{"tools": tools_schema}]),
            )
            if self.state.compression_failures < 3:
                try:
                    await compress_if_needed(
                        self.session, self.llm_provider, input_budget
                    )
                except (ValueError, RuntimeError):
                    self.state.compression_failures += 1
            messages = self.session.build_api_messages()
            if estimate_tokens(messages) > input_budget:
                message = (
                    "上下文仍超出预算，原始历史已保留；请提高上下文预算或开始新会话"
                )
                self._save("failed", "失败")
                yield AgentError(message)
                yield AgentFinished(message)
                return

            text_buffer: list[str] = []
            tool_calls: list[dict] = []
            try:
                async with aclosing(
                    self.llm_provider.chat(
                        messages=messages, tools=tools_schema, stream=True
                    )
                ) as stream:
                    async for event in stream:
                        if event["type"] in ("text_delta", "text"):
                            text_buffer.append(event["content"])
                            yield TextDelta(event["content"])
                        elif event["type"] == "tool_calls":
                            tool_calls = event["tool_calls"]
                        elif event["type"] == "error":
                            raise RuntimeError(event["message"])
                        elif event["type"] == "finish":
                            break
            except asyncio.CancelledError:
                if text_buffer:
                    self.session.add_assistant_message("".join(text_buffer))
                raise
            except Exception as exc:
                message = f"LLM 请求失败: {exc}"
                self.session.add_assistant_message(
                    "".join(text_buffer) + f"\n[错误] {message}"
                )
                self._save("failed", "失败")
                yield AgentError(message)
                yield AgentFinished(f"因错误终止: {message}")
                return

            self.session.add_assistant_message(
                "".join(text_buffer), tool_calls=tool_calls
            )
            self._save()
            if not tool_calls:
                self._save("completed", "完成")
                yield AgentFinished("".join(text_buffer))
                return
            async for event in self._execute_tool_calls(tool_calls):
                yield event
                if isinstance(event, PermissionRequest):
                    return

        message = f"已达到最大轮次 ({self.max_turns})，任务终止"
        self.session.add_assistant_message(message)
        self._save("limit", "达到轮次上限")
        yield AgentFinished(message)

    async def _execute_tool_calls(
        self, tool_calls: list[dict]
    ) -> AsyncIterator[AgentEvent]:
        for index, tc in enumerate(tool_calls):
            name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                arguments = None
            call = ToolCall(tc["id"], name, arguments)
            error = self.tool_registry.validate(name, arguments)
            if not error and name == "shell_exec":
                from ..tools.shell_policy import check_shell_command

                error = check_shell_command(arguments["command"])
            if error:
                result = self.executor.record(call, False, error)
                self._save()
                yield result
                continue

            tool = self.tool_registry.get(name)
            decision = self.permission_guard.check(call, tool.permission_level)
            if decision == PermissionDecision.ASK:
                self.state.queued = tool_calls[index + 1 :]
                self._save("waiting", "等待确认")
                yield PermissionRequest(
                    call.id, name, arguments, self._format_tool_summary(name, arguments)
                )
                return
            if decision == PermissionDecision.DENY:
                self.executor.record(call, False, f"用户拒绝了 {name} 操作")
                self._save()
                yield PermissionDenied(call.id, name)
                continue
            self._save("running", f"执行 {name}")
            yield ToolCallStart(call.id, name, arguments)
            result = await self.executor.execute(call)
            self._save()
            yield result

    def _format_tool_summary(self, name: str, arguments: dict) -> str:
        if name == "shell_exec":
            from ..tools.workspace import get_workspace_root

            return f"在本机执行命令（受当前用户系统权限约束）: {arguments['command']}\n工作目录：{arguments.get('cwd') or get_workspace_root()}\n文件影响未追踪；Shell 修改不计入文件统计，也不支持自动撤销。"
        if name in ("write_file", "edit_file"):
            from ..tools.file_state import preview_change

            return preview_change(name, arguments)
        return f"{name}: {json.dumps(arguments, ensure_ascii=False)[:100]}"
