"""启动欢迎页 — 对齐 Claude Code 橙框左右分栏 + Douhua 小猫徽标"""

from __future__ import annotations

from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.widgets import Static

# 终端半块像素：尖耳、弯弯笑眼、收拢前爪和右侧卷尾。
# 固定画布宽度，避免逐行居中时将头部和身体错开一列。
WELCOME_ICON = "\n".join(
    row.ljust(23) for row in
    [
        "    ▄▄        ▄▄       ",
        "    ███▄    ▄███       ",
        "    ████████████       ",
        "    █▀▄▀████▀▄▀█       ",
        "    █████▀▀█████       ",
        "   ▄████████████▄      ",
        "   ██████████████      ",
        "  ▄████ ▀██▀ ████▄█▀█  ",
        "  █████  ██  █████▀▄█  ",
        "  █████  ██  █████  █  ",
        "   ▀███▄▄██▄▄███▀▄▄█▀  ",
        "     ▀▀▀▀▀▀▀▀▀▀▀▀▀▀    ",
    ]
)
BRAND_WORDMARK = "Douhua"

WELCOME_TIPS: tuple[str, ...] = (
    "只读工具会自动执行；写入与 Shell 会先征求你的确认。",
    "权限确认时按 A，可在本会话跳过后续确认（黑名单仍生效）。",
    "用 /model 切换模型，用 /provider 在 OpenAI 兼容与 Anthropic 间切换。",
    "任务跑偏时按 Esc 或输入 /stop，可立刻中止当前 Agent 循环。",
    "用 /status 查看轮次、估算 tokens 与本会话权限状态。",
    "Shell 高危命令（如 rm -rf /、curl|sh）会被安全策略直接拦截。",
    "直接描述目标即可，例如：帮我梳理这个项目的目录结构。",
    "输入 /help 可查看全部命令与可用工具列表。",
    "用 /sessions 列出历史会话，或 /sessions <序号> 直接恢复。",
)


def get_app_version() -> str:
    """读取已安装包版本；开发态回退到默认版本号。"""
    try:
        return version("tui-agent")
    except PackageNotFoundError:
        return "0.2.1"


def pick_tip_index(*, seed: str | None = None) -> int:
    """按日期 + 可选 seed 选择起始 tip，同日相对稳定、跨日轮换。"""
    base = date.today().toordinal()
    if seed:
        base += sum(ord(c) for c in seed)
    return base % len(WELCOME_TIPS)


def _short_cwd(cwd: Path | str | None) -> str:
    workdir = Path(cwd or Path.cwd()).resolve()
    home = Path.home().resolve()
    try:
        return f"~/{workdir.relative_to(home)}"
    except ValueError:
        return str(workdir)


def _format_recent_activity(sessions: list[dict[str, Any]] | None) -> str:
    if not sessions:
        return "暂无最近活动"
    lines: list[str] = []
    for i, s in enumerate(sessions[:3], 1):
        preview = (s.get("preview") or "").strip()
        preview = f"「{preview[:24]}」" if preview else ""
        lines.append(
            f"{i}. {s.get('last_active', '?')} · {s.get('model', '?')} {preview}"
        )
    return "\n".join(lines)


def build_welcome_banner(
    *,
    provider: str,
    model: str,
    cwd: Path | str | None = None,
    max_turns: int | None = None,
    context_max_tokens: int | None = None,
    tip_index: int | None = None,
    app_version: str | None = None,
    recent_sessions: list[dict[str, Any]] | None = None,
) -> str:
    """纯文本版欢迎页（测试/降级用）；正式 UI 使用 WelcomeWidget 左右分栏。"""
    display_cwd = _short_cwd(cwd)
    ver = app_version or get_app_version()
    idx = pick_tip_index(seed=display_cwd) if tip_index is None else tip_index % len(WELCOME_TIPS)
    tip = WELCOME_TIPS[idx]
    recent = _format_recent_activity(recent_sessions)

    left = [
        WELCOME_ICON,
        f"{BRAND_WORDMARK} · tui-agent v{ver}",
        f"{provider} · {model}",
        display_cwd,
    ]
    if max_turns is not None:
        left.append(f"最大轮次 {max_turns}")
    if context_max_tokens is not None:
        left.append(f"上下文 ~{context_max_tokens} tokens")

    right = [
        "入门提示",
        tip,
        "────────",
        "最近活动",
        recent,
    ]
    left_w = max(len(line) for line in left)
    rows = max(len(left), len(right))
    out = [f" tui-agent v{ver} ".center(left_w + 28, "─")]
    for i in range(rows):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        out.append(f"{l:<{left_w}}  │  {r}")
    return "\n".join(out)


class WelcomeWidget(Vertical):
    """Claude Code 风格：橙线方框 + 顶栏标题 + 左徽标 / 右 Tips+活动。"""

    DEFAULT_CSS = """
    WelcomeWidget {
        height: auto;
        margin: 0 0 1 0;
        border: solid #da7756;
        background: #1a1a1a;
        padding: 0 1;
    }

    #welcome-body {
        height: auto;
        layout: horizontal;
    }

    #welcome-left {
        width: 3fr;
        height: auto;
        min-height: 0;
        padding: 0 2 0 1;
        border-right: solid #da7756;
        content-align: center middle;
    }

    #welcome-right {
        width: 2fr;
        height: auto;
        padding: 0 1 0 2;
    }

    #welcome-right-top {
        height: auto;
        padding: 0 0 1 0;
        border-bottom: solid #da7756;
        margin: 0 0 1 0;
    }

    #welcome-right-bottom {
        height: auto;
    }

    .welcome-logo-container {
        height: auto;
    }

    .welcome-logo {
        width: 23;
        color: #da7756;
        text-align: left;
        text-style: bold;
        margin: 0 0 1 0;
    }

    .welcome-links {
        color: #8a857c;
        text-align: center;
        margin: 0 0 0 0;
    }

    .welcome-path {
        color: #8a857c;
        text-align: center;
        margin: 0;
    }

    .welcome-section-title {
        color: #da7756;
        text-style: bold;
        margin: 0 0 1 0;
    }

    WelcomeWidget.compact { padding: 0 1; }
    WelcomeWidget.dismissed { border: none; padding: 0; margin: 0 0 1 0; }
    WelcomeWidget.dismissed #welcome-body { display: none; }
    .welcome-summary { height: 1; color: #8a857c; }
    WelcomeWidget.compact #welcome-body { layout: vertical; }
    WelcomeWidget.compact #welcome-left {
        width: 1fr; min-height: 0; padding: 0; border-right: none;
    }
    WelcomeWidget.compact #welcome-right { width: 1fr; padding: 1 0 0 0; }
    WelcomeWidget.compact .welcome-logo { display: none; }
    WelcomeWidget.compact .welcome-path { margin: 0; }
    WelcomeWidget.compact #welcome-right-top { padding: 0; margin: 0; border-bottom: none; }
    WelcomeWidget.compact .welcome-section-title { margin: 0; }
    .welcome-section-body {
        color: #c8c2b8;
        height: auto;
    }
    """

    def on_resize(self) -> None:
        # 使用稳定的终端宽度，避免滚动条出现/消失导致布局反复切换。
        self.set_class(self.screen.size.width < 84, "compact")

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        cwd: Path | str | None = None,
        max_turns: int | None = None,
        context_max_tokens: int | None = None,
        recent_sessions: list[dict[str, Any]] | None = None,
        rotate_seconds: float = 5.0,
    ):
        super().__init__(classes="welcome-panel")
        self._provider = provider
        self._model = model
        self._cwd = cwd
        self._max_turns = max_turns
        self._context_max_tokens = context_max_tokens
        self._recent_sessions = recent_sessions or []
        self._rotate_seconds = rotate_seconds
        self._tip_index = pick_tip_index(seed=_short_cwd(cwd))
        self._version = get_app_version()
        # 对齐参考图：品牌 + 版本嵌在顶边左侧
        self.border_title = f"{BRAND_WORDMARK} · tui-agent v{self._version}"

    def compose(self) -> ComposeResult:
        display_cwd = _short_cwd(self._cwd)
        link_bits = [self._model, self._provider]
        if self._max_turns is not None:
            link_bits.append(f"轮次≤{self._max_turns}")

        with Horizontal(id="welcome-body"):
            with Vertical(id="welcome-left"):
                with Center(classes="welcome-logo-container"):
                    yield Static(WELCOME_ICON, classes="welcome-logo", markup=False)
                yield Static(
                    " · ".join(link_bits),
                    classes="welcome-links",
                    markup=False,
                )
                yield Static(display_cwd, classes="welcome-path", markup=False)

            with Vertical(id="welcome-right"):
                with Vertical(id="welcome-right-top"):
                    yield Static("入门提示", classes="welcome-section-title", markup=False)
                    yield Static(
                        WELCOME_TIPS[self._tip_index],
                        id="welcome-tip",
                        classes="welcome-section-body",
                        markup=False,
                    )
                with Vertical(id="welcome-right-bottom"):
                    yield Static("最近活动", classes="welcome-section-title", markup=False)
                    yield Static(
                        _format_recent_activity(self._recent_sessions),
                        id="welcome-recent",
                        classes="welcome-section-body",
                        markup=False,
                    )

    def on_mount(self) -> None:
        self.set_class(self.screen.size.width < 84, "compact")
        if self._rotate_seconds > 0 and len(WELCOME_TIPS) > 1:
            self.set_interval(self._rotate_seconds, self._rotate_tip)

    def _rotate_tip(self) -> None:
        self._tip_index = (self._tip_index + 1) % len(WELCOME_TIPS)
        tip = self.query_one("#welcome-tip", Static)
        tip.update(WELCOME_TIPS[self._tip_index])

    def collapse(self) -> None:
        if self.has_class("dismissed"):
            return
        self.add_class("dismissed")
        self.border_title = ""
        self.mount(Static(f"{BRAND_WORDMARK} · {self._model} · {_short_cwd(self._cwd)}", classes="welcome-summary", markup=False))
