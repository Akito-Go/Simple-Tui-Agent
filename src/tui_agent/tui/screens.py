"""主界面布局 — 自适应欢迎页、工具详情与状态反馈"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Static
from textual import events

from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget


class MainScreen(Screen):
    """主界面 — 对话区和固定底部操作区"""

    CSS = """
    MainScreen {
        background: #1a1a1a;
    }

    #header {
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
        height: auto;
        padding: 0 1;
        background: #1a1a1a;
    }

    #confirm-slot {
        height: auto;
        margin: 0;
        padding: 0;
    }

    #btw-slot { height: auto; max-height: 9; color: #c8c2b8; background: #24211e; }
    #btw-slot Static { height: auto; padding: 0 1; }
    MainScreen.short #btw-slot { max-height: 4; }

    #completion-popup {
        height: 1;
        color: #a9a39a;
        background: #24211e;
        padding: 0 1;
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
        color: #a9a39a;
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
        color: #e8e4dc;
        margin: 1 0;
        text-style: bold;
        background: #262321;
        padding: 0 1;
    }

    .assistant-msg {
        color: #e8e4dc;
        margin: 0 0 1 0;
        padding-left: 1;
    }

    .tool-msg {
        color: #e2c08d;
        margin: 0 0;
    }

    .tool-result {
        color: #9a958c;
        margin: 0 0 1 1;
        padding-left: 1;
    }

    .tool-running {
        color: #e2c08d;
        margin: 0 0 0 1;
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
        max-height: 17;
        border: solid #e2c08d;
        background: #2a2418;
        padding: 0 1;
    }

    .confirm-preview {
        height: auto;
        max-height: 8;
        overflow-y: auto;
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
    MainScreen.narrow #chat { padding: 0 1; }
    MainScreen.short .confirm-preview { max-height: 3; }
    MainScreen.short .confirm-inline { max-height: 11; }
    #input-wrap:focus-within { border-top: solid #da7756; }
    MainScreen.awaiting #input-wrap { border-top: solid #e2c08d; }
    .tool-result:focus { border-left: solid #da7756; background: #24211e; }
    .tool-result { height: auto; max-height: 16; overflow-y: auto; }
    .tool-failed { color: #e06c75; border-left: solid #e06c75; }
    """

    def compose(self) -> ComposeResult:
        # 正常纵向布局：聊天占余量，底部操作区和状态行各占独立空间。
        yield ChatWidget()
        with Container(id="input-container"):
            yield Static("", id="completion-popup", markup=False)
            yield VerticalScroll(id="btw-slot")
            yield Container(id="confirm-slot")
            with Horizontal(id="input-wrap"):
                yield Static(">", id="input-prompt", markup=False)
                yield InputWidget()
            yield Static(
                "Enter 发送 · /help 帮助 · /sessions 历史 · Esc 停止",
                id="footer-hint",
                markup=False,
            )

        yield HeaderWidget()

    def on_mount(self) -> None:
        """Screen 挂载后通知 App 初始化 Agent"""
        self.set_class(self.app.size.width < 76, "narrow")
        self.set_class(self.app.size.height < 30, "short")
        self.app.init_agent()
        self.call_after_refresh(lambda: self.query_one("#input", InputWidget).focus())

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 76, "narrow")
        self.set_class(event.size.height < 30, "short")
        self.update_hints(getattr(self, "_display_status", "就绪"))

    def update_hints(self, status: str) -> None:
        self._display_status = status
        waiting = status == "等待确认"
        self.set_class(waiting, "awaiting")
        if waiting:
            hint = "Y 单次允许 · A 本会话允许 · N 拒绝 · Esc 停止"
        elif status == "运行中" or status.startswith("执行 "):
            hint = "Esc 停止 · 点击工具结果展开 · 可滚动查看历史"
        else:
            hint = "Enter 发送 · /help 帮助 · Ctrl+C 复制/停止"
        if self.has_class("narrow"):
            hint = "Y 允许 · A 会话 · N 拒绝 · Esc 停止" if waiting else "Esc 停止 · Ctrl+C 复制/停止 · /help"
        self.query_one("#footer-hint", Static).update(hint)
