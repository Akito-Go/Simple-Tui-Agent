"""主界面布局 — 对齐 Claude Code：橙框欢迎页 + 细线输入区"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Horizontal
from textual.widgets import Static

from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget


class MainScreen(Screen):
    """主界面 — Claude Code 骨架"""

    CSS = """
    Screen {
        background: #1a1a1a;
    }

    #header {
        dock: bottom;
        height: 1;
        background: #1a1a1a;
        color: #8a857c;
        padding: 0 1;
    }

    #chat {
        height: 1fr;
        padding: 1 2 0 2;
        overflow-y: auto;
        background: #1a1a1a;
        scrollbar-color: #3a3a3a #1a1a1a;
        scrollbar-size: 1 1;
    }

    /* 底部：确认槽 + 细线夹着的单行输入 + 快捷提示 */
    #input-container {
        dock: bottom;
        height: auto;
        padding: 0 1;
        background: #1a1a1a;
    }

    #confirm-slot {
        height: auto;
        margin: 0;
        padding: 0;
    }

    /* height=3：上下细线各占 1 行，中间留给 > 与输入（height:1 会被边框吃光） */
    #input-wrap {
        height: 3;
        layout: horizontal;
        border-top: solid #3a3a3a;
        border-bottom: solid #3a3a3a;
        background: #1a1a1a;
        padding: 0 1;
        align: left middle;
    }

    #input-prompt {
        width: 2;
        height: 1;
        color: #f0ece4;
        content-align: left middle;
    }

    #input {
        width: 1fr;
        height: 1;
        background: #1a1a1a;
        border: none;
        color: #f0ece4;
        padding: 0;
    }

    #input:focus {
        background: #1a1a1a;
    }

    #footer-hint {
        color: #6b6560;
        padding: 0 1;
        height: 1;
        text-style: dim;
    }

    .welcome-msg {
        color: #da7756;
        margin: 0 0 1 0;
        text-style: bold;
    }

    .welcome-panel {
        margin: 0 0 1 0;
    }

    .user-msg {
        color: #7ee787;
        margin: 1 0 0 0;
        text-style: bold;
        border-left: thick #3fb950;
        padding-left: 1;
    }

    .assistant-msg {
        color: #e8e4dc;
        margin: 0 0 1 0;
        border-left: thick #da7756;
        padding-left: 1;
    }

    .tool-msg {
        color: #e2c08d;
        margin: 0 0;
    }

    .tool-result {
        color: #9a958c;
        margin: 0 0 1 1;
        border-left: solid #3a3a3a;
        padding-left: 1;
    }

    .tool-running {
        color: #e2c08d;
        margin: 0 0 0 1;
        border-left: solid #e2c08d;
        padding-left: 1;
    }

    .permission-msg {
        color: #e2c08d;
        margin: 0;
        height: auto;
        max-height: 3;
        text-style: bold;
    }

    .denied-msg {
        color: #e06c75;
        margin: 1 0;
        border-left: thick #e06c75;
        padding-left: 1;
    }

    .error-msg {
        color: #e06c75;
        margin: 1 0;
        text-style: bold;
        border-left: thick #e06c75;
        padding-left: 1;
    }

    .system-msg {
        color: #8a857c;
        margin: 1 0;
        background: #222222;
        border-left: thick #6b6560;
        padding: 0 1;
    }

    .thinking-msg {
        color: #8a857c;
        margin: 1 0;
        text-style: dim italic;
    }

    .confirm-inline {
        margin: 0;
        height: auto;
        max-height: 10;
        border: solid #e2c08d;
        background: #2a2418;
        padding: 0 1;
    }

    .confirm-hint {
        color: #6b6560;
        margin: 0;
        height: 1;
        text-style: dim;
    }

    .confirm-option {
        color: #c8c2b8;
        height: 1;
        padding: 0 1;
    }

    .confirm-option-selected {
        color: #1a1a1a;
        background: #da7756;
        text-style: bold;
        height: 1;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        # dock:bottom 先挂载贴最底 → 状态行 → 输入区（上细线 / > / 下细线 / 提示）
        yield ChatWidget()
        yield HeaderWidget()
        with Container(id="input-container"):
            yield Container(id="confirm-slot")
            with Horizontal(id="input-wrap"):
                yield Static(">", id="input-prompt", markup=False)
                yield InputWidget()
            yield Static(
                "Esc=/stop · /help · /sessions · 写入与 Shell 需确认 · 只读自动执行",
                id="footer-hint",
                markup=False,
            )

    def on_mount(self) -> None:
        """Screen 挂载后通知 App 初始化 Agent"""
        self.app.init_agent()
