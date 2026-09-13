"""上下文压缩 — token 估算 + LLM 摘要"""

from __future__ import annotations

from typing import Any
from contextlib import aclosing

from .manager import SessionManager


def _estimate_text_tokens(text: str) -> int:
    """粗估字符串 token：CJK 约 1 token/字，其余约 4 字符/token。"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0x3040 <= code <= 0x30FF
            or 0xAC00 <= code <= 0xD7AF
        ):
            cjk += 1
        else:
            other += 1
    return cjk + (other + 3) // 4


def _estimate_value(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return _estimate_text_tokens(value)
    if isinstance(value, (int, float, bool)):
        return 1
    if isinstance(value, dict):
        return sum(_estimate_value(k) + _estimate_value(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return sum(_estimate_value(item) for item in value)
    return _estimate_text_tokens(str(value))


def estimate_tokens(messages: list[dict]) -> int:
    """估算消息列表 token 数（启发式，用于压缩阈值判断）"""
    total = 0
    for message in messages:
        total += 4  # 每条消息角色开销
        total += _estimate_value(message)
    return max(1, total)


async def compress_if_needed(
    session: SessionManager,
    llm_provider,
    threshold: int = 8000,
) -> bool:
    """
    如果消息 token 数超过阈值，压缩早期消息为摘要。

    压缩策略：
    - 优先保留 system prompt + 最近 2 轮完整对话；长任务改按工具批次压缩
    - 中间消息调用 LLM 生成摘要
    - 保证 tool 对不被截断

    Returns:
        True 如果执行了压缩
    """
    messages = session.build_api_messages()
    estimated = estimate_tokens(messages)
    session.token_usage.prompt_tokens = estimated
    if estimated <= threshold:
        return False

    # 找到最近 2 轮对话的起始位置
    keep_from = 1
    turns_to_keep = 0
    for i in range(len(messages) - 1, 0, -1):
        if messages[i]["role"] == "user":
            turns_to_keep += 1
            if turns_to_keep >= 2:
                keep_from = i
                break

    while keep_from < len(messages) and messages[keep_from]["role"] == "tool":
        keep_from += 1

    prefix = messages[:1]
    if keep_from <= 1 or estimate_tokens(messages[keep_from:]) >= threshold:
        # assistant 开始新批次时，之前的 tool_call/result 已完整闭合。
        # 保留最近两个批次和原始用户任务，允许单次长任务继续压缩。
        batches = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
        if len(batches) < 3:
            return False
        user_boundary = keep_from
        keep_from = batches[-2]
        preserved = {
            i
            for i in range(max(1, user_boundary), keep_from)
            if messages[i]["role"] == "user"
            and not messages[i].get("content", "").startswith("[上下文摘要]")
        }
        prefix = [messages[0], *(messages[i] for i in sorted(preserved))]
        middle = [
            m for i, m in enumerate(messages[1:keep_from], 1) if i not in preserved
        ]
    else:
        middle = messages[1:keep_from]
    try:
        summary = await _generate_summary(llm_provider, middle)
    except Exception as exc:
        raise RuntimeError(f"摘要失败，保留原始上下文: {exc}") from exc
    if not summary.strip():
        raise ValueError("摘要为空，保留原始上下文")

    new_messages = list(prefix)
    new_messages.append(
        {
            "role": "user",
            "content": f"[上下文摘要] 以下是之前对话的摘要，请基于这些信息继续对话:\n{summary}",
        }
    )
    new_messages.extend(messages[keep_from:])

    if estimate_tokens(new_messages) >= estimated:
        raise ValueError("摘要未减少上下文，保留原始历史")
    session.messages = new_messages
    session._context_dirty = True
    session.token_usage.prompt_tokens = estimate_tokens(new_messages)
    return True


async def _generate_summary(llm_provider, messages: list[dict]) -> str:
    """调用 LLM 生成对话摘要，保留技术细节"""
    summary_prompt = [
        {
            "role": "system",
            "content": (
                "你是一个对话摘要助手。请将以下对话历史压缩为简洁的摘要。"
                "必须保留以下技术细节：文件路径、错误信息、关键决策、代码片段要点。"
                "用中文回复，不超过 500 字。"
            ),
        },
        {
            "role": "user",
            "content": f"请摘要以下对话:\n{str(messages)}",
        },
    ]

    text_parts = []
    async with aclosing(llm_provider.chat(summary_prompt, stream=True)) as events:
        async for event in events:
            if event["type"] == "text_delta":
                text_parts.append(event["content"])
            elif event["type"] == "error":
                raise RuntimeError(event["message"])
            elif event["type"] == "finish":
                break

    return "".join(text_parts)
