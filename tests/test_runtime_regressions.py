"""运行时跨模块回归：确认、取消、持久化与工具边界。"""

import asyncio
from copy import deepcopy
import json
import os
import shlex
import sys
import time

import pytest

from tests.conftest import MockLLMProvider, MockLLMResponse
from tui_agent.agent.loop import AgentLoop
from tui_agent.agent.types import (
    AgentError,
    AgentFinished,
    PermissionRequest,
    ToolCallResult,
)
from tui_agent.permissions.guard import PermissionGuard
from tui_agent.session.compressor import compress_if_needed
from tui_agent.session.loader import load_session
from tui_agent.session.manager import SessionManager
from tui_agent.session.storage import save_session
from tui_agent.tools.builtin import create_default_registry
from tui_agent.tools.shell_exec import ShellExecTool
from tui_agent.tools.workspace import set_workspace_root


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_workspace_root(tmp_path)
    provider = MockLLMProvider()
    loop = AgentLoop(
        provider, create_default_registry(), PermissionGuard(), SessionManager()
    )
    return loop, provider, tmp_path


def call(name, args, call_id="call_1"):
    return {"id": call_id, "function": {"name": name, "arguments": json.dumps(args)}}


async def collect(events):
    return [event async for event in events]


async def wait_for_file(path):
    async with asyncio.timeout(3):
        while not path.exists():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_allow_session_executes_current_and_remaining_once(runtime):
    loop, provider, root = runtime
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[
                    call("write_file", {"path": "a", "content": "A"}),
                    call("write_file", {"path": "b", "content": "B"}, "call_2"),
                ]
            ),
            MockLLMResponse(content="done"),
        ]
    )
    events = await collect(loop.run("create files"))
    assert any(isinstance(e, PermissionRequest) for e in events)
    events = await collect(loop.continue_with_confirmation(True, allow_session=True))
    assert not any(isinstance(e, AgentError) for e in events)
    assert (root / "a").read_text() == "A"
    assert (root / "b").read_text() == "B"
    results = [m for m in loop.session.messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in results] == ["call_1", "call_2"]


@pytest.mark.asyncio
async def test_stop_waiting_then_new_request_has_complete_pairs(runtime):
    loop, provider, root = runtime
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[
                    call("write_file", {"path": "a", "content": "A"}),
                    call("write_file", {"path": "b", "content": "B"}, "call_2"),
                ]
            ),
            MockLLMResponse(content="next task"),
        ]
    )
    await collect(loop.run("create files"))
    loop.stop()
    assert not loop.state.queued
    assert loop.permission_guard.pending_tool_call is None
    await collect(loop.run("new task"))
    assert not (root / "a").exists() and not (root / "b").exists()
    messages = provider.last_messages
    declaration = next(i for i, m in enumerate(messages) if m.get("tool_calls"))
    assert [m["tool_call_id"] for m in messages[declaration + 1 : declaration + 3]] == [
        "call_1",
        "call_2",
    ]


@pytest.mark.asyncio
async def test_turn_limit_resets_only_for_new_query(runtime):
    loop, provider, _ = runtime
    loop.max_turns = 1
    provider.set_responses(
        [MockLLMResponse(content="one"), MockLLMResponse(content="two")]
    )
    await collect(loop.run("first"))
    events = await collect(loop.run("second"))
    assert next(e.message for e in events if isinstance(e, AgentFinished)) == "two"
    assert loop.state.turn_count == 1 and loop.session.turn_count == 2
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[call("write_file", {"path": "c", "content": "C"})]
            )
        ]
    )
    await collect(loop.run("third"))
    events = await collect(loop.continue_with_confirmation(True))
    assert "最大轮次" in events[-1].message
    assert provider._call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["[]", "null", "{bad", '{"command": 123}'])
async def test_bad_tool_arguments_return_error_without_confirmation(runtime, arguments):
    loop, provider, _ = runtime
    tc = call("shell_exec", {})
    tc["function"]["arguments"] = arguments
    provider.set_responses(
        [MockLLMResponse(tool_calls=[tc]), MockLLMResponse(content="recovered")]
    )
    events = await collect(loop.run("test"))
    assert not any(isinstance(e, PermissionRequest) for e in events)
    assert any(isinstance(e, ToolCallResult) and not e.success for e in events)
    assert events[-1].message == "recovered"


@pytest.mark.asyncio
async def test_compress_save_restore_and_continue(runtime):
    loop, provider, _ = runtime
    session = loop.session
    for i in range(12):
        session.add_user_message(f"history {i}")
        session.add_assistant_message("old response" * 20)
    filepath = save_session(session)
    provider.set_responses([MockLLMResponse(content="summary")])
    assert await compress_if_needed(session, provider, threshold=100)
    session.add_user_message("after compression")
    session.add_assistant_message("new response")
    save_session(session)
    restored = load_session(str(filepath))
    assert any("上下文摘要" in m.get("content", "") for m in restored.messages)
    assert any(m.get("content") == "after compression" for m in restored.messages)
    restored.add_user_message("after restore")
    save_session(restored)
    again = load_session(str(filepath))
    assert again.messages[-1]["content"] == "after restore"
    records = [json.loads(line) for line in filepath.read_text().splitlines()]
    assert sum(r.get("content") == "after compression" for r in records) == 1
    assert sum(r.get("content") == "after restore" for r in records) == 1
    assert any(r.get("content") == "history 0" for r in records)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "empty"])
async def test_failed_summary_never_replaces_context(runtime, failure):
    loop, _, _ = runtime
    for i in range(5):
        loop.session.add_user_message(f"important {i}" * 50)
        loop.session.add_assistant_message("reply")
    before = deepcopy(loop.session.messages)

    class Failing:
        async def chat(self, *args, **kwargs):
            yield (
                {"type": "error", "message": "network down"}
                if failure == "error"
                else {"type": "finish"}
            )

    with pytest.raises((RuntimeError, ValueError)):
        await compress_if_needed(loop.session, Failing(), 100)
    assert loop.session.messages == before


def test_save_failure_rolls_back_and_retry_has_no_duplicates(runtime, monkeypatch):
    loop, _, _ = runtime
    session = loop.session
    session.add_user_message("first")
    path = save_session(session)
    original = path.read_bytes()
    cursor = session._saved_message_count
    session.add_user_message("second")
    with monkeypatch.context() as patch:
        patch.setattr(
            "tui_agent.session.storage.os.fsync",
            lambda _: (_ for _ in ()).throw(OSError("disk full")),
        )
        with pytest.raises(OSError):
            save_session(session)
    assert path.read_bytes() == original
    assert session._saved_message_count == cursor
    save_session(session)
    assert path.read_text().count('"content": "second"') == 1


def test_clear_preserves_old_log_and_metadata_updates(runtime):
    loop, _, _ = runtime
    session = loop.session
    session.add_user_message("old history")
    path = save_session(session)
    session.increment_turn()
    session.set_model("new-model")
    save_session(session)
    restored = load_session(str(path))
    assert restored.model == "new-model" and restored.turn_count == 1
    session.clear()
    session.add_user_message("new history")
    next_path = save_session(session)
    assert path != next_path and "old history" in path.read_text()


@pytest.mark.asyncio
async def test_sensitive_symlink_not_returned_by_search(runtime):
    loop, _, root = runtime
    (root / ".env").write_text("FAKE_TEST_SECRET=private")
    (root / "ordinary.txt").symlink_to(root / ".env")
    for name, args in [
        ("grep_search", {"pattern": "FAKE_TEST_SECRET"}),
        ("read_file", {"path": "ordinary.txt"}),
    ]:
        result = await loop.tool_registry.execute(name, args)
        assert "private" not in result.output


@pytest.mark.asyncio
async def test_file_write_requires_read_and_rejects_external_change(runtime):
    loop, _, root = runtime
    path = root / "a.py"
    path.write_text("initial")
    registry = loop.tool_registry
    assert not (
        await registry.execute("write_file", {"path": "a.py", "content": "new"})
    ).success
    assert (await registry.execute("read_file", {"path": "a.py"})).success
    # 内容校验不能只依赖 mtime；模拟保留时间戳的外部编辑。
    stamp = path.stat().st_mtime_ns
    path.write_text("external")
    os.utime(path, ns=(stamp, stamp))
    assert not (
        await registry.execute("write_file", {"path": "a.py", "content": "new"})
    ).success
    assert path.read_text() == "external"
    await registry.execute("read_file", {"path": "a.py"})
    assert (
        await registry.execute("write_file", {"path": "a.py", "content": "new"})
    ).success


@pytest.mark.asyncio
async def test_edit_rejects_empty_or_ambiguous_match(runtime):
    loop, _, root = runtime
    path = root / "a.py"
    path.write_text("same\nsame\n")
    await loop.tool_registry.execute("read_file", {"path": "a.py"})
    for old in ("", "same"):
        result = await loop.tool_registry.execute(
            "edit_file", {"path": "a.py", "old_string": old, "new_string": "changed"}
        )
        assert not result.success
    assert path.read_text() == "same\nsame\n"


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="Unix process group semantics")
@pytest.mark.parametrize("cancel", [True, False])
async def test_shell_cancellation_and_timeout_kill_children(runtime, cancel):
    _, _, root = runtime
    ready, marker = root / "ready", root / "after"
    script = f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(.6); Path({str(marker)!r}).touch()"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)} & wait"
    tool = ShellExecTool()
    tool.timeout = 0.2 if not cancel else 5
    task = asyncio.create_task(tool.execute(command))
    await wait_for_file(ready)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert not result.success and "超时" in result.error
    await asyncio.sleep(0.7)
    assert not marker.exists()


@pytest.mark.asyncio
async def test_large_output_is_bounded_and_saved(runtime):
    loop, _, root = runtime
    from tui_agent.tools.base import ToolBase, ToolResult

    class Large(ToolBase):
        name = "large"
        parameters = {"type": "object", "properties": {}}

        async def execute(self):
            return ToolResult.ok("x" * 80_000)

    loop.tool_registry.register(Large())
    result = await loop.tool_registry.execute("large", {})
    assert len(result.output) < 3000 and "read_file" in result.output
    saved = list((root / ".tui-agent" / "results").glob("*.txt"))
    assert len(saved) == 1 and len(saved[0].read_text()) == 80_000


def test_sdk_network_errors_are_retryable():
    import httpx
    from openai import APIConnectionError, APITimeoutError
    from tui_agent.llm.retry import is_retryable

    request = httpx.Request("GET", "https://example.invalid")
    assert is_retryable(APIConnectionError(request=request))
    assert is_retryable(APITimeoutError(request=request))


@pytest.mark.asyncio
async def test_cancel_active_tool_records_all_results_and_allows_new_task(runtime):
    from tui_agent.tools.base import ToolBase

    loop, provider, _ = runtime
    entered = asyncio.Event()

    class Hanging(ToolBase):
        name = "hanging"
        parameters = {"type": "object", "properties": {}}

        async def execute(self):
            entered.set()
            await asyncio.Event().wait()

    loop.tool_registry.register(Hanging())
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[
                    call("hanging", {}),
                    call("write_file", {"path": "never", "content": "no"}, "call_2"),
                ]
            ),
            MockLLMResponse(content="next"),
        ]
    )
    task = asyncio.create_task(collect(loop.run("hang")))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    results = [m for m in loop.session.messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in results] == ["call_1", "call_2"]
    assert not loop._busy and not loop.state.queued
    assert (await collect(loop.run("continue")))[-1].message == "next"


@pytest.mark.asyncio
async def test_search_timeout_for_pathological_regex(runtime):
    from tui_agent.tools.search import run_search

    _, _, root = runtime
    (root / "pathological.txt").write_text("a" * 5000 + "!")
    start = time.monotonic()
    result = await run_search("grep", "(a+)+$", timeout=0.3)
    assert not result.success and "超时" in result.error
    assert time.monotonic() - start < 3


@pytest.mark.asyncio
async def test_search_cancellation_reaps_worker(runtime, monkeypatch):
    from tui_agent.tools.search import run_search

    _, _, root = runtime
    (root / "pathological.txt").write_text("a" * 5000 + "!")
    processes = []
    created = asyncio.Event()
    original = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        created.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    task = asyncio.create_task(run_search("grep", "(a+)+$", timeout=5))
    await asyncio.wait_for(created.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_actual_tui_confirmation_and_stop(runtime):
    from tui_agent.config.schema import AppConfig
    from tui_agent.tui.app import TuiAgentApp
    from tui_agent.tui.widgets.confirm import ConfirmWidget

    loop, provider, root = runtime

    class TestApp(TuiAgentApp):
        def on_mount(self):
            from tui_agent.tui.screens import MainScreen

            self.push_screen(MainScreen())

        def init_agent(self):
            self.config = AppConfig()
            self.session = loop.session
            self.agent_loop = loop

    app = TestApp()
    provider.set_responses(
        [
            MockLLMResponse(
                tool_calls=[call("write_file", {"path": "approved", "content": "yes"})]
            ),
            MockLLMResponse(content="done"),
            MockLLMResponse(
                tool_calls=[
                    call("write_file", {"path": "cancelled", "content": "no"}, "call_2")
                ]
            ),
            MockLLMResponse(content="after stop"),
        ]
    )
    async with app.run_test(size=(100, 40)) as pilot:
        app._run_agent("first")
        await pilot.pause()
        assert app._waiting_confirmation and not loop._busy
        assert app.screen.query_one(ConfirmWidget).region.height > 0
        await pilot.press("a")
        await pilot.pause()
        assert (root / "approved").read_text() == "yes"
        assert not app._agent_running
        loop.permission_guard.reset_session_allow_all()
        app._run_agent("second")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not app._waiting_confirmation and not app._agent_running
        assert not (root / "cancelled").exists()
        app._run_agent("third")
        await pilot.pause()
        assert not app._agent_running
        assert loop.session.messages[-1]["content"] == "after stop"


def test_truncated_log_tail_can_be_repaired_on_next_save(runtime):
    loop, _, _ = runtime
    loop.session.add_user_message("first")
    path = save_session(loop.session)
    with path.open("ab") as handle:
        handle.write(b'{"type":"user","content":')
    restored = load_session(str(path))
    restored.add_user_message("recovered")
    save_session(restored)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert records[-1]["content"] == "recovered"


def test_message_budget_is_strict_and_does_not_mutate_history():
    from tui_agent.tools.output import apply_message_budget, MAX_MESSAGE_TOOL_CHARS

    messages = [
        {"role": "tool", "content": "文" * 20_000, "tool_call_id": str(i)}
        for i in range(20)
    ]
    bounded = apply_message_budget(messages)
    assert sum(len(m["content"]) for m in bounded) <= MAX_MESSAGE_TOOL_CHARS
    assert all(len(m["content"]) == 20_000 for m in messages)


@pytest.mark.asyncio
async def test_openai_stream_closes_when_consumer_stops():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from tui_agent.llm.openai_compat import OpenAICompatProvider

    closed = False

    class Response:
        def __aiter__(self):
            return self.events()

        async def events(self):
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="partial", tool_calls=None),
                        finish_reason=None,
                    )
                ]
            )
            await asyncio.Event().wait()

        async def close(self):
            nonlocal closed
            closed = True

    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    provider.model, provider.timeout, provider.max_retries = "test", 10, 0
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=Response()))
        )
    )
    stream = provider.chat([{"role": "user", "content": "hi"}])
    assert (await anext(stream))["content"] == "partial"
    await stream.aclose()
    assert closed


@pytest.mark.asyncio
async def test_recursive_glob_preserves_zero_and_multiple_levels(runtime):
    loop, _, root = runtime
    (root / "src" / "nested" / "deeper").mkdir(parents=True)
    for name in ("src/top.py", "src/nested/mid.py", "src/nested/deeper/end.py"):
        (root / name).write_text("pass")
    result = await loop.tool_registry.execute("glob_search", {"pattern": "src/**/*.py"})
    assert result.success
    assert all(name in result.output for name in ("top.py", "mid.py", "end.py"))
    shallow = await loop.tool_registry.execute("glob_search", {"pattern": "src/*.py"})
    assert "top.py" in shallow.output and "mid.py" not in shallow.output


async def test_paginated_read_accumulates_and_invalidates(runtime):
    loop, _, root = runtime
    registry = loop.tool_registry
    path = root / "pages.txt"
    content = "".join(f"line {i}\n" for i in range(700))
    path.write_text(content)
    read = registry.get("read_file")
    assert (await read.execute(str(path), start_line=1, end_line=350)).success
    assert (await read.execute(str(path), start_line=351, end_line=700)).success
    # 第一页的编辑证据和两页合并后的完整覆盖都必须有效。
    assert (
        await registry.get("edit_file").execute(str(path), "line 1\n", "changed\n")
    ).success
    assert (await registry.get("write_file").execute(str(path), content)).success
    path.write_text(content + "external\n")
    assert (await read.execute(str(path), start_line=351)).success
    assert not (
        await registry.get("write_file").execute(str(path), "overwrite")
    ).success
    assert not (
        await registry.get("edit_file").execute(str(path), "line 1\n", "bad")
    ).success


async def test_disjoint_read_regions_do_not_authorize_unread_content(runtime):
    loop, _, root = runtime
    p = root / "gap.txt"
    p.write_text("first\nunseen\nlast\n")
    read = loop.tool_registry.get("read_file")
    await read.execute(str(p), start_line=1, end_line=1)
    await read.execute(str(p), start_line=3, end_line=3)
    edit = loop.tool_registry.get("edit_file")
    assert not (await edit.execute(str(p), "unseen", "bad")).success
    assert (await edit.execute(str(p), "first", "longer first")).success
    assert (await edit.execute(str(p), "last", "end")).success
    assert not (
        await loop.tool_registry.get("write_file").execute(str(p), "bad")
    ).success


@pytest.mark.parametrize(
    "content",
    [
        "a" * 35000 + "TAIL_MARKER",
        "文" * 800000 + "TAIL_MARKER",
        "😀" * 600000 + "TAIL_MARKER",
    ],
)
async def test_stored_output_can_be_read_to_end(runtime, content):
    import re
    from tui_agent.tools.output import budget_result, MAX_STORED_BYTES

    loop, _, root = runtime
    result = budget_result(content)
    path = next((root / ".tui-agent/results").glob("*.txt"))
    assert str(path) in result
    assert path.stat().st_size <= MAX_STORED_BYTES
    read = loop.tool_registry.get("read_file")
    offset = 0
    seen_tail = False
    for _ in range(100):
        page = await read.execute(str(path), char_offset=offset)
        assert page.success, page.error
        seen_tail |= "TAIL_MARKER" in page.output
        match = re.search(r"char_offset=(\d+)", page.output)
        if match is None or int(match[1]) == offset:
            break
        offset = int(match[1])
    assert seen_tail
    assert loop.tool_registry.file_state.entries[path].full


async def test_single_query_compacts_completed_tool_batches(runtime):
    loop, provider, _ = runtime
    session = loop.session
    session.add_user_message("preserve original task")
    for i in range(8):
        session.add_assistant_message(
            "working", [call("read_file", {"path": "a"}, f"id{i}")]
        )
        session.add_tool_result(f"id{i}", "read_file", "large output " * 1000)
    original = deepcopy(session._transcript)
    provider.set_responses([MockLLMResponse(content="key decisions")])
    assert await compress_if_needed(session, provider, threshold=1000)
    assert session.messages[1]["content"] == "preserve original task"
    assert session._transcript == original
    calls = {c["id"] for m in session.messages for c in m.get("tool_calls", [])}
    results = {m["tool_call_id"] for m in session.messages if m["role"] == "tool"}
    assert calls == results == {"id6", "id7"}
    assert "key decisions" in str(session.messages)


@pytest.mark.parametrize("command", ["model", "provider"])
async def test_provider_switch_failure_preserves_all_state(monkeypatch, command):
    from unittest.mock import MagicMock
    from tui_agent.config.schema import AppConfig
    from tui_agent.tui.app import TuiAgentApp

    app = TuiAgentApp()
    app.config = AppConfig()
    app.config.llm.api_base = "https://custom.example/v1"
    app.session = SessionManager(model=app.config.llm.model)
    old = MagicMock(model=app.config.llm.model)
    app.agent_loop = MagicMock(llm_provider=old)
    app._update_header = MagicMock()
    before = app.config.model_dump()
    monkeypatch.setattr("tui_agent.tui.app.get_api_key", lambda _: "test-key")

    def fail(*args):
        raise RuntimeError("client setup failed")

    monkeypatch.setattr("tui_agent.tui.app.create_llm_provider", fail)
    handler = getattr(app, f"_handle_{command}_command")
    handler(
        MagicMock(),
        "claude-sonnet-4-5" if command == "model" else "anthropic",
    )
    assert app.config.model_dump() == before
    assert app.agent_loop.llm_provider is old
    assert app.session.model == before["llm"]["model"]


async def test_model_switch_commits_and_closes_old_client(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from tui_agent.config.schema import AppConfig
    from tui_agent.tui.app import TuiAgentApp

    app = TuiAgentApp()
    app.config = AppConfig()
    app.session = SessionManager(model=app.config.llm.model)
    old = MagicMock(aclose=AsyncMock())
    new = MagicMock(model="claude-sonnet-4-5")
    app.agent_loop = MagicMock(llm_provider=old)
    app._update_header = MagicMock()
    monkeypatch.setattr("tui_agent.tui.app.get_api_key", lambda _: "test-key")
    monkeypatch.setattr("tui_agent.tui.app.create_llm_provider", lambda *_: new)
    app._handle_model_command(MagicMock(), new.model)
    await asyncio.gather(*app._provider_cleanup_tasks)
    assert app.config.llm.model == app.session.model == new.model
    assert app.config.llm.provider == "anthropic"
    assert app.agent_loop.llm_provider is new
    old.aclose.assert_awaited_once()


async def test_repeated_compaction_retains_task_and_replaces_summary(runtime):
    loop, provider, _ = runtime
    session = loop.session
    session.add_user_message("original task")
    for cycle in range(3):
        for i in range(5):
            session.add_assistant_message("large progress " * 1000)
        provider.set_responses([MockLLMResponse(content=f"summary {cycle}")])
        assert await compress_if_needed(session, provider, threshold=1000)
        assert any(m.get("content") == "original task" for m in session.messages)
        summaries = [
            m
            for m in session.messages
            if m.get("content", "").startswith("[上下文摘要]")
        ]
        assert len(summaries) == 1
        assert f"summary {cycle}" in summaries[0]["content"]


async def test_actual_tui_cancel_active_tool_removes_spinner(runtime, monkeypatch):
    from tui_agent.config.schema import AppConfig
    from tui_agent.tui.app import TuiAgentApp
    from tui_agent.tui.widgets.chat import ChatWidget
    from tui_agent.tui.commands import Command

    loop, provider, _ = runtime
    entered = asyncio.Event()

    async def hanging(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(loop.tool_registry.get("read_file"), "execute", hanging)

    class TestApp(TuiAgentApp):
        def on_mount(self):
            from tui_agent.tui.screens import MainScreen

            self.push_screen(MainScreen())

        def init_agent(self):
            self.config = AppConfig()
            self.session = loop.session
            self.agent_loop = loop

    provider.set_responses(
        [MockLLMResponse(tool_calls=[call("read_file", {"path": "a"})])]
    )
    app = TestApp()
    async with app.run_test(size=(100, 40)) as pilot:
        app._run_agent("read")
        await asyncio.wait_for(entered.wait(), 2)
        await pilot.pause()
        chat = app.screen.query_one(ChatWidget)
        assert chat._running_widget is not None
        app._handle_command(Command.STOP, "")
        await pilot.pause()
        assert chat._running_widget is None
        assert not app._agent_running
        assert not list(chat.query(".tool-running"))


async def test_app_shutdown_waits_for_task_before_closing_provider():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from tui_agent.tui.app import TuiAgentApp

    order = []
    async def running():
        try:
            await asyncio.Event().wait()
        finally:
            order.append("task closed")
    async def close():
        order.append("client closed")
    app = TuiAgentApp()
    provider = SimpleNamespace(aclose=AsyncMock(side_effect=close))
    app.agent_loop = SimpleNamespace(llm_provider=provider)
    app._agent_task = asyncio.create_task(running())
    await asyncio.sleep(0)
    await app.on_unmount()
    assert app._agent_task.done()
    assert order == ["task closed", "client closed"]


async def test_llm_error_emits_one_message_and_preserves_partial_response(runtime):
    loop, provider, _ = runtime
    calls = []
    async def chat(*args, **kwargs):
        calls.append(True)
        yield {'type': 'text_delta', 'content': 'partial answer'}
        yield {'type': 'error', 'message': 'LLM 请求失败: Our servers are currently overloaded. Please try again later.'}
    provider.chat = chat
    events = [event async for event in loop.run('test')]
    errors = [event for event in events if isinstance(event, AgentError)]
    assert len(errors) == 1
    assert errors[0].message.count('LLM 请求失败:') == 1
    assert '暂时过载' in errors[0].message
    assert [e.message for e in events if isinstance(e, AgentFinished)] == ['']
    assert loop.checkpoint.data['status'] == 'failed'
    assert 'partial answer' in str(loop.session.build_messages())
    assert len(calls) == 1
