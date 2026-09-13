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
from ..session.storage import save_session
from ..session.compressor import compress_if_needed, estimate_tokens


@dataclass
class RunState:
    turn_count: int = 0
    queued: list[dict] = field(default_factory=list)
    compression_failures: int = 0


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

    def stop(self, reason: str = "用户取消了操作；如需执行，请重新发起任务") -> None:
        """终止当前批次，保证工具结果配对。调用方先取消运行中的 Task。"""
        self.session.close_pending_tools(reason)
        self.permission_guard.deny()
        self.state.queued.clear()
        save_session(self.session)

    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        if self._busy or self.permission_guard.pending_tool_call is not None:
            yield AgentError("已有任务运行或等待确认，请先停止当前任务")
            return
        self._busy = True
        self.state = RunState()
        self.session.close_pending_tools()
        self.session.add_user_message(user_input)
        try:
            save_session(self.session)
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
                yield await self.executor.execute(pending)
            else:
                self.permission_guard.deny()
                self.executor.record(pending, False, f"用户拒绝了 {pending.name} 操作")
                yield PermissionDenied(pending.id, pending.name)
            save_session(self.session)

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

    async def _continue_loop(self) -> AsyncIterator[AgentEvent]:
        while self.state.turn_count < self.max_turns:
            self.state.turn_count += 1
            self.session.increment_turn()
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
                save_session(self.session)
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
                save_session(self.session)
                yield AgentError(message)
                yield AgentFinished(f"因错误终止: {message}")
                return

            self.session.add_assistant_message(
                "".join(text_buffer), tool_calls=tool_calls
            )
            save_session(self.session)
            if not tool_calls:
                yield AgentFinished("".join(text_buffer))
                return
            async for event in self._execute_tool_calls(tool_calls):
                yield event
                if isinstance(event, PermissionRequest):
                    return

        message = f"已达到最大轮次 ({self.max_turns})，任务终止"
        self.session.add_assistant_message(message)
        save_session(self.session)
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
                save_session(self.session)
                yield result
                continue

            tool = self.tool_registry.get(name)
            decision = self.permission_guard.check(call, tool.permission_level)
            if decision == PermissionDecision.ASK:
                self.state.queued = tool_calls[index + 1 :]
                save_session(self.session)
                yield PermissionRequest(
                    call.id, name, arguments, self._format_tool_summary(name, arguments)
                )
                return
            if decision == PermissionDecision.DENY:
                self.executor.record(call, False, f"用户拒绝了 {name} 操作")
                save_session(self.session)
                yield PermissionDenied(call.id, name)
                continue
            yield ToolCallStart(call.id, name, arguments)
            result = await self.executor.execute(call)
            save_session(self.session)
            yield result

    def _format_tool_summary(self, name: str, arguments: dict) -> str:
        if name == "shell_exec":
            return f"在本机执行命令（受当前用户系统权限约束）: {arguments['command']}"
        if name in ("write_file", "edit_file"):
            from ..tools.file_state import preview_change

            return preview_change(name, arguments)
        return f"{name}: {json.dumps(arguments, ensure_ascii=False)[:100]}"
