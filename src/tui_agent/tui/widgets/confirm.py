"""权限确认组件 — Claude Code 双线框 + 中文选项"""

from textual.widgets import Static
from textual.containers import Vertical


class ConfirmWidget(Vertical, can_focus=True):
    """内联权限确认 — 双线边框强调安全决策"""

    OPTIONS = [
        ("确认执行", "confirm"),
        ("本次会话全部允许", "allow_session"),
        ("拒绝执行", "deny"),
    ]

    def __init__(self, tool_name: str, summary: str):
        super().__init__(classes="confirm-inline")
        self._selected_idx: int = 0
        self._tool_name = tool_name
        self._summary = summary
        self._option_widgets: list[Static] = []

    def on_mount(self) -> None:
        self.mount(Static(
            f"⚠ 需要确认\n"
            f" {self._tool_name}\n"
            f" {self._summary}",
            classes="permission-msg",
            markup=False,
        ))
        self.mount(Static(
            " ↑↓ 选择 · Enter 确认 · Y 同意 · A 本会话全允 · N 拒绝",
            classes="confirm-hint",
        ))
        for i, (label, _) in enumerate(self.OPTIONS):
            w = Static(label, markup=False)
            self._option_widgets.append(w)
            self.mount(w)
        self._refresh_options()
        self.focus()

    def _refresh_options(self) -> None:
        for i, (label, _) in enumerate(self.OPTIONS):
            widget = self._option_widgets[i]
            widget.remove_class("confirm-option")
            widget.remove_class("confirm-option-selected")
            n = i + 1
            if i == self._selected_idx:
                widget.add_class("confirm-option-selected")
                widget.update(f" ❯ {n}. {label}")
            else:
                widget.add_class("confirm-option")
                widget.update(f"   {n}. {label}")

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

    def key_1(self) -> None:
        self._submit("confirm")

    def key_2(self) -> None:
        self._submit("allow_session")

    def key_3(self) -> None:
        self._submit("deny")
