"""输入框组件 — 多行输入、命令识别"""

from textual.widgets import Input

INPUT_PLACEHOLDER = "输入消息或命令 (/help /clear /stop /model /status /exit)..."
INPUT_PLACEHOLDER_CONFIRM = "等待工具确认：↑↓ + Enter，或按 Y/N"


class InputWidget(Input):
    """底部输入框"""

    def __init__(self):
        super().__init__(
            placeholder=INPUT_PLACEHOLDER,
            id="input",
        )
