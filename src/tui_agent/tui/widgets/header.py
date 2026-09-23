"""自适应底部状态行，优先显示当前状态。"""

from rich.text import Text
from textual.widgets import Static


class HeaderWidget(Static):
    def __init__(self):
        super().__init__("就绪 · Douhua", id="header", markup=False)
        self._details = None

    def update_status(self, model: str, turn: int, max_turns: int,
                      status: str = "就绪", provider: str | None = None) -> None:
        clean = status
        for icon in ("🟢 ", "🟡 ", "🔴 ", "⏳ "):
            clean = clean.replace(icon, "")
        self._details = (clean, model, turn, max_turns, provider)
        self._refresh_status()

    def on_resize(self) -> None:
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self._details is None:
            return
        status, model, turn, maximum, provider = self._details
        color = "#e2c08d" if status == "等待确认" else "#7ee787" if status == "就绪" else "#da7756"
        text = Text(f"● {status}", style=color)
        text.append(f"  ·  {model}", style="#e8e4dc")
        if self.size.width >= 60:
            text.append(f"  ·  {turn}/{maximum} 轮", style="#a9a39a")
        if provider and self.size.width >= 95:
            text.append(f"  ·  {provider}", style="#a9a39a")
        text.truncate(max(1, self.content_size.width), overflow="ellipsis")
        self.update(text)
