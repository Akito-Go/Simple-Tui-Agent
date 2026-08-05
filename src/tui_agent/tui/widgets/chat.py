"""对话流组件"""

import re

from textual.widgets import Static
from textual.containers import VerticalScroll

STATUS_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
TOOL_SPINNER_FRAMES = STATUS_SPINNER_FRAMES


def _format_tool_args(arguments: dict, max_len: int = 80) -> str:
    """格式化工具参数，避免多行内容撑爆单行展示"""
    parts = []
    for key, value in arguments.items():
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        text = " ".join(text.split())
        if len(text) > max_len:
            text = text[:max_len] + "..."
        parts.append(f"{key}={text}")
    return ", ".join(parts)


def _normalize_display_text(text: str) -> str:
    """折叠连续空行并去除尾部空白，避免流式输出与工具调用之间出现大段空白"""
    collapsed = re.sub(r"\n{3,}", "\n\n", text)
    return collapsed.rstrip()


def _extract_assistant_body(text: str) -> str:
    if text.startswith("🤖 "):
        text = text[2:]
    for frame in STATUS_SPINNER_FRAMES:
        prefix = f"{frame} "
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


class ChatWidget(VerticalScroll):
    def __init__(self):
        super().__init__(id="chat")
        self._running_widget: Static | None = None
        self._running_tool_name: str | None = None
        self._running_tool_args: dict | None = None
        self._running_spinner_idx: int = 0
        self._streaming_widget: Static | None = None
        self._streaming_buffer: list[str] = []
        self._streaming_active: bool = False
        self._status_spinner_idx: int = 0
        self._last_assistant_widget: Static | None = None
        self._assistant_busy: bool = False

    def _static(self, text: str, *, classes: str = "") -> Static:
        """创建禁用 markup 的 Static，避免工具参数中的 [] 触发解析错误"""
        return Static(text, classes=classes, markup=False)

    def _set_text(self, widget: Static, text: str) -> None:
        widget.update(text)

    def on_mount(self) -> None:
        self.set_interval(0.1, self._tick_status_spinner)
        self.set_interval(0.1, self._tick_tool_spinner)

    def _format_assistant(self, body: str, *, busy: bool) -> str:
        body = _normalize_display_text(body)
        if busy:
            frame = STATUS_SPINNER_FRAMES[self._status_spinner_idx]
            if body:
                return f"🤖 {frame} {body}"
            return f"🤖 {frame} 思考中..."
        if body:
            return f"🤖 {body}"
        return "🤖"

    def _assistant_stream_text(self) -> str:
        return self._format_assistant("".join(self._streaming_buffer), busy=True)

    def _refresh_last_assistant_busy(self) -> None:
        if self._last_assistant_widget is None:
            return
        body = _extract_assistant_body(str(self._last_assistant_widget.content))
        self._set_text(
            self._last_assistant_widget,
            self._format_assistant(body, busy=self._assistant_busy),
        )

    def _tick_status_spinner(self) -> None:
        if not self._streaming_active and not self._assistant_busy:
            return
        self._status_spinner_idx = (self._status_spinner_idx + 1) % len(STATUS_SPINNER_FRAMES)
        if self._streaming_active and self._streaming_widget is not None:
            self._set_text(self._streaming_widget, self._assistant_stream_text())
        if self._assistant_busy:
            self._refresh_last_assistant_busy()

    def _tick_tool_spinner(self) -> None:
        if self._running_widget is None or self._running_tool_name is None:
            return
        self._running_spinner_idx = (self._running_spinner_idx + 1) % len(TOOL_SPINNER_FRAMES)
        frame = TOOL_SPINNER_FRAMES[self._running_spinner_idx]
        args_str = _format_tool_args(self._running_tool_args or {})
        self._set_text(
            self._running_widget,
            f"⚡ {self._running_tool_name}({args_str})   {frame} 执行中...",
        )

    def show_thinking(self) -> None:
        """在统一的助手行展示转圈等待态，首字到达后自动切换为流式输出"""
        self.start_streaming()

    def hide_thinking(self) -> None:
        """兼容旧调用：思考态已合并进流式助手行"""
        return

    def start_streaming(self) -> None:
        self._streaming_buffer = []
        self._streaming_active = True
        self._status_spinner_idx = 0
        if self._streaming_widget is not None:
            self._set_text(self._streaming_widget, self._assistant_stream_text())
        else:
            self._streaming_widget = self._static(self._assistant_stream_text(), classes="assistant-msg")
            self.mount(self._streaming_widget)
        self.scroll_end(animate=False)

    def append_streaming(self, text: str) -> None:
        self._streaming_buffer.append(text)
        if self._streaming_widget is not None:
            self._streaming_active = True
            self._set_text(self._streaming_widget, self._assistant_stream_text())
            self.scroll_end(animate=False)

    def finish_streaming(self) -> str:
        full_text = "".join(self._streaming_buffer)
        self._streaming_active = False
        content = _normalize_display_text(full_text)
        if self._streaming_widget is not None:
            widget = self._streaming_widget
            if content:
                self._set_text(widget, self._format_assistant(content, busy=False))
                self._last_assistant_widget = widget
            else:
                widget.remove()
            self._streaming_widget = None
        self._streaming_buffer = []
        return full_text

    def add_user_message(self, content: str) -> None:
        self.mount(self._static(f"👤 {content}", classes="user-msg"))
        self.scroll_end(animate=False)

    def add_assistant_message(self, content: str) -> None:
        self.finish_streaming()
        widget = self._static(self._format_assistant(content, busy=False), classes="assistant-msg")
        self.mount(widget)
        self._last_assistant_widget = widget
        self.scroll_end(animate=False)

    def show_tool_running(self, name: str, arguments: dict) -> None:
        if self._streaming_widget is not None:
            self.finish_streaming()
        self._assistant_busy = True
        self._refresh_last_assistant_busy()
        args_str = _format_tool_args(arguments)
        self._running_tool_name = name
        self._running_tool_args = arguments
        self._running_spinner_idx = 0
        frame = TOOL_SPINNER_FRAMES[0]
        self._running_widget = self._static(
            f"⚡ {name}({args_str})   {frame} 执行中...",
            classes="tool-running",
        )
        self.mount(self._running_widget)
        self.scroll_end(animate=False)

    def hide_tool_running(self) -> None:
        if self._running_widget is not None:
            self._running_widget.remove()
            self._running_widget = None
        self._running_tool_name = None
        self._running_tool_args = None

    def add_tool_result(self, name: str, arguments: dict, auto: bool, result: str, success: bool) -> None:
        self._assistant_busy = False
        self._refresh_last_assistant_busy()
        args_str = _format_tool_args(arguments)
        status = "✓" if (auto and success) else ("⚠" if not auto else "✗")
        lines = result.split("\n")
        summary = " ".join(lines[0].split())[:120]
        more = f" ({len(lines)} 行, {len(result)} 字符)" if len(lines) > 1 or len(result) > 120 else ""
        text = f"⚡ {name}({args_str}) {status} {summary}{more}"
        if self._running_widget is not None:
            self._set_text(self._running_widget, text)
            self._running_widget.remove_class("tool-running")
            self._running_widget.add_class("tool-result")
            self._running_widget = None
            self._running_tool_name = None
            self._running_tool_args = None
        else:
            self.mount(self._static(text, classes="tool-result"))
        self.scroll_end(animate=False)

    def add_permission_denied(self, name: str) -> None:
        self.mount(self._static(f"🚫 {name} — 用户已拒绝", classes="denied-msg"))
        self.scroll_end(animate=False)

    def add_error(self, message: str) -> None:
        self.finish_streaming()
        self.mount(self._static(f"❌ {message}", classes="error-msg"))
        self.scroll_end(animate=False)

    def add_system_message(self, content: str) -> None:
        self.mount(self._static(f"📢 {content}", classes="system-msg"))
        self.scroll_end(animate=False)

    def clear(self) -> None:
        self._running_widget = None
        self._running_tool_name = None
        self._running_tool_args = None
        self._streaming_widget = None
        self._streaming_buffer = []
        self._streaming_active = False
        self._last_assistant_widget = None
        self._assistant_busy = False
        for child in list(self.children):
            child.remove()

    def child_labels(self) -> list[str]:
        """返回子组件展示文本，供测试校验顺序"""
        return [str(child.content) for child in self.children if isinstance(child, Static)]
