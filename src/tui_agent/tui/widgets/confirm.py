"""权限确认组件 — 内联在对话流中，键盘 ↑↓ 选择"""

from textual.widgets import Static
from textual.containers import Vertical


class ConfirmWidget(Vertical, can_focus=True):
    """内联权限确认 — 直接嵌入对话流，不改变布局"""

    OPTIONS = [
        ("  ✅ 确认执行", "confirm"),
        ("  ✅ 本次会话全部允许", "allow_session"),
        ("  ❌ 拒绝执行", "deny"),
    ]

    def __init__(self, tool_name: str, summary: str):
        super().__init__(classes="confirm-inline")
        self._selected_idx: int = 0
        self._tool_name = tool_name
        self._summary = summary
        self._option_widgets: list[Static] = []

    def on_mount(self) -> None:
        self.mount(Static(
            f"⚡ {self._tool_name}   ⚠ 需确认\n"
            f"   {self._summary}",
            classes="permission-msg",
        ))
        self.mount(Static(
            "   ↑↓ 选择 · Enter 确认 · Y 同意 · A 本会话全允 · N 拒绝",
            classes="confirm-hint",
        ))
        for i, (label, _) in enumerate(self.OPTIONS):
            prefix = "▶" if i == self._selected_idx else " "
            w = Static(f"{prefix}{label}")
            self._option_widgets.append(w)
            self.mount(w)
        self.focus()

    def _refresh_options(self) -> None:
        for i, (label, _) in enumerate(self.OPTIONS):
            prefix = "▶" if i == self._selected_idx else " "
            self._option_widgets[i].update(f"{prefix}{label}")

    def _submit(self, action: str) -> None:
        if action == "allow_session":
            self.app.on_confirm(True, allow_session=True)
        elif action == "confirm":
            self.app.on_confirm(True, allow_session=False)
        else:
            self.app.on_confirm(False, allow_session=False)

    def key_up(self) -> None:
        self._selected_idx = (self._selected_idx - 1) % len(self.OPTIONS)
        self._refresh_options()

    def key_down(self) -> None:
        self._selected_idx = (self._selected_idx + 1) % len(self.OPTIONS)
        self._refresh_options()

    def key_enter(self) -> None:
        self._submit(self.OPTIONS[self._selected_idx][1])

    def key_y(self) -> None:
        self._submit("confirm")

    def key_a(self) -> None:
        self._submit("allow_session")

    def key_n(self) -> None:
        self._submit("deny")
