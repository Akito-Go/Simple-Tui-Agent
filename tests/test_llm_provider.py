"""LLM Provider 测试 — Mock Provider 场景"""

import pytest

from tests.conftest import MockLLMResponse


class TestMockLLMProvider:
    @pytest.mark.asyncio
    async def test_text_response(self, mock_llm_provider):
        """测试文本回复"""
        mock_llm_provider.set_responses([
            MockLLMResponse(content="Hello, world!"),
        ])

        events = []
        async for event in mock_llm_provider.chat(
            messages=[{"role": "user", "content": "hi"}],
        ):
            events.append(event)

        # 应该有 text_delta 事件和 finish 事件
        text_events = [e for e in events if e["type"] == "text_delta"]
        assert len(text_events) > 0
        assert "".join(e["content"] for e in text_events) == "Hello, world!"
        assert events[-1]["type"] == "finish"

    @pytest.mark.asyncio
    async def test_tool_call_response(self, mock_llm_provider):
        """测试工具调用响应"""
        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}
            ]),
        ])

        events = []
        async for event in mock_llm_provider.chat(
            messages=[{"role": "user", "content": "list files"}],
            tools=[{"name": "list_dir", "description": "List directory", "parameters": {}}],
        ):
            events.append(event)

        tool_events = [e for e in events if e["type"] == "tool_calls"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool_calls"][0]["function"]["name"] == "list_dir"

    @pytest.mark.asyncio
    async def test_multi_turn(self, mock_llm_provider):
        """测试多轮调用"""
        mock_llm_provider.set_responses([
            MockLLMResponse(tool_calls=[
                {"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}
            ]),
            MockLLMResponse(content="Found 3 files."),
        ])

        # 第一轮
        events_1 = []
        async for event in mock_llm_provider.chat(
            messages=[{"role": "user", "content": "list files"}],
        ):
            events_1.append(event)
        assert any(e["type"] == "tool_calls" for e in events_1)

        # 第二轮
        events_2 = []
        async for event in mock_llm_provider.chat(
            messages=[
                {"role": "user", "content": "list files"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}]},
                {"role": "tool", "content": "src/ tests/ pyproject.toml"},
            ],
        ):
            events_2.append(event)
        assert any(e["type"] == "text_delta" for e in events_2)

    @pytest.mark.asyncio
    async def test_messages_passed_correctly(self, mock_llm_provider):
        """测试消息正确传递"""
        mock_llm_provider.set_responses([
            MockLLMResponse(content="ok"),
        ])

        messages = [{"role": "user", "content": "test"}]
        tools = [{"name": "test_tool", "description": "test", "parameters": {}}]

        async for _ in mock_llm_provider.chat(messages=messages, tools=tools):
            pass

        assert mock_llm_provider.last_messages == messages
        assert mock_llm_provider.last_tools == tools
