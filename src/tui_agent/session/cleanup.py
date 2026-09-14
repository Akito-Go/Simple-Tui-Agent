"""会话历史删除：预览绑定内容，确认时重新检查，保护当前会话。"""

from dataclasses import dataclass
import hashlib
import json
import re

from .checkpoint import safe_path
from ..tools.workspace import get_workspace_root


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class CleanupPlan:
    session_ids: tuple[str, ...]
    files: tuple[tuple[str, str], ...]
    workspace: str

    def delete(self, current_session_id: str | None = None) -> int:
        root = get_workspace_root().resolve()
        if str(root) != self.workspace or current_session_id in self.session_ids:
            raise ValueError("工作区或当前会话已变化，请重新预览")
        # 重新生成预览，同时检测关联检查点的新增、删除与内容变化。
        latest = prepare_cleanup(self.session_ids, current_session_id)
        if latest.files != self.files:
            raise ValueError("历史在预览后发生变化，请重新预览")
        deleted = 0
        for relative, digest in self.files:
            path = safe_path(root, relative)
            if fingerprint(path) != digest:
                raise ValueError(f"文件在删除期间变化，已删除 {deleted} 项，请重新预览")
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                raise OSError(f"已删除 {deleted} 项，剩余删除失败：{exc}") from exc
        return deleted


def prepare_cleanup(session_ids, current_session_id=None) -> CleanupPlan:
    root = get_workspace_root().resolve()
    ids = tuple(sorted(set(session_ids)))
    if not ids or current_session_id in ids:
        raise ValueError("不能删除当前会话，或没有可清理的历史")
    files = []
    for session_id in ids:
        if not re.fullmatch(r"session_[A-Za-z0-9_-]+", session_id):
            raise ValueError("会话 ID 无效")
        relative = f".tui-agent/logs/{session_id}.jsonl"
        files.append((relative, fingerprint(safe_path(root, relative))))
    directory = safe_path(root, ".tui-agent/checkpoints")
    for candidate in sorted(directory.glob('*.json')):
        path = safe_path(root, str(candidate.relative_to(root)))
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('session_id') in ids:
            files.append((str(path.relative_to(root)), fingerprint(path)))
    return CleanupPlan(ids, tuple(sorted(files)), str(root))
