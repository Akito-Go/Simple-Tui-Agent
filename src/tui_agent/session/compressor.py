"""上下文压缩 — token 估算 + LLM 摘要"""

from .manager import SessionManager


def estimate_tokens(messages: list[dict]) -> int:
    """简单字符估算 token 数（len(str)/4）"""
    return len(str(messages)) // 4


async def compress_if_needed(
    session: SessionManager,
    llm_provider,
    threshold: int = 8000,
) -> bool:
    """
    如果消息 token 数超过阈值，压缩早期消息为摘要。

    压缩策略：
    - 保留 system prompt + 最近 2 轮完整对话
    - 中间消息调用 LLM 生成摘要
    - 保证 tool 对不被截断

    Returns:
        True 如果执行了压缩
    """
    messages = session.messages
    if estimate_tokens(messages) <= threshold:
        return False

    # 找到最近 2 轮对话的起始位置
    # 一轮 = user + assistant(+tool_calls) + tool_results...
    keep_from = len(messages)
    turns_to_keep = 0
    for i in range(len(messages) - 1, 0, -1):
        if messages[i]["role"] == "user":
            turns_to_keep += 1
            if turns_to_keep >= 2:
                keep_from = i
                break

    # 确保 keep_from 不截断 tool 对
    # 如果 keep_from 位置是 tool 消息，向前找到对应的 assistant(tool_calls)
    while keep_from < len(messages) and messages[keep_from]["role"] == "tool":
        keep_from += 1

    if keep_from <= 1:
        return False  # 没有可压缩的内容

    # 中间消息（system 之后，keep_from 之前）
    middle = messages[1:keep_from]

    # 调用 LLM 生成摘要
    summary = await _generate_summary(llm_provider, middle)

    # 重建消息列表：system + summary(as user) + 最近消息
    new_messages = [messages[0]]  # system prompt
    new_messages.append({
        "role": "user",
        "content": f"[上下文摘要] 以下是之前对话的摘要，请基于这些信息继续对话:\n{summary}",
    })
    new_messages.extend(messages[keep_from:])

    session.messages = new_messages
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
    async for event in llm_provider.chat(summary_prompt, stream=True):
        if event["type"] == "text_delta":
            text_parts.append(event["content"])
        elif event["type"] == "error":
            return f"摘要生成失败: {event['message']}"
        elif event["type"] == "finish":
            break

    return "".join(text_parts)
