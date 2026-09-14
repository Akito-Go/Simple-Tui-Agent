"""Anthropic Messages API 实现 — Session 仍存 OpenAI 格式，边界做转换"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
import json
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from .provider import LLMProvider
from .retry import with_retry
from .errors import format_llm_error

ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com"


def openai_messages_to_anthropic(
    messages: list[dict],
) -> tuple[str | None, list[dict]]:
    """将 OpenAI Chat messages 转为 Anthropic Messages API 格式。"""
    system_parts: list[str] = []
    out: list[dict] = []

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            content = msg.get("content") or ""
            if content:
                system_parts.append(str(content))
            continue

        if role == "user":
            out.append({"role": "user", "content": msg.get("content") or ""})
            continue

        if role == "assistant":
            blocks: list[dict] = []
            text = msg.get("content") or ""
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in msg.get("tool_calls") or []:
                raw_args = tc.get("function", {}).get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        parsed = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        parsed = {}
                else:
                    parsed = raw_args if isinstance(raw_args, dict) else {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id") or "",
                        "name": tc.get("function", {}).get("name") or "",
                        "input": parsed,
                    }
                )
            if not blocks:
                blocks = [{"type": "text", "text": ""}]
            out.append({"role": "assistant", "content": blocks})
            continue

        if role == "tool":
            tool_result = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id") or "",
                "content": msg.get("content") or "",
            }
            if (
                out
                and out[-1]["role"] == "user"
                and isinstance(out[-1]["content"], list)
            ):
                out[-1]["content"].append(tool_result)
            else:
                out.append({"role": "user", "content": [tool_result]})

    system = "\n\n".join(system_parts) if system_parts else None
    return system, out


def flatten_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """内部扁平工具 schema → Anthropic tools。"""
    return [
        {
            "name": t["name"],
            "description": t.get("description") or "",
            "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


class AnthropicProvider(LLMProvider):
    """通过 anthropic SDK 接入 Messages API（含 tool use / 流式）"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = ANTHROPIC_DEFAULT_BASE,
        timeout: int = 120,
        max_retries: int = 3,
        max_tokens: int = 8192,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url or ANTHROPIC_DEFAULT_BASE,
            timeout=timeout,
            max_retries=0,
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict]:
        try:
            async with aclosing(self._do_chat(messages, tools, stream)) as events:
                async for event in events:
                    yield event
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            yield {"type": "error", "message": f"LLM 请求超时 ({self.timeout}s)"}
        except Exception as e:
            yield {"type": "error", "message": format_llm_error(e)}

    async def _do_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict]:
        system, anthropic_messages = openai_messages_to_anthropic(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = flatten_tools_to_anthropic(tools)

        if stream:
            async with aclosing(self._handle_stream(kwargs)) as events:
                async for event in events:
                    yield event
        else:
            response = await with_retry(
                lambda: self.client.messages.create(**kwargs),
                max_retries=self.max_retries,
            )
            for event in self._handle_non_stream(response):
                yield event

    async def _handle_stream(self, kwargs: dict[str, Any]) -> AsyncIterator[dict]:
        """处理 Anthropic 流式事件，产出统一契约。"""

        async def _open_stream():
            return await self.client.messages.create(**kwargs)

        response = await with_retry(_open_stream, max_retries=self.max_retries)

        content_parts: list[str] = []
        tool_calls: list[dict] = []
        current_tool: dict | None = None
        input_json_parts: list[str] = []

        try:
            async for event in response:
                etype = getattr(event, "type", None)

                if etype == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", None) == "tool_use":
                        current_tool = {
                            "id": block.id,
                            "function": {"name": block.name, "arguments": ""},
                        }
                        input_json_parts = []

                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", None)
                    if dtype == "text_delta":
                        text = delta.text or ""
                        content_parts.append(text)
                        yield {"type": "text_delta", "content": text}
                    elif dtype == "input_json_delta" and current_tool is not None:
                        input_json_parts.append(delta.partial_json or "")

                elif etype == "content_block_stop":
                    if current_tool is not None:
                        current_tool["function"]["arguments"] = (
                            "".join(input_json_parts) or "{}"
                        )
                        tool_calls.append(current_tool)
                        current_tool = None
                        input_json_parts = []

                # 自然读完 SSE 响应，避免在 message_stop 处悬挂底层迭代器。

        finally:
            await response.close()

        if tool_calls:
            yield {"type": "tool_calls", "tool_calls": tool_calls}
        yield {"type": "finish", "content": "".join(content_parts)}

    def _handle_non_stream(self, response) -> list[dict]:
        events: list[dict] = []
        text_parts: list[str] = []
        tool_calls: list[dict] = []

        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text or "")
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(
                                block.input or {}, ensure_ascii=False
                            ),
                        },
                    }
                )

        text = "".join(text_parts)
        if text:
            events.append({"type": "text_delta", "content": text})
        if tool_calls:
            events.append({"type": "tool_calls", "tool_calls": tool_calls})
        events.append({"type": "finish", "content": text})
        return events
