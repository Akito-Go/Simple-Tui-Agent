"""会话加载 — 从 JSONL 恢复历史会话"""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .manager import SessionManager
from .storage import get_log_dir


def _format_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def _preview_text(text: str, max_len: int = 40) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


def list_sessions() -> list[dict]:
    """扫描 .tui-agent/logs/ 返回可恢复的会话列表（仅 session_*.jsonl）"""
    log_dir = get_log_dir()
    sessions = []
    for filepath in sorted(
        log_dir.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        try:
            meta: dict = {}
            msg_count = 0
            last_user = ""
            with open(filepath, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get("type") == "meta":
                        meta = record
                    elif record.get("type") == "user":
                        last_user = record.get("content", "")
                        msg_count += 1
                    elif record.get("type") in {
                        "assistant",
                        "tool_call",
                        "tool_result",
                    }:
                        msg_count += 1
            mtime = filepath.stat().st_mtime
            sessions.append(
                {
                    "session_id": filepath.stem,
                    "filepath": str(filepath),
                    "model": meta.get("model", "unknown"),
                    "turn_count": meta.get("turn_count", 0),
                    "msg_count": msg_count,
                    "last_active": _format_mtime(mtime),
                    "preview": _preview_text(last_user),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def _assign_tool_call_id(record: dict, index: int) -> str:
    tool_call_id = (record.get("tool_call_id") or "").strip()
    if tool_call_id:
        return tool_call_id
    return f"call_{index}"


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """移除孤立 tool 消息，补全缺失的 tool_call_id，保证符合 OpenAI 消息格式"""
    if not messages:
        return messages

    sanitized: list[dict] = []
    if messages[0].get("role") == "system":
        sanitized.append(messages[0])

    index = 1 if messages and messages[0].get("role") == "system" else 0
    call_counter = 0

    while index < len(messages):
        msg = messages[index]

        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_calls = []
            valid_ids: list[str] = []
            for tc in msg["tool_calls"]:
                call_counter += 1
                tool_call_id = (tc.get("id") or "").strip() or f"call_{call_counter}"
                valid_ids.append(tool_call_id)
                tool_calls.append(
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": tc["function"],
                    }
                )
            index += 1

            tool_msgs = []
            while index < len(messages) and messages[index].get("role") == "tool":
                tool_msg = messages[index]
                tool_call_id = (tool_msg.get("tool_call_id") or "").strip()
                if tool_call_id in valid_ids:
                    tool_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_msg.get("name", ""),
                            "content": tool_msg.get("content", ""),
                        }
                    )
                index += 1

            responded_ids = {t["tool_call_id"] for t in tool_msgs}
            matched_calls = [tc for tc in tool_calls if tc["id"] in responded_ids]

            if matched_calls and tool_msgs:
                sanitized.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": matched_calls,
                    }
                )
                sanitized.extend(tool_msgs)
            elif msg.get("content"):
                sanitized.append(
                    {
                        "role": "assistant",
                        "content": msg["content"],
                    }
                )
            continue

        if msg.get("role") == "tool":
            # 孤立的 tool 消息（旧日志重复写入导致），直接跳过
            index += 1
            continue

        sanitized.append(msg)
        index += 1

    return sanitized


def _merge_assistant_content(prev: str, nxt: str) -> str:
    if not prev:
        return nxt
    if not nxt:
        return prev
    return f"{prev.rstrip()}\n\n{nxt.lstrip()}"


def _normalize_message_sequence(messages: list[dict]) -> list[dict]:
    """合并连续 assistant 消息，修复 JSONL 交错记录导致的 API 非法序列"""
    if not messages:
        return messages

    normalized: list[dict] = []
    start = 1 if messages and messages[0].get("role") == "system" else 0
    if start:
        normalized.append(messages[0])

    index = start
    while index < len(messages):
        msg = messages[index]
        role = msg.get("role")

        if role != "assistant":
            normalized.append(msg)
            index += 1
            continue

        content = msg.get("content") or ""
        tool_calls = list(msg.get("tool_calls") or [])
        index += 1

        while index < len(messages) and messages[index].get("role") == "assistant":
            nxt = messages[index]
            nxt_content = nxt.get("content") or ""
            nxt_tool_calls = list(nxt.get("tool_calls") or [])
            if nxt_tool_calls:
                if tool_calls:
                    content = _merge_assistant_content(content, nxt_content)
                    tool_calls.extend(nxt_tool_calls)
                else:
                    content = _merge_assistant_content(content, nxt_content)
                    tool_calls = nxt_tool_calls
            else:
                content = _merge_assistant_content(content, nxt_content)
            index += 1

        merged: dict = {"role": "assistant", "content": content}
        if tool_calls:
            merged["tool_calls"] = tool_calls
        normalized.append(merged)

        while index < len(messages) and messages[index].get("role") == "tool":
            normalized.append(messages[index])
            index += 1

    return normalized


def load_session(filepath: str, model: str = "unknown") -> SessionManager | None:
    """
    从 JSONL 文件还原 SessionManager。

    JSONL 顺序（由 to_log_records 生成，兼容旧日志 tool_call 在前）：
      assistant(可选文本) → tool_call* → tool_result*
    旧格式：
      tool_call* → assistant(可选文本) → tool_result*
    """
    path = Path(filepath)
    if not path.exists():
        return None

    session_id = path.stem
    session = SessionManager(session_id=session_id, model=model)
    session.messages = []
    session._saved_message_count = 0

    pending_tool_calls: list[dict] = []
    pending_assistant_content: str = ""
    expected_tool_ids: list[str] = []
    call_counter = 0
    restored_model = model
    restored_turn_count = 0

    def flush_tool_calls(content: str = "") -> None:
        nonlocal \
            pending_tool_calls, \
            call_counter, \
            expected_tool_ids, \
            pending_assistant_content
        if not pending_tool_calls:
            return
        merged_content = _merge_assistant_content(pending_assistant_content, content)
        pending_assistant_content = ""
        normalized_calls = []
        for tc in pending_tool_calls:
            call_counter += 1
            tool_call_id = (tc.get("id") or "").strip() or f"call_{call_counter}"
            normalized_calls.append(
                {
                    "id": tool_call_id,
                    "function": tc["function"],
                }
            )
            expected_tool_ids.append(tool_call_id)
        session.add_assistant_message(merged_content, normalized_calls)
        pending_tool_calls = []

    def flush_pending_assistant_content() -> None:
        nonlocal pending_assistant_content
        if pending_assistant_content:
            session.add_assistant_message(pending_assistant_content)
            pending_assistant_content = ""

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type", "")

            if rtype == "context":
                flush_tool_calls()
                flush_pending_assistant_content()
                snapshot = record.get("messages")
                if isinstance(snapshot, list) and all(
                    isinstance(m, dict) and "role" in m for m in snapshot
                ):
                    session.messages = deepcopy(snapshot)
                expected_tool_ids = []
                continue

            if rtype == "meta":
                restored_model = record.get("model", model)
                restored_turn_count = record.get("turn_count", 0)
                continue

            if rtype == "user":
                flush_tool_calls()
                flush_pending_assistant_content()
                expected_tool_ids = []
                session.add_user_message(record.get("content", ""))

            elif rtype == "tool_call":
                call_counter += 1
                pending_tool_calls.append(
                    {
                        "id": _assign_tool_call_id(record, call_counter),
                        "function": {
                            "name": record.get("name", ""),
                            "arguments": record.get("arguments", "{}"),
                        },
                    }
                )

            elif rtype == "assistant":
                content = record.get("content", "")
                if pending_tool_calls:
                    flush_tool_calls(content)
                elif content:
                    pending_assistant_content = _merge_assistant_content(
                        pending_assistant_content, content
                    )

            elif rtype == "tool_result":
                if pending_tool_calls:
                    flush_tool_calls()
                tool_call_id = (record.get("tool_call_id") or "").strip()
                if not tool_call_id and expected_tool_ids:
                    tool_call_id = expected_tool_ids.pop(0)
                elif not tool_call_id:
                    call_counter += 1
                    tool_call_id = f"call_{call_counter}"
                session.add_tool_result(
                    tool_call_id,
                    record.get("name", ""),
                    record.get("result", ""),
                )

    flush_tool_calls()
    flush_pending_assistant_content()

    session.model = restored_model
    session.turn_count = restored_turn_count
    session.messages = _sanitize_messages(session.messages)
    session.messages = _normalize_message_sequence(session.messages)

    if not session.messages or session.messages[0].get("role") != "system":
        session.messages.insert(
            0,
            {
                "role": "system",
                "content": SessionManager.build_system_prompt(model),
            },
        )
    else:
        session.messages[0]["content"] = SessionManager.build_system_prompt(model)

    # 已完整加载历史，后续 save 应追加而非覆盖
    session._saved_message_count = len(session._transcript)
    session._saved_metadata = (session.model, session.turn_count)
    return session
