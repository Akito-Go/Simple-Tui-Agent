"""会话管理 — 多轮对话上下文维护"""

import time
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    """Token 用量统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class SessionManager:
    """会话管理器 — 维护多轮对话上下文"""

    SYSTEM_PROMPT_TEMPLATE = """你是一个 TUI 终端编码 Agent，运行在用户的终端中。
你可以使用提供的工具来浏览目录、读取文件、搜索代码、写入/编辑文件和执行 Shell 命令。

运行环境：
- 当前实际调用的模型是：{model}
- 你是上述模型通过 API 驱动的编码助手，不是 Claude、ChatGPT、Gemini 等产品的官方客户端
- 当用户询问你是什么模型/谁开发的时，如实回答当前模型名称（{model}），不要声称自己是 Claude、GPT 或其他未在配置中使用的模型

何时使用工具：
- 寒暄、闲聊、致谢、身份/能力询问，或没有明确编码任务时：不要调用任何工具，直接用中文简短回复
- 只有用户提出具体开发、排查、阅读/修改代码、运行命令等任务时，才使用工具
- 不要为了「先了解项目」而在未被要求时主动扫描整个仓库

重要规则：
- 只读操作（list_dir、read_file、glob_search、grep_search）会自动执行，不会再弹确认框
- 写入操作（write_file、edit_file）和 Shell 命令（shell_exec）需要用户确认
- 在修改文件前，先读取文件了解当前内容
- 执行 Shell 命令前，确保命令是安全的
- 如果用户拒绝了你的操作，调整策略而不是重复尝试
- 用中文回复用户

输出格式要求（仅在有具体任务并需要工具时）：
- 每次调用工具前，先用一句话简短说明你要做什么
- 每次工具执行完毕后，用一句话总结结果
- 不要在调用工具前输出大段分析文字；有任务时先行动再解释
- 工具调用和文字说明要交替进行，保持对话节奏感"""

    @classmethod
    def build_system_prompt(cls, model: str) -> str:
        return cls.SYSTEM_PROMPT_TEMPLATE.format(model=model)

    def __init__(self, session_id: str | None = None, model: str = "unknown"):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.model = model
        self.messages: list[dict] = []
        self.turn_count: int = 0
        self.token_usage = TokenUsage()
        self.created_at = time.time()
        self._saved_message_count: int = 1  # system 不计入，从 1 开始

        self.messages.append({"role": "system", "content": self.build_system_prompt(model)})

    def set_model(self, model: str) -> None:
        """更新当前模型，并同步刷新系统提示"""
        self.model = model
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = self.build_system_prompt(model)
        else:
            self.messages.insert(0, {"role": "system", "content": self.build_system_prompt(model)})

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str, tool_calls: list[dict] | None = None) -> None:
        """添加助手回复"""
        msg: dict = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": tc["function"],
                }
                for tc in tool_calls
            ]
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> None:
        """添加工具执行结果"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        })

    def build_messages(self) -> list[dict]:
        """构建完整的消息列表（含系统提示）"""
        return list(self.messages)

    def increment_turn(self) -> None:
        """增加轮次计数"""
        self.turn_count += 1

    def clear(self) -> None:
        """清空会话（保留系统提示）"""
        self.messages = [self.messages[0]]  # 只保留系统提示
        self.turn_count = 0
        self.token_usage = TokenUsage()
        self._saved_message_count = 1

    def to_log_records(self, since_index: int = 1) -> list[dict]:
        """将会话历史转为日志记录列表（用于 JSONL 持久化），仅导出 index >= since_index 的消息"""
        import datetime
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        records = []
        # 首次写入时添加 meta 记录
        if since_index <= 1:
            records.append({
                "type": "meta",
                "session_id": self.session_id,
                "model": self.model,
                "turn_count": self.turn_count,
                "timestamp": timestamp,
            })

        for i, msg in enumerate(self.messages):
            if i < since_index:
                continue
            role = msg["role"]
            if role == "system":
                continue
            elif role == "user":
                records.append({"type": "user", "content": msg["content"], "timestamp": timestamp})
            elif role == "assistant":
                if msg.get("content"):
                    records.append({"type": "assistant", "content": msg["content"], "timestamp": timestamp})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        records.append({
                            "type": "tool_call",
                            "tool_call_id": tc.get("id", ""),
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                            "timestamp": timestamp,
                        })
            elif role == "tool":
                records.append({
                    "type": "tool_result",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "name": msg.get("name", ""),
                    "result": msg["content"],
                    "timestamp": timestamp,
                })

        return records
