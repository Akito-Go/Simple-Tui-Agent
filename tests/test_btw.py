"""旁路问答的上下文隔离、并发与取消。"""

import asyncio
from copy import deepcopy

from tests.conftest import MockLLMProvider, MockLLMResponse
from tests.test_tui_layout import LayoutApp
from tui_agent.session.manager import SessionManager
from tui_agent.tui.btw import build_btw_messages
from tui_agent.tui.commands import Command


def test_btw_context_is_bounded_and_has_no_tool_protocol():
    history = [{'role': 'system', 'content': 'old instructions'}, {'role': 'assistant', 'tool_calls': [{}]}]
    history += [{'role': 'tool', 'content': 'x' * 4000} for _ in range(20)]
    before = deepcopy(history)
    messages = build_btw_messages(history, 'question')
    assert history == before
    assert len(messages[1]['content']) < 12100
    assert 'old instructions' not in str(messages)
    assert not any('tool_calls' in m or m['role'] == 'tool' for m in messages)
    assert messages[-1]['content'] == 'question'


async def test_btw_runs_beside_main_without_mutating_session(monkeypatch):
    provider = MockLLMProvider()
    provider.set_responses([MockLLMResponse(content='temporary answer')])
    closed = []
    async def close():
        closed.append(True)
    provider.aclose = close
    monkeypatch.setattr('tui_agent.tui.app.create_llm_provider', lambda *args: provider)
    monkeypatch.setattr('tui_agent.tui.app.get_api_key', lambda *args: 'test-key')
    app = LayoutApp()
    async with app.run_test() as pilot:
        app.session = SessionManager()
        app.session.add_user_message('main task')
        before = deepcopy(app.session.__dict__)
        main_provider = object()
        app.agent_loop = type('Loop', (), {'llm_provider': main_provider, 'tool_registry': type('Registry', (), {'_tools': {}})()})()
        app._agent_running = True
        main = app._agent_task = asyncio.create_task(asyncio.Event().wait())
        field = app.screen.query_one('#input')
        field.value = '/btw explain this'
        await pilot.press('enter')
        await pilot.pause()
        assert 'temporary answer' in str(app._btw_widget.content)
        assert provider.last_tools == [] and closed
        assert app.session.__dict__ == before
        assert app._agent_task is main and not main.done()
        assert app.agent_loop.llm_provider is main_provider
        await pilot.press('escape')
        await pilot.pause()
        assert app._btw_widget is None
        assert app._agent_running and not main.done()
        main.cancel()
        await asyncio.gather(main, return_exceptions=True)
        app._agent_running = False
        app.agent_loop = None


async def test_btw_cancel_closes_stream_and_keeps_input(monkeypatch):
    started, closed = asyncio.Event(), []
    class Provider:
        async def chat(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
                yield {}
            finally:
                closed.append('stream')
        async def aclose(self):
            closed.append('provider')
    monkeypatch.setattr('tui_agent.tui.app.create_llm_provider', lambda *args: Provider())
    monkeypatch.setattr('tui_agent.tui.app.get_api_key', lambda *args: 'test-key')
    app = LayoutApp()
    async with app.run_test() as pilot:
        app.agent_loop = object()
        app._handle_command(Command.BTW, 'question')
        await asyncio.wait_for(started.wait(), 2)
        await pilot.press('escape')
        await pilot.pause()
        assert closed == ['stream', 'provider']
        assert app._btw_widget is None
        assert not app.screen.query_one('#input').disabled
        app.agent_loop = None


async def test_btw_and_confirmation_fit_short_terminal(monkeypatch):
    provider = MockLLMProvider()
    provider.set_responses([MockLLMResponse(content='answer\n' * 30)])
    monkeypatch.setattr('tui_agent.tui.app.create_llm_provider', lambda *args: provider)
    monkeypatch.setattr('tui_agent.tui.app.get_api_key', lambda *args: 'test-key')
    app = LayoutApp()
    async with app.run_test(size=(48, 20)) as pilot:
        app.agent_loop = object()
        app._handle_command(Command.BTW, 'question')
        await pilot.pause()
        app._show_confirm_widget('write_file', '修改 example.txt\n' * 20)
        await pilot.pause()
        confirm = app.screen.query_one('.confirm-inline')
        field = app.screen.query_one('#input')
        assert confirm._option_widgets[-1].region.bottom <= field.region.y < 20
        await app._close_btw()
        app.agent_loop = None
