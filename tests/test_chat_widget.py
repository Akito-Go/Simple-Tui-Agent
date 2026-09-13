"""ChatWidget 展示逻辑测试"""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from tui_agent.tui.widgets.chat import (
    ChatWidget,
    _format_tool_args,
    _normalize_display_text,
)
from tui_agent.tui.welcome import (
    WELCOME_ICON,
    WELCOME_TIPS,
    WelcomeWidget,
    build_welcome_banner,
    get_app_version,
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


class TestWelcomeBanner:
    def test_welcome_icon_uses_block_texture(self):
        # 「STA」欢迎吉祥物：Q 版小猫块字（█ ▄ ▀）
        assert "█" in WELCOME_ICON and "▄" in WELCOME_ICON and "▀" in WELCOME_ICON
        assert len(WELCOME_ICON.splitlines()) >= 6

    def test_banner_includes_version_and_tip(self):
        banner = build_welcome_banner(
            provider="openai_compat",
            model="gpt-4o-mini",
            cwd="/tmp/demo",
            max_turns=50,
            context_max_tokens=80000,
            tip_index=0,
            app_version="0.1.0",
        )
        assert "STA" in banner
        assert "tui-agent v0.1.0" in banner
        assert "gpt-4o-mini" in banner
        assert "openai_compat" in banner
        assert "最大轮次" in banner
        assert WELCOME_TIPS[0] in banner
        assert "入门提示" in banner
        assert "最近活动" in banner
        assert get_app_version()

    @pytest.mark.asyncio
    async def test_welcome_widget_two_pane_layout(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()
            widget = WelcomeWidget(
                provider="openai_compat",
                model="gpt-4o-mini",
                cwd="/tmp/demo",
                max_turns=50,
                recent_sessions=[
                    {
                        "last_active": "今天",
                        "model": "gpt-4o-mini",
                        "preview": "测试会话",
                    }
                ],
                rotate_seconds=0,
            )
            chat.mount_welcome(widget)
            await pilot.pause()
            assert widget.border_title
            assert "STA" in widget.border_title
            assert "tui-agent" in widget.border_title
            assert app.query_one("#welcome-left")
            assert app.query_one("#welcome-right")
            assert app.query_one("#welcome-right-top")
            tip = app.query_one("#welcome-tip", Static)
            recent = app.query_one("#welcome-recent", Static)
            assert str(tip.content)
            assert "测试会话" in str(recent.content)

    @pytest.mark.asyncio
    async def test_welcome_widget_rotates_tips(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()
            widget = WelcomeWidget(
                provider="openai_compat",
                model="m",
                cwd="/tmp",
                rotate_seconds=0,
            )
            widget._tip_index = 0
            chat.mount_welcome(widget)
            await pilot.pause()
            tip = app.query_one("#welcome-tip", Static)
            tip.update(WELCOME_TIPS[0])
            assert WELCOME_TIPS[0] in str(tip.content)
            widget._rotate_tip()
            assert WELCOME_TIPS[1] in str(tip.content)


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
            assert labels[0] == "🤖 先看目录。"
            assert labels[1].startswith("● list_dir")
            assert "⎿" in labels[1]
            assert labels[2] == "🤖 继续写代码。"

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
            assert labels[1].startswith("● list_dir")

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
            assert labels[1].startswith("● read_file")

    @pytest.mark.asyncio
    async def test_user_message_uses_icon(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()
            chat.add_user_message("hello")
            assert chat.child_labels()[0] == "👤 hello"

    @pytest.mark.asyncio
    async def test_welcome_message_class(self):
        app = ChatTestApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatWidget)
            await pilot.pause()
            chat.add_welcome("STA")
            assert chat.child_labels()[0] == "STA"
