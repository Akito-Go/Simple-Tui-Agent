"""pytest fixtures — Mock LLM Provider 等共享测试资源"""

import pytest
from typing import AsyncIterator
from pathlib import Path


class MockLLMResponse:
    """模拟 LLM 响应"""

    def __init__(self, content: str = "", tool_calls: list[dict] | None = None, finish_reason: str = "stop"):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason


class MockLLMProvider:
    """Mock LLM Provider — 返回预设响应，不调用真实 API"""

    def __init__(self):
        self._responses: list[MockLLMResponse] = []
        self._call_count = 0
        self.last_messages: list[dict] = []
        self.last_tools: list[dict] = []

    def set_responses(self, responses: list[MockLLMResponse]) -> None:
        """设置预设响应序列"""
        self._responses = responses
        self._call_count = 0

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None, stream: bool = True
    ) -> AsyncIterator[dict]:
        """模拟 chat 调用，返回预设响应"""
        self.last_messages = messages
        self.last_tools = tools or []

        if self._call_count >= len(self._responses):
            # 默认返回结束
            yield {"type": "finish", "content": ""}
            return

        response = self._responses[self._call_count]
        self._call_count += 1

        if response.tool_calls:
            yield {
                "type": "tool_calls",
                "tool_calls": response.tool_calls,
            }
        elif response.content:
            if stream:
                # 模拟流式输出
                for char in response.content:
                    yield {"type": "text_delta", "content": char}
            else:
                yield {"type": "text", "content": response.content}

        yield {"type": "finish", "content": ""}


@pytest.fixture(autouse=True)
def _reset_workspace_root():
    """每个测试前后重置工作区，避免用例间污染"""
    from tui_agent.tools.workspace import reset_workspace_root

    reset_workspace_root()
    yield
    reset_workspace_root()


@pytest.fixture
def mock_llm_provider() -> MockLLMProvider:
    """返回 Mock LLM Provider 实例"""
    return MockLLMProvider()


@pytest.fixture
def temp_workspace(tmp_path):
    """临时工作空间 fixture"""
    from tui_agent.tools.workspace import set_workspace_root

    set_workspace_root(tmp_path)
    # 创建一些测试文件
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.py").write_text("VERSION = '1.0'\n")
    return tmp_path
