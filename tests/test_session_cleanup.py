"""历史清理的预览、路径、当前会话保护与删除确认。"""

import json

import pytest

from tui_agent.session.cleanup import prepare_cleanup
from tui_agent.session.manager import SessionManager
from tui_agent.session.storage import save_session
from tui_agent.tools.workspace import set_workspace_root


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_workspace_root(tmp_path)
    old, current = SessionManager(), SessionManager()
    for session in (old, current):
        session.add_user_message('example')
        save_session(session)
    cp = tmp_path / '.tui-agent/checkpoints/old.json'
    cp.parent.mkdir()
    cp.write_text(json.dumps({'session_id': old.session_id}))
    return tmp_path, old, current, cp


def test_cleanup_deletes_only_selected_history_and_checkpoint(history):
    root, old, current, cp = history
    project = root / 'project.txt'
    project.write_text('keep')
    plan = prepare_cleanup([old.session_id], current.session_id)
    assert len(plan.files) == 2
    assert cp.exists()
    assert plan.delete(current.session_id) == 2
    assert not cp.exists()
    assert (root / f'.tui-agent/logs/{current.session_id}.jsonl').exists()
    assert project.read_text() == 'keep'


def test_cleanup_protects_current_and_rejects_changes(history):
    root, old, current, cp = history
    with pytest.raises(ValueError):
        prepare_cleanup([current.session_id], current.session_id)
    plan = prepare_cleanup([old.session_id], current.session_id)
    with pytest.raises(ValueError):
        plan.delete(old.session_id)
    cp.write_text(json.dumps({'session_id': old.session_id, 'changed': True}))
    with pytest.raises(ValueError, match='预览后'):
        plan.delete(current.session_id)
    assert (root / f'.tui-agent/logs/{old.session_id}.jsonl').exists()


def test_cleanup_rejects_symlink_and_traversal(history):
    root, old, current, _ = history
    with pytest.raises(ValueError):
        prepare_cleanup(['../outside'])
    log = root / f'.tui-agent/logs/{old.session_id}.jsonl'
    log.unlink()
    target = root / 'keep.txt'
    target.write_text('keep')
    log.symlink_to(target)
    with pytest.raises(ValueError, match='符号链接'):
        prepare_cleanup([old.session_id], current.session_id)
    assert target.read_text() == 'keep'


async def test_cleanup_menu_requires_explicit_delete(history):
    from tests.test_tui_layout import LayoutApp
    from tui_agent.tui.commands import Command
    from tui_agent.tui.widgets.choice import ChoiceScreen
    from tui_agent.tui.widgets.input import InputWidget
    root, old, current, cp = history
    app = LayoutApp()
    async with app.run_test() as pilot:
        app.session = current
        app._handle_command(Command.SESSIONS, 'delete')
        await pilot.pause()
        await pilot.press('enter')
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        await pilot.press('enter')  # 默认取消
        await pilot.pause()
        assert cp.exists() and isinstance(app.focused, InputWidget)
        app._handle_command(Command.SESSIONS, 'delete all')
        await pilot.pause()
        await pilot.press('down', 'enter')
        await pilot.pause()
        assert not cp.exists()
        assert (root / f'.tui-agent/logs/{current.session_id}.jsonl').exists()


def test_empty_session_is_not_saved_or_listed(history):
    from tui_agent.session.loader import list_sessions
    root, _, _, _ = history
    empty = SessionManager()
    assert not save_session(empty).exists()
    legacy = root / '.tui-agent/logs/session_empty.jsonl'
    legacy.write_text('{"type":"meta","model":"demo"}\n')
    assert 'session_empty' not in {s['session_id'] for s in list_sessions()}
    empty.add_user_message('real conversation')
    assert save_session(empty).exists()
    assert empty.session_id in {s['session_id'] for s in list_sessions()}


async def test_delete_history_then_exit_empty_session_does_not_recreate_history(history):
    from tests.test_tui_layout import LayoutApp
    from tui_agent.session.loader import list_sessions
    root, old, current, _ = history
    fresh = SessionManager()
    prepare_cleanup([old.session_id, current.session_id], fresh.session_id).delete(fresh.session_id)
    app = LayoutApp()
    async with app.run_test() as pilot:
        app.session = fresh
        await app.action_exit_app()
        await pilot.pause()
    assert list_sessions() == []
    assert list((root / '.tui-agent/logs').glob('session_*.jsonl')) == []


def test_singular_session_command_alias():
    from tui_agent.tui.commands import Command, parse_command
    result = parse_command('/session delete all')
    assert result.command == Command.SESSIONS and result.args == 'delete all'
    assert not parse_command('/session-other').is_command
