"""LLM Provider 抽象基类"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """LLM Provider 抽象基类 — 定义 chat 接口"""

    async def aclose(self) -> None:
        """释放客户端资源；无外部资源的 Provider 可沿用空实现。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict]:
        """
        发起 LLM 请求，流式产出响应事件。

        Yields:
            dict: 事件类型包括:
                - {"type": "text_delta", "content": "..."}  流式文本片段
                - {"type": "tool_calls", "tool_calls": [...]}  工具调用
                - {"type": "error", "message": "..."}  错误信息
                - {"type": "finish", "content": "..."}  完成
        """
        ...
