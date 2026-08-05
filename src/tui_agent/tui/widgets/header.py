"""Header 组件 — 模型名、轮次、运行状态"""

from textual.widgets import Static


class HeaderWidget(Static):
    """顶部状态栏"""

    def __init__(self):
        super().__init__("", id="header")

    def update_status(self, model: str, turn: int, max_turns: int, status: str = "🟢 等待输入") -> None:
        """更新状态栏"""
        self.update(
            f" TUI Agent · {model} · turn {turn}/{max_turns}   {status}"
        )
