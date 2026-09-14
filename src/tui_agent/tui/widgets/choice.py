"""命令共用的键盘选择菜单。"""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static


class ChoiceScreen(ModalScreen[int | None]):
    DEFAULT_CSS = """
    ChoiceScreen { align: center middle; background: #000000 45%; }
    #choice-panel { width: 85%; max-width: 100; height: auto; max-height: 85%;
        background: #24211e; border: solid #da7756; padding: 0 1; }
    #choice-title { height: auto; color: #da7756; text-style: bold; }
    #choice-options { height: auto; max-height: 12; border: none; background: #24211e; }
    #choice-hint { height: auto; color: #a9a39a; }
    """

    def __init__(self, title: str, labels: list[str], selected: int = 0):
        super().__init__()
        self._title = title
        self._labels = labels
        self._selected = selected

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-panel"):
            yield Static(self._title, id="choice-title", markup=False)
            yield OptionList(*(Text(label) for label in self._labels), id="choice-options")
            yield Static("↑↓ 选择 · Enter 确认 · Esc 取消 · Ctrl+C 复制/停止", id="choice-hint", markup=False)

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.highlighted = self._selected
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option_index)
