"""任务检查点与文件写入日志；恢复不重放工具，撤销先检查全部冲突。"""

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from ..tools.file_state import atomic_write, read_bytes
from ..tools.changes import text_change
from ..tools.workspace import get_workspace_root

RESUMABLE = {"running", "waiting", "interrupted", "failed", "limit"}
MAX_SNAPSHOT_BYTES = 20_000_000


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("检查点路径无效")
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"路径包含符号链接: {relative}")
    path.resolve().relative_to(root)
    return path


def snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"不是普通文件: {path}")
    data = read_bytes(path)
    return {
        "data": base64.b64encode(data).decode("ascii"),
        "mode": path.stat().st_mode & 0o777,
    }


class Checkpoint:
    def __init__(self, data: dict):
        self.data = data
        self.root = get_workspace_root().resolve()
        if data["workspace"] != str(self.root):
            raise ValueError("检查点不属于当前工作区")
        if not re.fullmatch(r"[a-f0-9]{32}", data["id"]):
            raise ValueError("检查点 ID 无效")

    @property
    def path(self) -> Path:
        return safe_path(self.root, f".tui-agent/checkpoints/{self.data['id']}.json")

    @classmethod
    def create(cls, goal: str):
        return cls(
            {
                "version": 1,
                "id": uuid4().hex,
                "workspace": str(get_workspace_root()),
                "goal": goal,
                "status": "running",
                "phase": "分析",
                "files": {},
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        )

    @classmethod
    def load(cls, checkpoint_id: str):
        if not re.fullmatch(r"[a-f0-9]{32}", checkpoint_id):
            raise ValueError("请使用列表中的完整检查点 ID")
        path = safe_path(
            get_workspace_root(), f".tui-agent/checkpoints/{checkpoint_id}.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or data.get("id") != checkpoint_id:
            raise ValueError("检查点格式不支持")
        return cls(data)

    @classmethod
    def recent(cls):
        directory = safe_path(get_workspace_root(), ".tui-agent/checkpoints")
        result = []
        for path in directory.glob("*.json"):
            try:
                result.append(cls.load(path.stem))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(result, key=lambda cp: cp.data["updated_at"], reverse=True)

    def save(self):
        self.data["updated_at"] = time.time()
        atomic_write(self.path, json.dumps(self.data, ensure_ascii=False))
        self.path.chmod(0o600)

    def update(self, session, state, status=None, phase=None):
        self.data.update(
            session_id=session.session_id,
            model=session.model,
            messages=session.build_messages(),
            turn_count=state.turn_count,
            session_turn_count=session.turn_count,
        )
        if status:
            self.data["status"] = status
        if phase:
            self.data["phase"] = phase
        self.save()

    def file_path(self, relative: str) -> Path:
        if not Path(relative).parts or Path(relative).parts[0] in {
            ".git",
            ".tui-agent",
        }:
            raise ValueError("任务快照不允许修改 Git 元数据或 STA 自身状态")
        return safe_path(self.root, relative)

    def prepare_write(self, path: Path, content: str):
        relative = str(path.relative_to(self.root))
        path = self.file_path(relative)
        before = snapshot(path)
        encoded = content.encode("utf-8")
        if len(encoded) > 2_000_000:
            raise ValueError("文件超过检查点单文件 2 MB 上限")
        entry = self.data["files"].get(relative)
        if entry is not None:
            expected = self._expected(entry, before)
            if before != expected:
                raise ValueError(
                    f"文件在本任务写入后被外部修改，不能继续覆盖: {relative}"
                )
        after = {
            "data": base64.b64encode(encoded).decode("ascii"),
            "mode": before["mode"] if before else None,
        }
        # 新文件权限以系统 umask 创建后的结果为准，预写日志只比较内容。
        record = {
            "before": entry["before"] if entry else before,
            "after": after,
            "previous": before,
            "pending": True,
        }
        old = deepcopy(self.data)
        self.data["files"][relative] = record
        size = sum(len(json.dumps(item)) for item in self.data["files"].values())
        if size > MAX_SNAPSHOT_BYTES or len(self.data["files"]) > 100:
            self.data = old
            raise ValueError("任务文件快照超过 20 MB 或 100 个文件上限")
        try:
            self.save()  # 写入前落盘；失败则阻止修改。
        except BaseException:
            self.data = old
            raise

    @staticmethod
    def _expected(entry, current):
        if entry.get("pending") and current == entry.get("previous"):
            return entry["previous"]
        expected = entry["after"]
        if expected and expected["mode"] is None and current:
            expected = {**expected, "mode": current["mode"]}
        return expected

    def finish_write(self, path: Path):
        entry = self.data["files"][str(path.relative_to(self.root))]
        entry["after"] = snapshot(path)
        entry["pending"] = False
        entry.pop("previous", None)
        self.save()

    def inspect_files(self) -> list[str]:
        report = []
        for relative, entry in self.data["files"].items():
            try:
                current = snapshot(self.file_path(relative))
                unchanged = current == self._expected(entry, current)
                report.append(
                    f"{relative}: {'与检查点一致' if unchanged else '已变化，需重新读取'}"
                )
            except (OSError, ValueError) as exc:
                report.append(f"{relative}: 无法核对（{exc}）")
        return report

    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def file_changes(self) -> list[dict]:
        """比较任务起点与记录结果；外部变化只标注，不归入任务统计。"""
        changes = []
        for relative, entry in self.data["files"].items():
            note = ""
            current = None
            readable = True
            try:
                current = snapshot(self.file_path(relative))
            except (OSError, ValueError) as exc:
                readable = False
                note = f"无法核对：{exc}"
            after = entry["after"]
            if entry.get("pending"):
                if readable:
                    after = self._expected(entry, current)
                else:
                    after = entry.get("previous")
                note = "写入结果待核实" + (f"；{note}" if note else "")
            if readable and current != self._expected(entry, current):
                note = "文件已被后续修改或删除；展示任务记录结果"
            before = entry["before"]
            if before == after:
                continue
            old = base64.b64decode(before["data"]).decode("utf-8") if before else ""
            new = base64.b64decode(after["data"]).decode("utf-8") if after else ""
            added, removed, diff = text_change(relative, old, new)
            kind = "新增" if before is None else "修改"
            if before and after and before["mode"] != after["mode"]:
                diff += f"\n权限：{before['mode']:03o} → {after['mode']:03o}"
            changes.append(dict(path=relative, kind=kind, added=added, removed=removed,
                                diff=diff or "空文件新增", note=note))
        return changes

    def change_report(self, *, diff: bool = False, path: str = "") -> str:
        from ..tools.output import truncate

        changes = self.file_changes()
        if path:
            relative = str(self.file_path(path).relative_to(self.root))
            changes = [item for item in changes if item["path"] == relative]
        if not changes:
            return "当前任务暂无匹配的文件净变更（仅统计文件工具，Shell 不在范围内）。"
        lines = [f"任务文件变更：{len(changes)} 个文件，+{sum(c['added'] for c in changes)} / -{sum(c['removed'] for c in changes)} 行"]
        for item in changes:
            lines.append(f"{item['kind']} {item['path']}  +{item['added']} / -{item['removed']}" + (f" · {item['note']}" if item['note'] else ""))
            if diff:
                lines.append(truncate(item["diff"], 12000))
        lines.append("以本任务起点和记录结果比较；不含 Shell 修改。/diff [路径] 查看差异，/files 查看列表。")
        return truncate("\n".join(lines), 48000)

    def undo_preview(self) -> list[str]:
        if self.data["status"] == "undone":
            raise ValueError("该任务已经撤销")
        changes = []
        for relative, entry in self.data["files"].items():
            current = snapshot(self.file_path(relative))
            if self.data["status"] == "undoing" and current == entry["before"]:
                continue  # 上次撤销已恢复此文件，允许重试剩余部分。
            if current != self._expected(entry, current):
                raise ValueError(f"撤销冲突，文件已被后续修改: {relative}")
            if current != entry["before"]:
                changes.append(relative)
        return changes

    def undo(self, fingerprint: str) -> list[str]:
        if self.fingerprint() != fingerprint:
            raise ValueError("检查点在预览后发生变化，请重新预览")
        changes = self.undo_preview()  # 全量检查通过后才开始写入。
        self.data["status"] = "undoing"
        self.save()
        for relative in changes:
            path = self.file_path(relative)
            entry = self.data["files"][relative]
            if snapshot(path) != self._expected(entry, snapshot(path)):
                raise ValueError(f"撤销期间发生冲突: {relative}")
            before = entry["before"]
            if before is None:
                path.unlink()
            else:
                atomic_write(path, base64.b64decode(before["data"]).decode("utf-8"))
                path.chmod(before["mode"])
        self.data["status"] = "undone"
        self.save()
        return changes
