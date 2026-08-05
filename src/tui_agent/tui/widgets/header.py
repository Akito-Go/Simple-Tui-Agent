"""底部状态行 — Claude Code 布局 + 中文状态"""

from textual.widgets import Static


class HeaderWidget(Static):
    """底部状态行：model / turn / status"""

    def __init__(self):
        super().__init__(" tui-agent", id="header")

    def update_status(
        self,
        model: str,
        turn: int,
        max_turns: int,
        status: str = "就绪",
        provider: str | None = None,
    ) -> None:
        """更新状态栏"""
        parts = ["tui-agent"]
        if provider:
            parts.append(provider)
        parts.append(model)
        parts.append(f"轮次 {turn}/{max_turns}")
        clean = (
            status.replace("🟢 ", "")
            .replace("🟡 ", "")
            .replace("🔴 ", "")
            .replace("⏳ ", "")
        )
        self.update(f" {' · '.join(parts)}    {clean}")
