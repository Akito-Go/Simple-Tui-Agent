""" /sessions 命令解析与欢迎页提示 """

from tui_agent.tui.commands import Command, parse_command
from tui_agent.tui.welcome import WELCOME_ICON, WELCOME_TIPS, _format_recent_activity


class TestSessionsCommandParse:
    def test_parse_sessions(self):
        result = parse_command("/sessions")
        assert result.is_command
        assert result.command == Command.SESSIONS
        assert result.args == ""

    def test_parse_sessions_with_index(self):
        result = parse_command("/sessions 2")
        assert result.is_command
        assert result.command == Command.SESSIONS
        assert result.args == "2"


class TestWelcomeCatAndSessionsHint:
    def test_welcome_icon_is_block_cat(self):
        assert "█" in WELCOME_ICON and "▄" in WELCOME_ICON and "▀" in WELCOME_ICON
        # Q 版小猫应有双耳轮廓（两段顶部块）
        lines = WELCOME_ICON.splitlines()
        assert len(lines) >= 6

    def test_recent_activity_and_sessions_tip(self):
        assert "暂无最近活动" in _format_recent_activity([])
        assert "hi" in _format_recent_activity(
            [{"last_active": "今天", "model": "m", "preview": "hi"}]
        )
        # /sessions 引导放在 tips，对齐 Claude「No recent activity」简洁展示
        assert any("/sessions" in tip for tip in WELCOME_TIPS)
