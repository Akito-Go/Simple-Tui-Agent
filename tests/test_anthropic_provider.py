"""Anthropic 消息转换与 Provider 工厂测试"""

import pytest

from tui_agent.config.schema import LLMConfig
from tui_agent.llm.anthropic_compat import (
    AnthropicProvider,
    flatten_tools_to_anthropic,
    openai_messages_to_anthropic,
)
from tui_agent.llm.factory import (
    apply_provider_defaults,
    create_llm_provider,
    infer_provider_for_model,
    normalize_provider_name,
)
from tui_agent.llm.openai_compat import OpenAICompatProvider


class TestOpenAIToAnthropicMessages:
    def test_system_and_user(self):
        system, messages = openai_messages_to_anthropic(
            [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "hi"},
            ]
        )
        assert system == "You are helpful"
        assert messages == [{"role": "user", "content": "hi"}]

    def test_assistant_tool_calls_and_results(self):
        system, messages = openai_messages_to_anthropic(
            [
                {"role": "user", "content": "list"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "list_dir",
                                "arguments": '{"path": "."}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "list_dir",
                    "content": "src/",
                },
            ]
        )
        assert system is None
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"][0]["type"] == "tool_use"
        assert messages[1]["content"][0]["name"] == "list_dir"
        assert messages[1]["content"][0]["input"] == {"path": "."}
        assert messages[2]["role"] == "user"
        assert messages[2]["content"][0]["type"] == "tool_result"
        assert messages[2]["content"][0]["tool_use_id"] == "call_1"

    def test_merge_consecutive_tool_results(self):
        _, messages = openai_messages_to_anthropic(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "a", "function": {"name": "list_dir", "arguments": "{}"}},
                        {"id": "b", "function": {"name": "list_dir", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "tool_call_id": "a", "content": "1"},
                {"role": "tool", "tool_call_id": "b", "content": "2"},
            ]
        )
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert len(messages[1]["content"]) == 2


class TestAnthropicTools:
    def test_flatten_tools(self):
        tools = flatten_tools_to_anthropic(
            [
                {
                    "name": "list_dir",
                    "description": "List",
                    "parameters": {"type": "object", "properties": {}},
                }
            ]
        )
        assert tools[0]["name"] == "list_dir"
        assert tools[0]["input_schema"]["type"] == "object"


class TestFactory:
    def test_openai_provider(self):
        llm = LLMConfig(provider="openai_compat", model="gpt-4o-mini")
        provider = create_llm_provider(llm, "sk-test")
        assert isinstance(provider, OpenAICompatProvider)

    def test_anthropic_provider_rewrites_openai_base(self):
        llm = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-5",
            api_base="https://api.openai.com/v1",
        )
        provider = create_llm_provider(llm, "sk-ant-test")
        assert isinstance(provider, AnthropicProvider)
        assert "anthropic.com" in str(provider.client.base_url)

    def test_unknown_provider(self):
        llm = LLMConfig(provider="unknown")
        with pytest.raises(ValueError, match="未知 LLM provider"):
            create_llm_provider(llm, "sk-test")

    def test_infer_provider_for_model(self):
        assert infer_provider_for_model("claude-sonnet-4-5") == "anthropic"
        assert infer_provider_for_model("gpt-4o") == "openai_compat"
        assert infer_provider_for_model("deepseek-chat") is None

    def test_apply_provider_defaults(self):
        llm = LLMConfig(provider="openai_compat", api_base="https://api.openai.com/v1")
        apply_provider_defaults(llm, "anthropic")
        assert normalize_provider_name(llm.provider) == "anthropic"
        assert "anthropic.com" in llm.api_base
