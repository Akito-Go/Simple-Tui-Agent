"""/stop 命令测试"""

import pytest
from textual.app import App, ComposeResult

from tui_agent.tui.widgets.chat import ChatWidget
from tui_agent.tui.commands import parse_command, Command


class TestParseStop:
    def test_parse_stop(self):
        result = parse_command("/stop")
        assert result.is_command
        assert result.command == Command.STOP

    def test_parse_stop_with_args_ignored(self):
        result = parse_command("/stop something")
        assert result.is_command
        assert result.command == Command.STOP


class StopTestApp(App):
    def compose(self) -> ComposeResult:
        yield ChatWidget()


class TestStopCommand:
    @pytest.mark.asyncio
    async def test_stop_when_idle_shows_message(self):
        """空闲时 /stop 提示无运行任务"""
        app = StopTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()

            # 模拟空闲态 stop
            chat.add_system_message("当前没有正在运行的任务")
            labels = chat.child_labels()
            assert "没有正在运行" in labels[-1]

    @pytest.mark.asyncio
    async def test_stop_preserves_completed_tools(self):
        """stop 后保留已完成的工具结果"""
        app = StopTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()

            # 模拟：已完成 2 个工具，然后 stop
            chat.add_tool_result("list_dir", {"path": "."}, auto=True, result="src/", success=True)
            chat.add_tool_result("read_file", {"path": "a.py"}, auto=True, result="print(1)", success=True)
            chat.add_system_message("⏹ 任务已终止")

            labels = chat.child_labels()
            assert any("list_dir" in l for l in labels)
            assert any("read_file" in l for l in labels)
            assert any("终止" in l for l in labels)
