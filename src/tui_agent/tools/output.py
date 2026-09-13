"""工具输出预算：完整结果有界落盘，模型接收短预览。"""

from copy import deepcopy
from uuid import uuid4

from .workspace import get_workspace_root, resolve_in_workspace

MAX_RESULT_CHARS = 30_000
from .file_state import MAX_FILE_BYTES

MAX_STORED_BYTES = MAX_FILE_BYTES
MAX_MESSAGE_TOOL_CHARS = 100_000


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    notice = "\n…[输出已截断]…\n"
    if limit <= len(notice):
        return notice[:limit]
    keep = (limit - len(notice)) // 2
    return text[:keep] + notice + text[-(limit - len(notice) - keep) :]


def budget_result(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    path, err = resolve_in_workspace(
        str(get_workspace_root() / ".tui-agent" / "results" / f"{uuid4().hex}.txt")
    )
    try:
        if err or path is None:
            raise OSError(err)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = text.encode("utf-8")
        stored = text
        if len(encoded) > MAX_STORED_BYTES:
            notice = "\n…[超出存储上限，中间部分已截断]…\n"
            keep = (MAX_STORED_BYTES - len(notice.encode("utf-8"))) // 2
            stored = (
                encoded[:keep].decode("utf-8", errors="ignore")
                + notice
                + encoded[-keep:].decode("utf-8", errors="ignore")
            )
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(stored)
        label = (
            "完整输出"
            if len(encoded) <= MAX_STORED_BYTES
            else "有界输出（超出存储上限的部分已截断）"
        )
        return f"{label}已保存至 {path}；可使用 read_file 分段读取。\n" + truncate(
            text, 2000
        )
    except OSError:
        return truncate(text, MAX_RESULT_CHARS)


def apply_message_budget(messages: list[dict]) -> list[dict]:
    out = deepcopy(messages)
    remaining = MAX_MESSAGE_TOOL_CHARS
    # 优先保留最近的结果；保留 tool_result 结构以维持协议配对。
    for message in reversed(out):
        if message.get("role") == "tool":
            message["content"] = truncate(
                message.get("content", ""), min(MAX_RESULT_CHARS, remaining)
            )
            remaining -= len(message["content"])
    return out
