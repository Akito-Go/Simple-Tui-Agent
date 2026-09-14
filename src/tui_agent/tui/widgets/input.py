"""输入框组件 — Claude Code 式单行 > 提示"""

from textual.widgets import Input, Static
from textual import on, events

# `>` 由界面左侧 Static 绘制；保留淡色占位，避免空输入区「看不见」
INPUT_PLACEHOLDER = "输入消息，或 /help"
INPUT_PLACEHOLDER_CONFIRM = "等待确认：↑↓+Enter · Y/A/N"


class InputWidget(Input):
    """底部输入框（外层细线 + 左侧 >）"""

    def __init__(self):
        super().__init__(
            placeholder=INPUT_PLACEHOLDER,
            id="input",
        )

    def on_mount(self) -> None:
        self.call_after_refresh(self.focus)

    def key_tab(self) -> None:
        """循环补全内置命令、工具或模型名称。"""
        app = self.app
        candidates = list(app.completion_candidates())
        prefix = self.value.rsplit(" ", 1)[-1]
        if not prefix:
            self.focus()
            return
        matches = sorted(item for item in candidates if item.startswith(prefix))
        if matches:
            self.value = self.value[: -len(prefix)] + matches[0]
            self.cursor_position = len(self.value)
        self.focus()
        self._show_candidates(matches)

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self.key_tab()
            return
        await super()._on_key(event)

    @on(Input.Changed)
    def _input_changed(self, event: Input.Changed) -> None:
        if event.input is self:
            self._show_candidates(self._matching_candidates())

    def _matching_candidates(self) -> list[str]:
        prefix = self.value.rsplit(" ", 1)[-1]
        if not prefix:
            return []
        return [item for item in self.app.completion_candidates() if item.startswith(prefix)]

    def _show_candidates(self, matches: list[str]) -> None:
        try:
            popup = self.screen.query_one("#completion-popup", Static)
        except Exception:
            return
        popup.update("  " + "  ·  ".join(matches[:8]) if matches else "")
        popup.display = bool(self.value and matches and (self.value.startswith("/") or " " not in self.value))
