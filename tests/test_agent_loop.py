"""Agent Loop 测试 — 文本回复、工具调用、多轮推理、max_turns 终止"""

import pytest

from tui_agent.agent.loop import AgentLoop
from tui_agent.agent.types import (
    TextDelta,
    ToolCallStart,
    ToolCallResult,
    PermissionRequest,
    PermissionDenied,
    AgentFinished,
    AgentError,
)
from tui_agent.tools.registry import ToolRegistry
from tui_agent.tools.list_dir import ListDirTool
from tui_agent.tools.write_file import WriteFileTool
from tui_agent.tools.shell_exec import ShellExecTool
from tui_agent.permissions.guard import PermissionGuard
from tui_agent.session.manager import SessionManager
from tests.conftest import MockLLMProvider, MockLLMResponse


def make_agent(mock_provider: MockLLMProvider) -> AgentLoop:
    """创建测试用 AgentLoop"""
    registry = ToolRegistry()
    registry.register(ListDirTool())
    registry.register(WriteFileTool())
    registry.register(ShellExecTool())

    return AgentLoop(
        llm_provider=mock_provider,
        tool_registry=registry,
        permission_guard=PermissionGuard(),
        session=SessionManager(),
        max_turns=5,
    )


class TestAgentLoopText:
    @pytest.mark.asyncio
    async def test_simple_text_response(self, mock_llm_provider):
        """测试纯文本回复"""
        mock_llm_provider.set_responses([
            MockLLMResponse(content="你好！有什么可以帮助你的？"),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("你好"):
            events.append(event)

        # 应该有 TextDelta 和 AgentFinished
        assert any(isinstance(e, TextDelta) for e in events)
        assert any(isinstance(e, AgentFinished) for e in events)

    @pytest.mark.asyncio
    async def test_text_delta_streaming(self, mock_llm_provider):
        """测试流式文本输出"""
        mock_llm_provider.set_responses([
            MockLLMResponse(content="Hello"),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("hi"):
            events.append(event)

        text_deltas = [e for e in events if isinstance(e, TextDelta)]
        full_text = "".join(e.content for e in text_deltas)
        assert full_text == "Hello"


class TestAgentLoopToolCall:
    @pytest.mark.asyncio
    async def test_read_tool_auto_execute(self, mock_llm_provider, temp_workspace, monkeypatch):
        """测试只读工具自动执行"""
        monkeypatch.chdir(temp_workspace)

        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}
            ]),
            MockLLMResponse(content="目录内容如上。"),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("列出文件"):
            events.append(event)

        # 应该有 ToolCallStart 和 ToolCallResult
        assert any(isinstance(e, ToolCallStart) for e in events)
        assert any(isinstance(e, ToolCallResult) for e in events)
        # 不应该有 PermissionRequest（只读自动执行）
        assert not any(isinstance(e, PermissionRequest) for e in events)

    @pytest.mark.asyncio
    async def test_write_tool_requires_permission(self, mock_llm_provider, temp_workspace, monkeypatch):
        """测试写入工具需要权限确认"""
        monkeypatch.chdir(temp_workspace)

        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {"id": "call_1", "function": {"name": "write_file", "arguments": '{"path": "test.py", "content": "print(1)"}'}}
            ]),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("创建 test.py"):
            events.append(event)

        # 应该有 PermissionRequest
        assert any(isinstance(e, PermissionRequest) for e in events)

    @pytest.mark.asyncio
    async def test_blocked_shell_skips_permission_prompt(self, mock_llm_provider):
        """黑名单 Shell 命令应直接失败，不弹出确认"""
        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "shell_exec",
                        "arguments": '{"command": "rm -rf /"}',
                    },
                }
            ]),
            MockLLMResponse(content="命令被拦截了。"),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("删根目录"):
            events.append(event)

        assert not any(isinstance(e, PermissionRequest) for e in events)
        tool_results = [e for e in events if isinstance(e, ToolCallResult)]
        assert tool_results
        assert not tool_results[0].success
        assert "安全策略" in tool_results[0].output


class TestAgentLoopMaxTurns:
    @pytest.mark.asyncio
    async def test_max_turns_termination(self, mock_llm_provider):
        """测试达到最大轮次自动终止"""
        # 每轮都返回工具调用，触发多轮循环
        responses = [
            MockLLMResponse(tool_calls=[
                {"id": f"call_{i}", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}
            ])
            for i in range(10)
        ]
        mock_llm_provider.set_responses(responses)

        agent = make_agent(mock_llm_provider)
        agent.max_turns = 3  # 设置较小的 max_turns

        events = []
        async for event in agent.run("keep listing"):
            events.append(event)

        # 应该有 AgentFinished 且消息包含 "最大轮次"
        finished_events = [e for e in events if isinstance(e, AgentFinished)]
        assert len(finished_events) > 0
        assert "最大轮次" in finished_events[-1].message


class TestAgentLoopError:
    @pytest.mark.asyncio
    async def test_unknown_tool(self, mock_llm_provider):
        """测试未知工具处理"""
        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {"id": "call_1", "function": {"name": "unknown_tool", "arguments": "{}"}}
            ]),
            MockLLMResponse(content="我无法使用那个工具。"),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("use unknown tool"):
            events.append(event)

        # 应该有 ToolCallResult 且 success=False
        tool_results = [e for e in events if isinstance(e, ToolCallResult)]
        assert any(not r.success for r in tool_results)


class TestMultiToolPermissionQueue:
    @pytest.mark.asyncio
    async def test_remaining_tools_run_after_confirm(self, mock_llm_provider, temp_workspace, monkeypatch):
        """多工具时确认后应继续执行同轮后续工具，避免缺 tool_result"""
        monkeypatch.chdir(temp_workspace)

        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {
                    "id": "call_w",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path": "a.py", "content": "x=1"}',
                    },
                },
                {
                    "id": "call_l",
                    "function": {"name": "list_dir", "arguments": '{"path": "./"}'},
                },
            ]),
            MockLLMResponse(content="完成"),
        ])

        agent = make_agent(mock_llm_provider)
        events = []
        async for event in agent.run("写文件并列出"):
            events.append(event)

        assert any(isinstance(e, PermissionRequest) for e in events)
        assert agent._queued_tool_calls  # list_dir 排队

        cont = []
        async for event in agent.continue_with_confirmation(True):
            cont.append(event)

        # 后续 list_dir 应已执行，且最终有完成
        assert any(isinstance(e, ToolCallResult) and e.name == "list_dir" for e in cont)
        assert any(isinstance(e, AgentFinished) for e in cont)
        # 会话中两个 tool_result 齐全
        tool_msgs = [m for m in agent.session.messages if m.get("role") == "tool"]
        assert {m["tool_call_id"] for m in tool_msgs} == {"call_w", "call_l"}
