"""差异着色与长内容折叠，文件文本不解析为 markup。"""

from rich.text import Text
from textual.widgets import Static


def color_diff(content: str) -> Text:
    text = Text()
    for line in content.splitlines(keepends=True):
        style = ""
        if line.startswith(("--- ", "+++ ")):
            style = "bold #c8c2b8"
        elif line.startswith("@@"):
            style = "#79b8ff"
        elif line.startswith("+"):
            style = "#7ee787"
        elif line.startswith("-"):
            style = "#e06c75"
        text.append(line, style=style)
    return text


class DiffWidget(Static, can_focus=True):
    BINDINGS = [("enter,space", "toggle", "展开 / 收起差异")]
    DEFAULT_CSS = """
    DiffWidget { height: auto; margin: 0 0 1 1; }
    DiffWidget:focus { background: #222222; }
    """

    def __init__(self, title: str, diff: str):
        super().__init__(markup=False)
        self._title = title
        self._diff = diff
        self._expanded = len(diff.splitlines()) <= 16
        self._refresh_diff()

    def _refresh_diff(self) -> None:
        text = Text(self._title + "\n", style="bold #c8c2b8")
        text.append(f"{'▾' if self._expanded else '▸'} {'收起' if self._expanded else '展开'}差异 · 点击 / Enter\n", style="dim")
        if self._expanded:
            text.append(color_diff(self._diff))
        self.update(text)

    def action_toggle(self) -> None:
        self._expanded = not self._expanded
        self._refresh_diff()

    def on_click(self) -> None:
        self.action_toggle()
