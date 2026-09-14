"""窗口适配、工具详情与状态提示的界面回归。"""

import pytest
from textual.widgets import Static

from tui_agent.config.schema import AppConfig
from tui_agent.tui.app import TuiAgentApp
from tui_agent.tui.welcome import WelcomeWidget
from tui_agent.tui.widgets.chat import ChatWidget, ToolResultWidget
from tui_agent.tui.widgets.confirm import ConfirmWidget
from tui_agent.tui.widgets.input import InputWidget


class LayoutApp(TuiAgentApp):
    def init_agent(self):
        self.config = AppConfig()
        self._update_header()
        self.screen.query_one(ChatWidget).mount_welcome(
            WelcomeWidget(provider="openai_compat", model="gpt-4o-mini", cwd="/workspace/demo", rotate_seconds=0)
        )


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (48, 20)])
async def test_layout_keeps_input_and_confirmation_visible(size):
    app = LayoutApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        field = app.screen.query_one(InputWidget)
        assert app.screen.query_one("#input-container").region.bottom <= app.screen.query_one("#header").region.y
        assert field.region.height == 1
        assert 0 <= field.region.y < size[1]
        welcome = app.screen.query_one(WelcomeWidget)
        assert len(app.screen.query(WelcomeWidget)) == 1
        assert welcome.has_class("compact") == (size[0] < 84)
        if welcome.has_class("compact"):
            left = welcome.query_one("#welcome-left")
            right = welcome.query_one("#welcome-right")
            assert right.region.y >= left.region.bottom
        app._show_confirm_widget("edit_file", "\n".join(f"+ example line {i}" for i in range(20)))
        app._update_header("等待确认")
        await pilot.pause()
        confirm = app.screen.query_one(ConfirmWidget)
        assert confirm.region.height > 0
        assert confirm.region.y >= 0
        assert confirm.region.bottom <= field.region.y
        assert confirm._option_widgets[-1].region.bottom <= confirm.region.bottom
        assert "N" in str(app.screen.query_one("#footer-hint", Static).content)


async def test_tool_details_keyboard_toggle_and_error_state():
    app = LayoutApp()
    async with app.run_test() as pilot:
        chat = app.screen.query_one(ChatWidget)
        chat.add_tool_result("read_file", {"path": "demo.py"}, "first\n[bold]literal[/bold]\nlast", True)
        await pilot.pause()
        tool = chat.query_one(ToolResultWidget)
        assert "literal" not in str(tool.content)
        tool.focus()
        await pilot.press("enter")
        assert "[bold]literal[/bold]" in str(tool.content)
        await pilot.press("space")
        assert "literal" not in str(tool.content)
        chat.add_tool_result("shell_exec", {}, "failure\nuseful diagnosis", False)
        await pilot.pause()
        failed = list(chat.query(ToolResultWidget))[-1]
        assert failed.has_class("tool-failed")
        assert "useful diagnosis" in str(failed.content)


async def test_plan_command_only_shows_plan():
    from tui_agent.tui.commands import Command
    from tests.conftest import MockLLMProvider, MockLLMResponse
    app = LayoutApp()
    async with app.run_test(size=(80, 24)) as pilot:
        provider = MockLLMProvider(); provider.set_responses([MockLLMResponse(content="先检查配置，再运行测试。")])
        app.agent_loop = type("Loop", (), {"llm_provider": provider, "state": type("State", (), {"turn_count": 0})()})()
        app._handle_command(Command.PLAN, "优化配置加载")
        await pilot.pause()
        text = " ".join(app.screen.query_one(ChatWidget).child_labels())
        assert "计划" in text and "优化配置加载" in text and "先检查配置" in text
        assert provider.last_tools == []

async def test_input_completion_popup_and_focus():
    from textual.widgets import Static
    app = LayoutApp(); app.config = type("Config", (), {"available_models": ["demo-model"]})()
    app.agent_loop = type("Loop", (), {"state": type("State", (), {"turn_count": 0})(), "tool_registry": type("Registry", (), {"_tools": {"read_file": object()}})(), "llm_provider": type("P", (), {"aclose": lambda self: __import__('asyncio').sleep(0)})()})()
    async with app.run_test(size=(80, 24)) as pilot:
        field = app.screen.query_one(InputWidget); field.focus(); await pilot.pause()
        assert app.focused is field
        field.value = "/p"; await pilot.pause()
        popup = app.screen.query_one("#completion-popup", Static)
        assert "/plan" in str(popup.content)
        await pilot.press("tab")
        assert app.focused is field and field.value == "/plan"


async def test_file_commands_show_checkpoint_report(tmp_path, monkeypatch):
    from tui_agent.session.checkpoint import Checkpoint
    from tui_agent.tools.workspace import set_workspace_root
    from tui_agent.tools.file_state import tracked_write
    from tui_agent.tui.commands import Command, parse_command
    monkeypatch.chdir(tmp_path)
    set_workspace_root(tmp_path)
    cp = Checkpoint.create('create file')
    tracked_write(tmp_path / 'demo.txt', 'hello\n', type('State', (), {'checkpoint': cp})())
    app = LayoutApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.agent_loop = type('Loop', (), {'checkpoint': cp})()
        app._handle_command(Command.FILES, '')
        app._handle_command(Command.DIFF, 'demo.txt')
        await pilot.pause()
        text = ' '.join(app.screen.query_one(ChatWidget).child_labels())
        assert '新增 demo.txt' in text and '+hello' in text
        assert parse_command('/diff demo.txt').command == Command.DIFF
        assert parse_command('/files').command == Command.FILES
        app.agent_loop = None


async def test_welcome_collapses_without_losing_input_focus():
    app = LayoutApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        field = app.screen.query_one(InputWidget)
        field.focus()
        chat = app.screen.query_one(ChatWidget)
        welcome = chat.query_one(WelcomeWidget)
        original_height = welcome.size.height
        chat.add_user_message('开始检查')
        await pilot.pause()
        assert welcome.has_class('dismissed')
        assert welcome.size.height == 1 < original_height
        assert app.focused is field
        chat.add_user_message('继续')
        await pilot.pause()
        assert len(welcome.query('.welcome-summary')) == 1


async def test_diff_folding_and_literal_content():
    from tui_agent.tui.widgets.diff import DiffWidget, color_diff
    app = LayoutApp()
    async with app.run_test(size=(120, 40)) as pilot:
        widget = DiffWidget('demo.txt +20 / -0', '\n'.join(f'+[bold]line {i}' for i in range(20)))
        await app.screen.query_one(ChatWidget).mount(widget)
        assert '[bold]' not in str(widget.content)
        widget.focus()
        await pilot.press('enter')
        assert '+[bold]line 19' in str(widget.content)
        assert app.focused is widget
        await pilot.press('space')
        assert '[bold]' not in str(widget.content)
        text = color_diff('+added\n-removed\n')
        assert [span.style for span in text.spans] == ['#7ee787', '#e06c75']


@pytest.mark.parametrize('size', [(120, 40), (48, 20)])
async def test_model_picker_keyboard_and_focus(size):
    from tui_agent.tui.commands import Command
    from tui_agent.tui.widgets.choice import ChoiceScreen
    from textual.widgets import OptionList
    app = LayoutApp()
    chosen = []
    async with app.run_test(size=size) as pilot:
        app._rebuild_llm_provider = lambda config: chosen.append(config.model)
        app._handle_command(Command.MODEL, '')
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        assert isinstance(app.focused, OptionList)
        panel = app.screen.query_one('#choice-panel')
        assert 0 <= panel.region.y < panel.region.bottom <= size[1]
        await pilot.press('down', 'enter')
        await pilot.pause()
        assert chosen == [app.config.available_models[1]]
        assert isinstance(app.focused, InputWidget)
        app._handle_command(Command.PROVIDER, '')
        await pilot.pause()
        await pilot.press('escape')
        await pilot.pause()
        assert isinstance(app.focused, InputWidget)
        assert chosen == [app.config.available_models[1]]


@pytest.mark.parametrize('surface', ['input', 'picker', 'confirmation'])
async def test_ctrl_c_exits_from_all_surfaces(surface):
    from tui_agent.tui.commands import Command
    app = LayoutApp()
    async with app.run_test(size=(80, 24)) as pilot:
        if surface == 'picker':
            app._handle_command(Command.MODEL, '')
        elif surface == 'confirmation':
            app._show_confirm_widget('write_file', '新增 example.txt')
            app._waiting_confirmation = True
        await pilot.pause()
        if surface != 'input':
            await pilot.press('ctrl+c')
            await pilot.pause()
            assert not app._exiting
        await pilot.press('ctrl+c')
        await pilot.pause()
        assert not app._exiting
        await pilot.press('ctrl+c')
        await pilot.pause()
        assert app._exiting
        assert not app.is_running


async def test_empty_input_does_not_complete_unrelated_command():
    app = LayoutApp()
    async with app.run_test() as pilot:
        field = app.screen.query_one(InputWidget)
        field.value = '/p'
        await pilot.pause()
        field.value = ''
        await pilot.pause()
        await pilot.press('tab')
        assert field.value == ''
        assert not app.screen.query_one('#completion-popup').display
        assert app.focused is field


async def test_sessions_picker_uses_selected_snapshot(monkeypatch):
    from tui_agent.tui.commands import Command
    sessions = [dict(last_active='today', model='demo', preview=f'session {i}') for i in range(12)]
    monkeypatch.setattr('tui_agent.session.loader.list_sessions', lambda: sessions)
    app = LayoutApp()
    selected = []
    async with app.run_test() as pilot:
        app._resume_session_at = selected.append
        app._handle_command(Command.SESSIONS, '')
        await pilot.pause()
        await pilot.press('end', 'enter')
        await pilot.pause()
        assert selected == [11]
        assert isinstance(app.focused, InputWidget)


async def test_ctrl_c_copies_selection_before_interrupting():
    from textual.widgets._input import Selection
    app = LayoutApp()
    copied = []
    async with app.run_test() as pilot:
        app.copy_to_clipboard = copied.append
        field = app.screen.query_one(InputWidget)
        field.value = 'copy this'
        field.selection = Selection(0, 4)
        app._agent_running = True
        await pilot.press('ctrl+c')
        assert copied == ['copy']
        assert app._agent_running and not app._exiting
        field.selection = Selection(9, 9)
        app._agent_running = False
        await pilot.press('ctrl+c')
        assert field.value == '' and not app._exit_armed_at


async def test_ctrl_c_copies_chat_selection_and_expired_exit_does_not_quit(monkeypatch):
    app = LayoutApp()
    copied = []
    async with app.run_test() as pilot:
        app.copy_to_clipboard = copied.append
        monkeypatch.setattr(app.screen, 'get_selected_text', lambda: 'chat selection')
        await pilot.press('ctrl+c')
        assert copied == ['chat selection'] and not app._exit_armed_at
        monkeypatch.setattr(app.screen, 'get_selected_text', lambda: None)
        monkeypatch.setattr('tui_agent.tui.app.monotonic', lambda: 100.0)
        app._exit_armed_at = 97.0
        await pilot.press('ctrl+c')
        assert not app._exiting and app._exit_armed_at == 100.0
