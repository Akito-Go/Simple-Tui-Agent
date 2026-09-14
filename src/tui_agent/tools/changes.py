"""文本净变更统计；保留换行差异，不累计重复编辑。"""

from difflib import SequenceMatcher, unified_diff


def text_change(path: str, before: str, after: str) -> tuple[int, int, str]:
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    added = removed = 0
    for tag, i, j, k, l in SequenceMatcher(None, old, new).get_opcodes():
        if tag != "equal":
            removed += j - i
            added += l - k
    lines = []
    for line in unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}"):
        lines.append(line.rstrip("\r\n"))
        if not line.endswith("\n"):
            lines.append("\\ No newline at end of file")
    if before != after and before.splitlines() == after.splitlines():
        lines.append("提示：变化涉及换行格式或文件末尾换行。")
    return added, removed, "\n".join(lines)
