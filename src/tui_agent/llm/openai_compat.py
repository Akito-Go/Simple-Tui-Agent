"""OpenAI 兼容协议实现"""

import asyncio
from contextlib import aclosing
from typing import AsyncIterator

from openai import AsyncOpenAI

from .provider import LLMProvider
from .retry import with_retry


class OpenAICompatProvider(LLMProvider):
    """通过 openai SDK 接入任意 OpenAI 兼容 API"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,  # 我们自己控制重试
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict]:
        """发起 LLM 请求，流式产出响应事件"""
        try:
            async with aclosing(self._do_chat(messages, tools, stream)) as events:
                async for event in events:
                    yield event
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            yield {"type": "error", "message": f"LLM 请求超时 ({self.timeout}s)"}
        except Exception as e:
            yield {"type": "error", "message": f"LLM 请求失败: {str(e)}"}

    async def _do_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict]:
        """实际执行 LLM 请求（含重试）"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = self._format_tools(tools)

        # 带重试的请求
        response = await with_retry(
            lambda: self.client.chat.completions.create(**kwargs),
            max_retries=self.max_retries,
        )

        if stream:
            try:
                async with aclosing(self._handle_stream(response)) as events:
                    async for event in events:
                        yield event
            finally:
                await response.close()
        else:
            for event in self._handle_non_stream(response):
                yield event

    async def _handle_stream(self, response) -> AsyncIterator[dict]:
        """处理流式响应"""
        tool_calls_buffer: list[dict] = []
        content_buffer: list[str] = []

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # 文本内容
            if delta.content:
                content_buffer.append(delta.content)
                yield {"type": "text_delta", "content": delta.content}

            # 工具调用 (增量)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    # 确保 buffer 有足够位置
                    while len(tool_calls_buffer) <= tc.index:
                        tool_calls_buffer.append(
                            {"id": "", "function": {"name": "", "arguments": ""}}
                        )

                    if tc.id:
                        tool_calls_buffer[tc.index]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_buffer[tc.index]["function"]["name"] = (
                                tc.function.name
                            )
                        if tc.function.arguments:
                            tool_calls_buffer[tc.index]["function"]["arguments"] += (
                                tc.function.arguments
                            )

            # 结束
            if chunk.choices[0].finish_reason:
                if tool_calls_buffer:
                    yield {"type": "tool_calls", "tool_calls": tool_calls_buffer}
                # 继续读取协议结束标记，让 SDK 自然结束底层迭代。

        yield {"type": "finish", "content": "".join(content_buffer)}

    def _handle_non_stream(self, response) -> list[dict]:
        """处理非流式响应"""
        events = []
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
            events.append({"type": "tool_calls", "tool_calls": tool_calls})

        if message.content:
            events.append({"type": "text_delta", "content": message.content})

        events.append({"type": "finish", "content": message.content or ""})
        return events

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        """将工具定义转为 OpenAI function calling 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]
