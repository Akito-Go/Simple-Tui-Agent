"""主界面布局 — Claude Code 骨架 + 对话气泡图标"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Static

from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget


class MainScreen(Screen):
    """主界面 — Claude Code 布局 + 用户/助手图标与对话框感"""

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
        border-top: solid #2a2a2a;
    }

    #chat {
        height: 1fr;
        padding: 1 2 0 2;
        overflow-y: auto;
        background: #1a1a1a;
        scrollbar-color: #3a3a3a #1a1a1a;
        scrollbar-size: 1 1;
    }

    #input-container {
        dock: bottom;
        height: auto;
        min-height: 3;
        padding: 0 1 0 1;
        background: #1a1a1a;
        border-top: solid #2a2a2a;
    }

    #footer-hint {
        color: #6b6560;
        padding: 0 1;
        height: 1;
        text-style: dim;
    }

    #input {
        width: 100%;
        background: #1a1a1a;
        border: none;
        border-left: thick #da7756;
        color: #f0ece4;
        padding: 0 1;
    }

    #input:focus {
        border-left: thick #da7756;
        background: #222222;
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
        margin: 0 0;
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
        margin: 1 0;
        height: auto;
        border: double #e2c08d;
        background: #222222;
        padding: 0 1 1 1;
    }

    .confirm-hint {
        color: #6b6560;
        margin: 0 0 1 0;
        text-style: dim;
    }

    .confirm-option {
        color: #c8c2b8;
        padding: 0 1;
    }

    .confirm-option-selected {
        color: #1a1a1a;
        background: #da7756;
        text-style: bold;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        # dock:bottom 先挂载的贴最底 → 状态行在底，输入区在其上
        yield ChatWidget()
        yield HeaderWidget()
        with Container(id="input-container"):
            yield Static(
                "? for shortcuts · /help · 写入/Shell 需确认 · Y/A/N",
                id="footer-hint",
            )
            yield InputWidget()

    def on_mount(self) -> None:
        """Screen 挂载后通知 App 初始化 Agent"""
        self.app.init_agent()
