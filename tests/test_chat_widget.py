"""ChatWidget 展示逻辑测试"""

import pytest
from textual.app import App, ComposeResult

from tui_agent.tui.widgets.chat import (
    ChatWidget,
    _format_tool_args,
    _normalize_display_text,
)


class ChatTestApp(App):
    def compose(self) -> ComposeResult:
        yield ChatWidget()


class TestChatHelpers:
    def test_format_tool_args_collapses_multiline_content(self):
        args = _format_tool_args({
            "content": "#!/usr/bin/env python3\n\n\"\"\"贪吃蛇\"\"\"\nprint('hi')",
            "path": "snake_game.py",
        })
        assert "\n" not in args
        assert "content=" in args
        assert "path=snake_game.py" in args

    def test_normalize_display_text_collapses_blank_lines(self):
        text = "第一段\n\n\n\n\n第二段\n\n"
        assert _normalize_display_text(text) == "第一段\n\n第二段"

    def test_normalize_display_text_strips_trailing_blank_lines(self):
        assert _normalize_display_text("你好。\n\n\n\n") == "你好。"

    @pytest.mark.asyncio
    async def test_thinking_shows_spinner_on_assistant_line(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()
            chat.show_thinking()
            label = chat.child_labels()[0]
            assert label.startswith("🤖 ")
            assert "思考中" in label
            assert any(frame in label for frame in ["⠋", "⠙", "⠹"])


class TestChatWidgetOrder:
    @pytest.mark.asyncio
    async def test_tool_calls_follow_streaming_segments_in_order(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()

            chat.start_streaming()
            chat.append_streaming("先看目录。")
            chat.show_tool_running("list_dir", {"path": "."})
            chat.add_tool_result("list_dir", {"path": "."}, auto=True, result="main.py", success=True)
            chat.start_streaming()
            chat.append_streaming("继续写代码。")
            chat.finish_streaming()

            labels = chat.child_labels()
            assert labels[0].startswith("🤖 先看目录。")
            assert labels[1].startswith("⚡ list_dir")
            assert labels[2].startswith("🤖 继续写代码。")

    @pytest.mark.asyncio
    async def test_assistant_keeps_spinner_during_tool_execution(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()

            chat.start_streaming()
            chat.append_streaming("先看目录。")
            chat.show_tool_running("list_dir", {"path": "."})

            labels = chat.child_labels()
            assert labels[0].startswith("🤖 ")
            assert any(frame in labels[0] for frame in ["⠋", "⠙", "⠹"])
            assert "先看目录。" in labels[0]
            assert labels[1].startswith("⚡ list_dir")

            chat.add_tool_result("list_dir", {"path": "."}, auto=True, result="main.py", success=True)
            labels = chat.child_labels()
            assert labels[0] == "🤖 先看目录。"
            assert "⠋" not in labels[0]

    @pytest.mark.asyncio
    async def test_show_tool_running_finalizes_active_stream(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()

            chat.start_streaming()
            chat.append_streaming("准备执行工具")
            assert chat._streaming_widget is not None

            chat.show_tool_running("read_file", {"path": "a.py"})
            assert chat._streaming_widget is None

            labels = chat.child_labels()
            assert "准备执行工具" in labels[0]
            assert labels[1].startswith("⚡ read_file")
