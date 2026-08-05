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
from ..tools.base import PermissionLevel
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

    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """
        执行 Agent 主循环，流式产出事件。

        Args:
            user_input: 用户输入

        Yields:
            AgentEvent: 各类事件，供 TUI 层消费
        """
        # 添加用户消息到会话
        self.session.add_user_message(user_input)

        for turn in range(self.max_turns):
            self.session.increment_turn()

            # 0. 上下文压缩检查
            from ..session.compressor import compress_if_needed
            await compress_if_needed(self.session, self.llm_provider, self.context_max_tokens)

            # 1. 组装上下文
            messages = self.session.build_messages()
            tools_schema = self.tool_registry.to_openai_schemas()

            # 2. 调用 LLM (流式)
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

            # 3. 处理响应
            if tool_calls_buffer:
                # 记录助手消息（含工具调用）
                self.session.add_assistant_message(
                    content="".join(text_buffer),
                    tool_calls=tool_calls_buffer,
                )

                # 处理每个工具调用
                for tc in tool_calls_buffer:
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

                    # 4. 权限检查
                    tool_call_obj = ToolCall(id=tc["id"], name=tool_name, arguments=arguments)
                    decision = self.permission_guard.check(tool_call_obj, tool.permission_level)

                    if decision == PermissionDecision.ASK:
                        # 需要用户确认 — 暂停并等待
                        yield PermissionRequest(
                            tool_id=tc["id"],
                            name=tool_name,
                            arguments=arguments,
                            summary=self._format_tool_summary(tool_name, arguments),
                        )
                        # 注意：实际确认由 TUI 层处理，这里返回让 TUI 等待用户输入
                        # 在 TUI 集成中，用户确认后会重新调用 run_continue
                        save_session(self.session)
                        return

                    elif decision == PermissionDecision.DENY:
                        result_text = f"用户拒绝了 {tool_name} 操作"
                        self.session.add_tool_result(tc["id"], tool_name, result_text)
                        yield PermissionDenied(tool_id=tc["id"], name=tool_name)
                        continue

                    # 5. 执行工具
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

                # 工具结果已注入上下文，继续下一轮推理
                continue

            else:
                # 纯文本回复
                full_text = "".join(text_buffer)
                self.session.add_assistant_message(content=full_text)
                yield AgentFinished(message=full_text)
                save_session(self.session)
                return

        # 达到最大轮次
        msg = f"已达到最大轮次 ({self.max_turns})，任务终止"
        self.session.add_assistant_message(msg)
        yield AgentFinished(message=msg)
        save_session(self.session)

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
            decision = self.permission_guard.confirm()
            # 执行工具
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
            decision = self.permission_guard.deny()
            result_text = f"用户拒绝了 {pending.name} 操作"
            self.session.add_tool_result(pending.id, pending.name, result_text)
            yield PermissionDenied(tool_id=pending.id, name=pending.name)

        # 继续 Agent Loop（从当前上下文继续推理）
        async for event in self._continue_loop():
            yield event

    async def _continue_loop(self) -> AsyncIterator[AgentEvent]:
        """从当前上下文继续推理（内部方法）"""
        for turn in range(self.session.turn_count, self.max_turns):
            self.session.increment_turn()

            # 上下文压缩检查
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
                        yield AgentError(message=event["message"])
                        yield AgentFinished(message=f"因错误终止: {event['message']}")
                        save_session(self.session)
                        return
                    elif event["type"] == "finish":
                        break
            except Exception as e:
                yield AgentError(message=f"Agent Loop 异常: {str(e)}")
                yield AgentFinished(message=f"因异常终止: {str(e)}")
                save_session(self.session)
                return

            if tool_calls_buffer:
                self.session.add_assistant_message(
                    content="".join(text_buffer),
                    tool_calls=tool_calls_buffer,
                )
                for tc in tool_calls_buffer:
                    tool_name = tc["function"]["name"]
                    try:
                        arguments = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}

                    tool = self.tool_registry.get(tool_name)
                    if tool is None:
                        result_text = f"未知工具: {tool_name}"
                        self.session.add_tool_result(tc["id"], tool_name, result_text)
                        yield ToolCallResult(tool_id=tc["id"], name=tool_name, success=False, output=result_text)
                        continue

                    tool_call_obj = ToolCall(id=tc["id"], name=tool_name, arguments=arguments)
                    decision = self.permission_guard.check(tool_call_obj, tool.permission_level)

                    if decision == PermissionDecision.ASK:
                        yield PermissionRequest(
                            tool_id=tc["id"],
                            name=tool_name,
                            arguments=arguments,
                            summary=self._format_tool_summary(tool_name, arguments),
                        )
                        save_session(self.session)
                        return
                    elif decision == PermissionDecision.DENY:
                        result_text = f"用户拒绝了 {tool_name} 操作"
                        self.session.add_tool_result(tc["id"], tool_name, result_text)
                        yield PermissionDenied(tool_id=tc["id"], name=tool_name)
                        continue

                    yield ToolCallStart(tool_id=tc["id"], name=tool_name, arguments=arguments)
                    result = await self.tool_registry.execute(tool_name, arguments)
                    result_text = result.output if result.success else f"[错误] {result.error}"
                    self.session.add_tool_result(tc["id"], tool_name, result_text)
                    yield ToolCallResult(tool_id=tc["id"], name=tool_name, success=result.success, output=result_text)
                continue
            else:
                full_text = "".join(text_buffer)
                self.session.add_assistant_message(content=full_text)
                yield AgentFinished(message=full_text)
                save_session(self.session)
                return

        msg = f"已达到最大轮次 ({self.max_turns})，任务终止"
        self.session.add_assistant_message(msg)
        yield AgentFinished(message=msg)
        save_session(self.session)

    def _format_tool_summary(self, name: str, arguments: dict) -> str:
        """格式化工具调用摘要"""
        if name == "write_file":
            return f"写入文件: {arguments.get('path', '?')}"
        elif name == "edit_file":
            return f"编辑文件: {arguments.get('path', '?')}"
        elif name == "shell_exec":
            cmd = arguments.get("command", "?")
            return f"执行命令: {cmd[:80]}"
        return f"{name}: {json.dumps(arguments, ensure_ascii=False)[:100]}"
