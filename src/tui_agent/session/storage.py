"""JSONL 增量历史与压缩检查点；写入失败保留游标并回滚本次追加。"""

import json
import os
from pathlib import Path

from ..logging.logger import sanitize_log_record
from .manager import SessionManager


def get_log_dir() -> Path:
    log_dir = Path.cwd() / ".tui-agent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def save_session(session: SessionManager) -> Path:
    filepath = get_log_dir() / f"{session.session_id}.jsonl"
    since = session._saved_message_count
    records = session.to_log_records(since_index=since)
    metadata = (session.model, session.turn_count)
    if since > 1 and session._saved_metadata != metadata:
        from datetime import datetime, timezone

        records.append(
            {
                "type": "meta",
                "session_id": session.session_id,
                "model": session.model,
                "turn_count": session.turn_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    if session._context_dirty:
        records.append({"type": "context", "messages": session.build_messages()})
    if not records:
        return filepath

    # Serialize before touching disk. Append rollback avoids duplicates after a
    # partial write in this process; a crash-truncated final line is repaired below.
    payload = "".join(
        json.dumps(sanitize_log_record(r), ensure_ascii=False) + "\n" for r in records
    ).encode()
    with open(filepath, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        offset = handle.tell()
        if offset:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                handle.seek(0)
                data = handle.read()
                offset = data.rfind(b"\n") + 1
                handle.truncate(offset)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.truncate(offset)
            raise

    session._saved_message_count = len(session._transcript)
    session._saved_metadata = metadata
    session._context_dirty = False
    return filepath
