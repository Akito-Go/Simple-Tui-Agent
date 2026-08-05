"""输入框组件 — 多行输入、命令识别"""

from textual.widgets import Input

INPUT_PLACEHOLDER = "> 输入消息，或 /help /sessions /model /provider /status /stop /clear /exit"
INPUT_PLACEHOLDER_CONFIRM = "> 等待确认：↑↓+Enter · Y 同意 · A 本会话全允 · N 拒绝"


class InputWidget(Input):
    """底部输入框"""

    def __init__(self):
        super().__init__(
            placeholder=INPUT_PLACEHOLDER,
            id="input",
        )
