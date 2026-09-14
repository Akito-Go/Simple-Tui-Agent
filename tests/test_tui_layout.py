"""窗口适配、工具详情与状态提示的界面回归。"""

import pytest
from textual.widgets import Static

from tui_agent.config.schema import AppConfig
from tui_agent.tui.app import TuiAgentApp
from tui_agent.tui.screens import MainScreen
from tui_agent.tui.welcome import WelcomeWidget
from tui_agent.tui.widgets.chat import ChatWidget, ToolResultWidget
from tui_agent.tui.widgets.confirm import ConfirmWidget
from tui_agent.tui.widgets.input import InputWidget


class LayoutApp(TuiAgentApp):
    def on_mount(self):
        self.push_screen(MainScreen())

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
        chat.add_tool_result("read_file", {"path": "demo.py"}, True, "first\n[bold]literal[/bold]\nlast", True)
        await pilot.pause()
        tool = chat.query_one(ToolResultWidget)
        assert "literal" not in str(tool.content)
        tool.focus()
        await pilot.press("enter")
        assert "[bold]literal[/bold]" in str(tool.content)
        await pilot.press("space")
        assert "literal" not in str(tool.content)
        chat.add_tool_result("shell_exec", {}, False, "failure\nuseful diagnosis", False)
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
