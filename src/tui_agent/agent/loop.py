"""Agent Loop 核心 — 自实现，不使用任何 Agent SDK/Framework"""

import json
from typing import AsyncIterator

from .types import (
    TextDelta,
    ToolCallStart,
    ToolCallResult,
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


class AgentLoop:
    """Agent 主循环 — 模型决策 → 工具调用 → 结果回传 → 继续推理"""

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
        # 权限确认暂停时，尚未执行的后续 tool_calls
        self._queued_tool_calls: list[dict] = []

    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """
        执行 Agent 主循环，流式产出事件。

        Args:
            user_input: 用户输入

        Yields:
            AgentEvent: 各类事件，供 TUI 层消费
        """
        self.session.add_user_message(user_input)
        async for event in self._continue_loop():
            yield event

    async def continue_with_confirmation(self, confirmed: bool) -> AsyncIterator[AgentEvent]:
        """
        用户确认/拒绝后继续执行。

        Args:
            confirmed: True 表示确认，False 表示拒绝
        """
        pending = self.permission_guard.pending_tool_call
        if pending is None:
            yield AgentError(message="没有待确认的操作")
            return

        if confirmed:
            self.permission_guard.confirm()
            yield ToolCallStart(tool_id=pending.id, name=pending.name, arguments=pending.arguments)
            result = await self.tool_registry.execute(pending.name, pending.arguments)
            result_text = result.output if result.success else f"[错误] {result.error}"
            self.session.add_tool_result(pending.id, pending.name, result_text)
            yield ToolCallResult(
                tool_id=pending.id,
                name=pending.name,
                success=result.success,
                output=result_text,
            )
        else:
            self.permission_guard.deny()
            result_text = f"用户拒绝了 {pending.name} 操作"
            self.session.add_tool_result(pending.id, pending.name, result_text)
            yield PermissionDenied(tool_id=pending.id, name=pending.name)

        # 先消化同轮剩余工具，再继续推理
        queued = self._queued_tool_calls
        self._queued_tool_calls = []
        if queued:
            async for event in self._execute_tool_calls(queued):
                yield event
                if isinstance(event, PermissionRequest):
                    save_session(self.session)
                    return

        async for event in self._continue_loop():
            yield event

    async def _continue_loop(self) -> AsyncIterator[AgentEvent]:
        """从当前上下文继续推理"""
        for _ in range(self.session.turn_count, self.max_turns):
            self.session.increment_turn()

            from ..session.compressor import compress_if_needed
            await compress_if_needed(self.session, self.llm_provider, self.context_max_tokens)

            messages = self.session.build_messages()
            tools_schema = self.tool_registry.to_openai_schemas()

            text_buffer: list[str] = []
            tool_calls_buffer: list[dict] = []

            try:
                async for event in self.llm_provider.chat(
                    messages=messages,
                    tools=tools_schema,
                    stream=True,
                ):
                    if event["type"] == "text_delta":
                        text_buffer.append(event["content"])
                        yield TextDelta(content=event["content"])
                    elif event["type"] == "tool_calls":
                        tool_calls_buffer = event["tool_calls"]
                    elif event["type"] == "error":
                        error_msg = event["message"]
                        self.session.add_assistant_message(f"[错误] {error_msg}")
                        yield AgentError(message=error_msg)
                        yield AgentFinished(message=f"因错误终止: {error_msg}")
                        save_session(self.session)
                        return
                    elif event["type"] == "finish":
                        break
            except Exception as e:
                error_msg = f"Agent Loop 异常: {str(e)}"
                self.session.add_assistant_message(f"[异常] {error_msg}")
                yield AgentError(message=error_msg)
                yield AgentFinished(message=f"因异常终止: {error_msg}")
                save_session(self.session)
                return

            if tool_calls_buffer:
                self.session.add_assistant_message(
                    content="".join(text_buffer),
                    tool_calls=tool_calls_buffer,
                )
                async for event in self._execute_tool_calls(tool_calls_buffer):
                    yield event
                    if isinstance(event, PermissionRequest):
                        save_session(self.session)
                        return
                continue

            full_text = "".join(text_buffer)
            self.session.add_assistant_message(content=full_text)
            yield AgentFinished(message=full_text)
            save_session(self.session)
            return

        msg = f"已达到最大轮次 ({self.max_turns})，任务终止"
        self.session.add_assistant_message(msg)
        yield AgentFinished(message=msg)
        save_session(self.session)

    async def _execute_tool_calls(self, tool_calls: list[dict]) -> AsyncIterator[AgentEvent]:
        """
        顺序执行工具调用。若遇到需确认的工具，将后续调用放入队列并 yield PermissionRequest。
        """
        for index, tc in enumerate(tool_calls):
            tool_name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                arguments = {}

            tool = self.tool_registry.get(tool_name)
            if tool is None:
                result_text = f"未知工具: {tool_name}"
                self.session.add_tool_result(tc["id"], tool_name, result_text)
                yield ToolCallResult(
                    tool_id=tc["id"],
                    name=tool_name,
                    success=False,
                    output=result_text,
                )
                continue

            tool_call_obj = ToolCall(id=tc["id"], name=tool_name, arguments=arguments)
            decision = self.permission_guard.check(tool_call_obj, tool.permission_level)

            if decision == PermissionDecision.ASK:
                self._queued_tool_calls = tool_calls[index + 1 :]
                yield PermissionRequest(
                    tool_id=tc["id"],
                    name=tool_name,
                    arguments=arguments,
                    summary=self._format_tool_summary(tool_name, arguments),
                )
                return

            if decision == PermissionDecision.DENY:
                result_text = f"用户拒绝了 {tool_name} 操作"
                self.session.add_tool_result(tc["id"], tool_name, result_text)
                yield PermissionDenied(tool_id=tc["id"], name=tool_name)
                continue

            yield ToolCallStart(tool_id=tc["id"], name=tool_name, arguments=arguments)
            result = await self.tool_registry.execute(tool_name, arguments)
            result_text = result.output if result.success else f"[错误] {result.error}"
            self.session.add_tool_result(tc["id"], tool_name, result_text)
            yield ToolCallResult(
                tool_id=tc["id"],
                name=tool_name,
                success=result.success,
                output=result_text,
            )

    def _format_tool_summary(self, name: str, arguments: dict) -> str:
        """格式化工具调用摘要"""
        if name == "write_file":
            return f"写入文件: {arguments.get('path', '?')}"
        if name == "edit_file":
            return f"编辑文件: {arguments.get('path', '?')}"
        if name == "shell_exec":
            cmd = arguments.get("command", "?")
            return f"执行命令: {cmd[:80]}"
        return f"{name}: {json.dumps(arguments, ensure_ascii=False)[:100]}"
