"""会话持久化 — JSONL 格式写入 .tui-agent/logs/"""

import json
from pathlib import Path

from ..logging.logger import sanitize_log_record
from .manager import SessionManager


def get_log_dir() -> Path:
    """获取 TUI 项目日志目录"""
    log_dir = Path.cwd() / ".tui-agent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def save_session(session: SessionManager) -> Path:
    """
    将会话历史以 JSONL 格式增量持久化。
    首次写入用 'w'，后续用 'a'，避免重复写入已保存的消息。

    Returns:
        写入的文件路径
    """
    log_dir = get_log_dir()
    filepath = log_dir / f"{session.session_id}.jsonl"

    since = session._saved_message_count
    records = session.to_log_records(since_index=since)

    if not records:
        return filepath

    mode = "w" if since <= 1 else "a"
    with open(filepath, mode, encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(sanitize_log_record(record), ensure_ascii=False) + "\n")

    session._saved_message_count = len(session.messages)

    return filepath
