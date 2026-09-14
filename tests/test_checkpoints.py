"""任务恢复与文件撤销的跨模块回归。"""

import json
import os

import pytest

from tests.conftest import MockLLMProvider, MockLLMResponse
from tui_agent.agent.loop import AgentLoop
from tui_agent.agent.types import PermissionRequest
from tui_agent.permissions.guard import PermissionGuard
from tui_agent.session.checkpoint import Checkpoint
from tui_agent.session.manager import SessionManager
from tui_agent.tools.builtin import create_default_registry
from tui_agent.tools.workspace import set_workspace_root


@pytest.fixture
def task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_workspace_root(tmp_path)
    provider = MockLLMProvider()
    loop = AgentLoop(
        provider, create_default_registry(), PermissionGuard(), SessionManager()
    )
    return loop, provider, tmp_path


def call(name, args, id="one"):
    return {"id": id, "function": {"name": name, "arguments": json.dumps(args)}}


async def collect(events):
    return [event async for event in events]


async def make_change(task):
    loop, provider, root = task
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[call("write_file", {"path": "new.txt", "content": "hello"})]
            ),
            MockLLMResponse(content="done"),
        ]
    )
    await collect(loop.run("create new file"))
    await collect(loop.continue_with_confirmation(True))
    return loop.checkpoint


async def test_task_checkpoint_waiting_completed_and_stop(task):
    loop, provider, root = task
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[call("write_file", {"path": "a", "content": "A"})]
            )
        ]
    )
    await collect(loop.run("goal"))
    cp = Checkpoint.load(loop.checkpoint.data["id"])
    assert cp.data["status"] == "waiting"
    assert cp.data["goal"] == "goal" and cp.data["files"] == {}
    assert not (root / "a").exists()
    loop.stop()
    assert Checkpoint.load(cp.data["id"]).data["status"] == "interrupted"
    if os.name != "nt":
        assert cp.path.stat().st_mode & 0o777 == 0o600


async def test_create_and_undo_removes_only_created_file(task):
    cp = await make_change(task)
    root = task[2]
    (root / "unrelated").write_text("keep")
    assert cp.data["status"] == "completed"
    assert cp.undo_preview() == ["new.txt"]
    cp.undo(cp.fingerprint())
    assert not (root / "new.txt").exists()
    assert (root / "unrelated").read_text() == "keep"
    with pytest.raises(ValueError, match="已经撤销"):
        cp.undo_preview()


async def test_multiple_edits_restore_exact_original_and_mode(task):
    loop, _, root = task
    p = root / "source.txt"
    p.write_bytes("原文\r\nsecond\r\n".encode())
    p.chmod(0o640)
    original_mode = p.stat().st_mode & 0o777
    cp = Checkpoint.create("edit twice")
    loop.tool_registry.file_state.checkpoint = cp
    registry = loop.tool_registry
    assert (await registry.execute("read_file", {"path": str(p)})).success
    assert (
        await registry.execute(
            "edit_file", {"path": str(p), "old_string": "原文", "new_string": "新版"}
        )
    ).success
    assert (
        await registry.execute(
            "edit_file", {"path": str(p), "old_string": "second", "new_string": "third"}
        )
    ).success
    loaded = Checkpoint.load(cp.data["id"])
    loaded.undo(loaded.fingerprint())
    assert p.read_bytes() == "原文\r\nsecond\r\n".encode()
    assert p.stat().st_mode & 0o777 == original_mode


async def test_external_change_blocks_entire_undo(task):
    loop, _, root = task
    cp = await make_change(task)
    state = loop.tool_registry.file_state
    assert (
        await loop.tool_registry.execute(
            "write_file", {"path": "second", "content": "two"}
        )
    ).success
    assert state.checkpoint is cp
    (root / "second").write_text("user change")
    with pytest.raises(ValueError, match="冲突"):
        cp.undo(cp.fingerprint())
    assert (root / "new.txt").read_text() == "hello"
    assert (root / "second").read_text() == "user change"


async def test_undo_rechecks_changes_after_preview(task):
    cp = await make_change(task)
    signature = cp.fingerprint()
    assert cp.undo_preview()
    (task[2] / "new.txt").write_text("edited after preview")
    with pytest.raises(ValueError, match="冲突"):
        cp.undo(signature)
    cp.save()
    with pytest.raises(ValueError, match="预览后"):
        cp.undo(signature)


@pytest.mark.parametrize("written", [False, True])
def test_write_ahead_snapshot_survives_interrupted_write(task, written):
    root = task[2]
    p = root / "a"
    p.write_text("before")
    cp = Checkpoint.create("interrupted write")
    cp.prepare_write(p, "after")
    if written:
        p.write_text("after")
    loaded = Checkpoint.load(cp.data["id"])
    assert loaded.undo_preview() == (["a"] if written else [])
    loaded.undo(loaded.fingerprint())
    assert p.read_text() == "before"


def test_partial_undo_can_retry_after_io_failure(task, monkeypatch):
    from tui_agent.session import checkpoint as module

    root = task[2]
    cp = Checkpoint.create("two files")
    for name in ["a", "b"]:
        p = root / name
        p.write_text("before")
        cp.prepare_write(p, "after")
        p.write_text("after")
        cp.finish_write(p)
    original = module.atomic_write

    def fail_b(path, content):
        if path == root / "b":
            raise OSError("disk unavailable")
        original(path, content)

    monkeypatch.setattr(module, "atomic_write", fail_b)
    with pytest.raises(OSError):
        cp.undo(cp.fingerprint())
    assert (root / "a").read_text() == "before"
    assert (root / "b").read_text() == "after"
    monkeypatch.setattr(module, "atomic_write", original)
    loaded = Checkpoint.load(cp.data["id"])
    assert loaded.data["status"] == "undoing"
    loaded.undo(loaded.fingerprint())
    assert (root / "b").read_text() == "before"


async def test_resume_new_runtime_never_replays_pending_shell(task):
    loop, provider, root = task
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[call("shell_exec", {"command": "touch do-not-run"})]
            )
        ]
    )
    await collect(loop.run("review project"))
    checkpoint_id = loop.checkpoint.data["id"]
    loop.stop()
    fresh = AgentLoop(
        provider, create_default_registry(), PermissionGuard(), SessionManager()
    )
    provider.set_responses([MockLLMResponse(content="remaining work assessed")])
    events = await collect(fresh.resume(checkpoint_id))
    assert events[-1].message == "remaining work assessed"
    assert not (root / "do-not-run").exists()
    assert fresh.session.session_id != loop.session.session_id
    assert "不得直接重放" in provider.last_messages[-1]["content"]
    assert any(m.get("role") == "tool" for m in provider.last_messages)
    assert fresh.checkpoint.data["source_checkpoint"] == checkpoint_id
    assert Checkpoint.load(checkpoint_id).data["status"] == "continued"


async def test_resume_rechecks_external_changes_and_resets_permission(task):
    loop, provider, root = task
    cp = await make_change(task)
    cp.data["status"] = "interrupted"
    cp.save()
    (root / "new.txt").write_text("user edit")
    loop.permission_guard.enable_session_allow_all()
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[call("write_file", {"path": "another", "content": "new"})]
            )
        ]
    )
    events = await collect(loop.resume(cp.data["id"]))
    assert any(isinstance(e, PermissionRequest) for e in events)
    assert "已变化" in provider.last_messages[-1]["content"]
    assert loop.tool_registry.file_state.entries == {}
    assert not (root / "another").exists()
    assert loop.checkpoint.data["files"] == {}


async def test_missing_snapshot_storage_prevents_file_mutation(task, monkeypatch):
    loop, _, root = task
    cp = Checkpoint.create("disk full")
    loop.tool_registry.file_state.checkpoint = cp

    def fail():
        raise OSError("disk full")

    monkeypatch.setattr(cp, "save", fail)
    result = await loop.tool_registry.execute(
        "write_file", {"path": "a", "content": "bad"}
    )
    assert not result.success
    assert not (root / "a").exists()


async def test_checkpoint_rejects_path_traversal_and_symlink(task):
    cp = await make_change(task)
    with pytest.raises(ValueError):
        Checkpoint.load("../../outside")
    cp.data["files"]["../outside"] = cp.data["files"].pop("new.txt")
    with pytest.raises(ValueError):
        cp.undo_preview()
    root = task[2]
    cp.data["files"]["new.txt"] = cp.data["files"].pop("../outside")
    (root / "new.txt").unlink()
    (root / "target").write_text("hello")
    try:
        (root / "new.txt").symlink_to(root / "target")
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="符号链接"):
        cp.undo_preview()


async def test_tui_undo_requires_preview_then_confirmation(task):
    from tui_agent.config.schema import AppConfig
    from tui_agent.tui.app import TuiAgentApp
    from tui_agent.tui.commands import Command
    from tui_agent.tui.screens import MainScreen
    from tui_agent.tui.widgets.chat import ChatWidget

    loop, _, root = task
    cp = await make_change(task)

    class App(TuiAgentApp):
        def on_mount(self):
            self.push_screen(MainScreen())

        def init_agent(self):
            self.config = AppConfig()
            self.agent_loop = loop
            self.session = loop.session

    app = App()
    async with app.run_test() as pilot:
        app._handle_command(Command.UNDO, "confirm")
        await pilot.pause()
        assert (root / "new.txt").exists()
        app._handle_command(Command.UNDO, cp.data["id"])
        await pilot.pause()
        assert app._pending_undo and (root / "new.txt").exists()
        app.action_stop_agent()
        assert app._pending_undo is None
        app._handle_command(Command.UNDO, cp.data["id"])
        app._handle_command(Command.UNDO, "confirm")
        await pilot.pause()
        assert not (root / "new.txt").exists()
        assert "已撤销" in " ".join(app.screen.query_one(ChatWidget).child_labels())
        assert "重新读取" in loop.session.messages[-1]["content"]


async def test_completed_and_undone_tasks_cannot_resume(task):
    cp = await make_change(task)
    loop = task[0]
    with pytest.raises(ValueError, match="不能恢复"):
        await collect(loop.resume(cp.data["id"]))
    cp.undo(cp.fingerprint())
    with pytest.raises(ValueError, match="不能恢复"):
        await collect(loop.resume(cp.data["id"]))


async def test_resume_undo_preserves_user_edits_during_interruption(task):
    loop, provider, root = task
    original = await make_change(task)
    original.data["status"] = "interrupted"
    original.save()
    (root / "new.txt").write_text("user edit")
    provider.set_responses([
        MockLLMResponse(tool_calls=[call("read_file", {"path": "new.txt"})]),
        MockLLMResponse(tool_calls=[call("edit_file", {"path": "new.txt", "old_string": "user edit", "new_string": "user edit plus agent"}, "edit")]),
        MockLLMResponse(content="done"),
    ])
    events = await collect(loop.resume(original.data["id"]))
    assert isinstance(events[-1], PermissionRequest)
    await collect(loop.continue_with_confirmation(True))
    assert (root / "new.txt").read_text() == "user edit plus agent"
    continued = Checkpoint.load(loop.checkpoint.data["id"])
    continued.undo(continued.fingerprint())
    assert (root / "new.txt").read_text() == "user edit"


async def test_cancel_stream_persists_interrupted_context(task):
    import asyncio
    loop, _, _ = task
    entered = asyncio.Event()
    class Provider(MockLLMProvider):
        async def chat(self, *args, **kwargs):
            yield {"type": "text_delta", "content": "partial progress"}
            entered.set()
            await asyncio.Event().wait()
    loop.llm_provider = Provider()
    running = asyncio.create_task(collect(loop.run("long task")))
    await asyncio.wait_for(entered.wait(), 2)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    cp = Checkpoint.load(loop.checkpoint.data["id"])
    assert cp.data["status"] == "interrupted"
    assert "partial progress" in str(cp.data["messages"])


async def test_tui_resume_updates_current_session(task):
    from tui_agent.config.schema import AppConfig
    from tui_agent.tui.app import TuiAgentApp
    from tui_agent.tui.commands import Command
    from tui_agent.tui.screens import MainScreen
    from tui_agent.tui.widgets.chat import ChatWidget
    loop, provider, _ = task
    cp = await make_change(task)
    cp.data["status"] = "interrupted"
    cp.save()
    previous_session = loop.session
    provider.set_responses([MockLLMResponse(content="resumed answer")])
    class App(TuiAgentApp):
        def on_mount(self):
            self.push_screen(MainScreen())
        def init_agent(self):
            self.config = AppConfig()
            self.agent_loop = loop
            self.session = loop.session
    app = App()
    async with app.run_test() as pilot:
        app._handle_command(Command.RESUME, "")
        await pilot.pause()
        assert cp.data["id"] in " ".join(app.screen.query_one(ChatWidget).child_labels())
        app._handle_command(Command.RESUME, cp.data["id"])
        await pilot.pause()
        assert not app._agent_running
        assert app.session is loop.session and app.session is not previous_session
        assert "resumed answer" in " ".join(app.screen.query_one(ChatWidget).child_labels())
