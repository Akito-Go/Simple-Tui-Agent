"""主界面布局 — Header + Body + Footer"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container

from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget


class MainScreen(Screen):
    """主界面 — 全屏对话流布局"""

    CSS = """
    #header {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    #chat {
        height: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }

    #input-container {
        dock: bottom;
        height: auto;
        min-height: 3;
        padding: 1;
        border-top: solid $primary;
    }

    #input {
        width: 100%;
    }

    .user-msg {
        color: $success;
        margin: 1 0;
    }

    .assistant-msg {
        color: $text;
        margin: 0 0;
    }

    .tool-msg {
        color: $warning;
        margin: 0 0;
    }

    .tool-result {
        color: $text-muted;
        margin: 0 0 1 2;
    }

    .permission-msg {
        color: $warning;
        margin: 1 0;
    }

    .denied-msg {
        color: $error;
        margin: 1 0;
    }

    .error-msg {
        color: $error;
        margin: 1 0;
    }

    .system-msg {
        color: $secondary;
        margin: 1 0;
    }

    .thinking-msg {
        color: $text-muted;
        margin: 1 0;
    }

    #confirm-container {
        dock: bottom;
        height: auto;
        padding: 1;
        border-top: solid $warning;
        background: $surface;
    }

    .confirm-inline {
        margin: 1 0;
        height: auto;
        border: solid $warning;
        padding: 0 1;
    }

    .confirm-hint {
        color: $text-muted;
        margin: 0 0 1 0;
    }

    .tool-running {
        color: $warning;
        margin: 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield HeaderWidget()
        yield ChatWidget()
        with Container(id="input-container"):
            yield InputWidget()

    def on_mount(self) -> None:
        """Screen 挂载后通知 App 初始化 Agent"""
        self.app.init_agent()
