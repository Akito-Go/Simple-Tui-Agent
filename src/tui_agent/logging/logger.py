"""日志系统 — loguru 配置 + 脱敏 filter"""

import re
import sys
from pathlib import Path

from loguru import logger


# 脱敏规则
SENSITIVE_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9_-]+"), "sk-***"),  # API Key
    (re.compile(r"Bearer\s+[^\s]+"), "Bearer ***"),  # Bearer Token
    (re.compile(r"TUI_AGENT_API_KEY[=:]\s*[^\s,}]+"), "TUI_AGENT_API_KEY=***"),
    (re.compile(r"OPENAI_API_KEY[=:]\s*[^\s,}]+"), "OPENAI_API_KEY=***"),
    (re.compile(r"ANTHROPIC_API_KEY[=:]\s*[^\s,}]+"), "ANTHROPIC_API_KEY=***"),
]


def sanitize_message(message: str) -> str:
    """对日志消息进行脱敏处理"""
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


# 会话 JSONL 中可能含用户/工具内容的字段
_LOG_RECORD_TEXT_FIELDS = frozenset({"content", "result", "arguments"})


def sanitize_log_record(record: dict) -> dict:
    """对单条会话 JSONL 记录中的文本字段脱敏（日志须提交仓库时使用）"""
    if record.get("type") == "context":

        def scrub(value):
            if isinstance(value, str):
                return sanitize_message(value)
            if isinstance(value, dict):
                return {k: scrub(v) for k, v in value.items()}
            if isinstance(value, list):
                return [scrub(v) for v in value]
            return value

        return scrub(record)
    return {
        key: sanitize_message(value)
        if key in _LOG_RECORD_TEXT_FIELDS and isinstance(value, str)
        else value
        for key, value in record.items()
    }


def sanitize_record(record: dict) -> bool:
    """loguru 脱敏 filter — 对每条日志记录进行脱敏"""
    record["message"] = sanitize_message(str(record["message"]))
    return True


def setup_logging(level: str = "INFO") -> None:
    """
    配置日志系统。

    - 控制台输出：彩色格式，INFO 级别
    - TUI 项目日志：JSONL 格式写入 .tui-agent/logs/
    - 两层日志区分：.tui-agent/logs/ (TUI 项目) vs .ai_history/logs/ (考核交付)

    注意：考核交付日志 (.ai_history/logs/) 由 Cursor 对话管理，本系统不修改。
    """
    # 移除默认 handler
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        level=level,
        colorize=True,
        filter=sanitize_record,
    )

    # TUI 项目日志 — JSONL 格式
    log_dir = Path.cwd() / ".tui-agent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "agent_{time:YYYY-MM-DD}.jsonl",
        format="{message}",
        level="DEBUG",
        serialize=True,  # JSON 格式
        rotation="10 MB",
        retention="7 days",
        filter=sanitize_record,
    )


def get_logger(name: str):
    """获取模块级 logger"""
    return logger.bind(name=name)
