"""统一模型错误提示，避免 Provider 与运行时叠加前缀。"""


def format_llm_error(error: Exception) -> str:
    message = str(error).strip()
    prefix = "LLM 请求失败: "
    while message.startswith(prefix):
        message = message[len(prefix):]
    if "overloaded" in message.lower() or getattr(error, "status_code", None) == 529:
        message = "模型服务暂时过载，请稍后重试或切换模型。"
    if message.startswith("LLM 请求超时"):
        return message
    return prefix + message
