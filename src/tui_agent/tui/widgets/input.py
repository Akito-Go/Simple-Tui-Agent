"""输入框组件 — Claude Code 式单行 > 提示"""

from textual.widgets import Input

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
