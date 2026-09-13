"""Textual App 主类 — 事件绑定、Agent Loop 集成"""

import asyncio
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Input

from .screens import MainScreen
from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget, INPUT_PLACEHOLDER, INPUT_PLACEHOLDER_CONFIRM
from .widgets.confirm import ConfirmWidget
from .welcome import WelcomeWidget
from .commands import parse_command, Command

from ..agent.loop import AgentLoop
from ..agent.types import (
    TextDelta,
    ToolCallStart,
    ToolCallResult,
    PermissionRequest,
    PermissionDenied,
    AgentFinished,
    AgentError,
)
from ..config.loader import load_config, get_api_key
from ..config.schema import AppConfig
from ..llm.factory import (
    apply_provider_defaults,
    create_llm_provider,
    infer_provider_for_model,
    normalize_provider_name,
)
from ..tools.builtin import create_default_registry
from ..tools.workspace import set_workspace_root
from ..permissions.guard import PermissionGuard
from ..session.manager import SessionManager
from ..logging.logger import setup_logging, get_logger

logger = get_logger(__name__)


class TuiAgentApp(App):
    """STA 主应用"""

    TITLE = "STA"

    # Esc 全局优先：运行中 / 等待确认时均可中断（与 /stop 相同）
    BINDINGS = [
        Binding("escape", "stop_agent", "Stop", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.config: AppConfig | None = None
        self.agent_loop: AgentLoop | None = None
        self.session: SessionManager | None = None
        self._waiting_confirmation: bool = False
        self._agent_running: bool = False
        self._stop_requested: bool = False
        self._agent_task: asyncio.Task | None = None
        self._welcome_shown: bool = False

    def action_stop_agent(self) -> None:
        """Esc 快捷键：终止当前 Agent / 取消待确认操作"""
        self._handle_command(Command.STOP, "")

    def _update_header(self, status: str = "就绪") -> None:
        """刷新底部状态行（含 provider）"""
        if self.config is None:
            return
        try:
            header = self.screen.query_one("#header", HeaderWidget)
        except Exception:
            return
        self.screen.update_hints(status)
        turn = self.agent_loop.state.turn_count if self.agent_loop else 0
        header.update_status(
            model=self.config.llm.model,
            turn=turn,
            max_turns=self.config.max_turns,
            status=status,
            provider=normalize_provider_name(self.config.llm.provider),
        )

    def _show_welcome(
        self,
        chat: ChatWidget,
        *,
        recent_sessions: list | None = None,
    ) -> None:
        """展示 Claude Code 式左右分栏欢迎页（同一次启动只显示一次）"""
        if self._welcome_shown or self.config is None:
            return
        chat.mount_welcome(
            WelcomeWidget(
                provider=normalize_provider_name(self.config.llm.provider),
                model=self.config.llm.model,
                cwd=Path.cwd(),
                max_turns=self.config.max_turns,
                context_max_tokens=self.config.context_max_tokens,
                recent_sessions=recent_sessions,
                rotate_seconds=5.0,
            )
        )
        self._welcome_shown = True

    def on_mount(self) -> None:
        """应用挂载后初始化"""
        setup_logging()
        logger.info("TUI Agent 启动")

        # 先 push MainScreen，初始化在 screen 的 on_mount 中完成
        self.push_screen(MainScreen())

    def init_agent(self) -> None:
        """初始化 Agent（在 MainScreen 挂载后调用）"""
        screen = self.screen
        try:
            self.config = load_config()
            api_key = get_api_key(self.config.llm.provider)
            # 启动始终进入新会话；历史恢复请用 /sessions
            from ..session.loader import list_sessions

            self._do_init_agent(api_key, recent_sessions=list_sessions())

        except ValueError as e:
            chat = screen.query_one("#chat", ChatWidget)
            chat.add_error(f"配置错误: {e}")
            logger.error(f"启动失败: {e}")

    def _do_init_agent(
        self,
        api_key: str,
        session: SessionManager | None = None,
        *,
        recent_sessions: list | None = None,
        show_welcome: bool = True,
    ) -> None:
        """执行 Agent 初始化"""
        set_workspace_root(Path.cwd().resolve())
        screen = self.screen
        provider = create_llm_provider(self.config.llm, api_key)
        registry = create_default_registry()

        if session is not None:
            self.session = session
            self.session.set_model(self.config.llm.model)
        else:
            self.session = SessionManager(model=self.config.llm.model)

        guard = PermissionGuard()
        self.agent_loop = AgentLoop(
            llm_provider=provider,
            tool_registry=registry,
            permission_guard=guard,
            session=self.session,
            max_turns=self.config.max_turns,
            context_max_tokens=self.config.context_max_tokens,
        )

        self._update_header()

        logger.info(f"Agent 初始化完成, model={self.config.llm.model}")
        chat = screen.query_one("#chat", ChatWidget)
        if show_welcome:
            from ..session.loader import list_sessions

            self._welcome_shown = False
            self._show_welcome(
                chat,
                recent_sessions=recent_sessions
                if recent_sessions is not None
                else list_sessions(),
            )
        if session is not None:
            chat.add_system_message(
                f"已恢复会话 {session.session_id} · "
                f"provider={normalize_provider_name(self.config.llm.provider)} · "
                f"model={self.config.llm.model}"
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理用户输入"""
        if not event.value.strip():
            return

        text = event.value.strip()

        # 会话选择模式
        if getattr(self, "_selecting_session", False):
            cmd_result = parse_command(text)
            if cmd_result.is_command:
                self._handle_command(cmd_result.command, cmd_result.args)
            else:
                self._handle_session_selection(text)
            event.input.value = ""
            return

        # /stop 优先于所有拦截（运行中/等待确认态均可执行）
        cmd_result = parse_command(text)
        if cmd_result.is_command and cmd_result.command == Command.STOP:
            self._handle_command(Command.STOP, cmd_result.args)
            event.input.value = ""
            return

        if self._waiting_confirmation:
            screen = self.screen
            chat = screen.query_one("#chat", ChatWidget)
            chat.add_system_message("请使用 ↑↓ + Enter 或 Y/N 确认/拒绝待执行的工具")
            event.input.value = ""
            return

        if self._agent_running:
            screen = self.screen
            chat = screen.query_one("#chat", ChatWidget)
            chat.add_system_message("Agent 正在运行，请等待当前任务完成")
            event.input.value = ""
            return

        screen = self.screen
        input_widget = screen.query_one("#input", InputWidget)
        input_widget.clear()

        # 检查是否为内置命令
        if cmd_result.is_command:
            self._handle_command(cmd_result.command, cmd_result.args)
            return

        # 正常对话
        self._run_agent(text)

    def _handle_session_selection(self, text: str) -> None:
        """处理 /sessions 触发的会话选择输入"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        sessions = getattr(self, "_pending_sessions", [])

        if text.upper() in ("N", "NEW", "C", "CANCEL", "取消"):
            self._selecting_session = False
            self._pending_sessions = []
            chat.add_system_message("已取消会话恢复")
            self._update_header(status="就绪")
            return

        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(sessions):
                self._resume_session_at(idx)
                return
            chat.add_system_message(
                f"无效序号，请输入 1-{min(len(sessions), 9)}，或 N 取消"
            )
            return

        chat.add_system_message(
            f"请输入序号 1-{min(len(sessions), 9)} 恢复会话，或 N 取消"
        )

    def _list_sessions_for_resume(self) -> None:
        """列出可恢复会话并进入选择模式"""
        from ..session.loader import list_sessions

        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        sessions = list_sessions()
        if not sessions:
            chat.add_system_message("暂无历史会话可恢复")
            return

        self._selecting_session = True
        self._pending_sessions = sessions
        lines = [
            "📂 历史会话（输入序号恢复，N 取消）",
        ]
        for i, s in enumerate(sessions[:9], 1):
            preview = s.get("preview", "")
            preview_part = f"  「{preview}」" if preview else ""
            lines.append(
                f"  {i}. {s['last_active']} · {s['model']} · "
                f"轮次 {s['turn_count']} · {s['msg_count']} 条消息{preview_part}"
            )
        lines.append("  N. 取消")
        chat.add_system_message("\n".join(lines))
        self._update_header(status="选择会话")

    def _resume_session_at(self, idx: int) -> None:
        """按列表序号恢复会话"""
        from ..session.loader import list_sessions, load_session

        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        sessions = getattr(self, "_pending_sessions", None) or list_sessions()
        if not (0 <= idx < len(sessions)):
            chat.add_system_message("无效的会话序号")
            return

        session = load_session(sessions[idx]["filepath"], model=self.config.llm.model)
        if session is None:
            chat.add_system_message("会话加载失败")
            return

        self._selecting_session = False
        self._pending_sessions = []
        chat.clear()
        self._do_init_agent(
            get_api_key(self.config.llm.provider),
            session=session,
            recent_sessions=list_sessions(),
            show_welcome=True,
        )

    def _handle_command(self, command: Command, args: str) -> None:
        """处理内置命令"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        header = screen.query_one("#header", HeaderWidget)

        if command == Command.HELP:
            help_text = """
📋 内置命令:
  /help     - 显示此帮助信息
  /clear    - 清空当前会话
  /sessions - 列出/恢复历史会话
  /sessions <序号> - 直接恢复指定会话
  /stop     - 停止当前 Agent 运行（快捷键 Esc）
  /model    - 列出可用模型
  /model <序号|名称> - 切换模型（跨 Provider 会重建客户端）
  /provider - 查看/切换 LLM Provider（openai_compat / anthropic）
  /status   - 查看运行状态
  /exit     - 退出程序

🛠 可用工具:
  list_dir    - 列出目录内容
  read_file   - 读取文件（支持行范围）
  glob_search - Glob 模式匹配文件
  grep_search - 内容搜索
  write_file  - 写入文件 (需确认)
  edit_file   - 编辑文件 (需确认)
  shell_exec  - 执行非交互命令 (需确认)

权限确认时可选择「本次会话全部允许」。
"""
            chat.add_system_message(help_text)

        elif command == Command.CLEAR:
            if getattr(self, "_selecting_session", False):
                self._selecting_session = False
                self._pending_sessions = []
            if self.session:
                self.session.clear()
            if self.agent_loop is not None:
                self.agent_loop.permission_guard.reset_session_allow_all()
                state = getattr(self.agent_loop.tool_registry, "file_state", None)
                if state is not None:
                    state.clear()
            chat.clear()
            from ..session.loader import list_sessions

            self._welcome_shown = False
            self._show_welcome(chat, recent_sessions=list_sessions())
            chat.add_system_message("会话已清空")
            self._update_header(status="就绪")
            logger.info("会话已清空")

        elif command == Command.SESSIONS:
            if self._agent_running or self._waiting_confirmation:
                chat.add_system_message("请先等待当前任务结束，或使用 /stop")
                return
            args = (args or "").strip()
            if not args:
                self._list_sessions_for_resume()
            elif args.isdigit():
                from ..session.loader import list_sessions

                sessions = list_sessions()
                self._pending_sessions = sessions
                idx = int(args) - 1
                if sessions and 0 <= idx < len(sessions):
                    self._resume_session_at(idx)
                else:
                    chat.add_system_message(
                        f"无效序号，请输入 1-{min(len(sessions), 9)}（当前共 {len(sessions)} 个）"
                        if sessions
                        else "暂无历史会话可恢复"
                    )
            else:
                chat.add_system_message("用法: /sessions  或  /sessions <序号>")

        elif command == Command.MODEL:
            self._handle_model_command(chat, header, args)

        elif command == Command.PROVIDER:
            self._handle_provider_command(chat, header, args)

        elif command == Command.STATUS:
            if self.config and self.session:
                allow_all = (
                    self.agent_loop.permission_guard.session_allow_all
                    if self.agent_loop is not None
                    else False
                )
                est = self.session.token_usage.prompt_tokens
                status_text = f"""
📊 运行状态:
  Provider: {self.config.llm.provider}
  模型: {self.config.llm.model}
  当前任务轮次: {self.agent_loop.state.turn_count if self.agent_loop else 0}/{self.config.max_turns}
  会话累计轮次: {self.session.turn_count}
  API: {self.config.llm.api_base}
  超时: {self.config.llm.timeout}s
  重试: {self.config.llm.max_retries}次
  估算 tokens: {est}
  本会话全允: {"是" if allow_all else "否"}
"""
                chat.add_system_message(status_text)
            elif self.config:
                status_text = f"""
📊 配置状态（尚未选择会话）:
  Provider: {self.config.llm.provider}
  模型: {self.config.llm.model}
  API: {self.config.llm.api_base}
  超时: {self.config.llm.timeout}s
  重试: {self.config.llm.max_retries}次
  最大轮次: {self.config.max_turns}
"""
                chat.add_system_message(status_text)
            else:
                chat.add_system_message("Agent 未初始化")

        elif command == Command.STOP:
            if self._waiting_confirmation:
                # 等待确认态：移除 ConfirmWidget，拒绝操作，终止
                try:
                    confirm = screen.query_one(".confirm-inline")
                    confirm.remove()
                except Exception:
                    pass
                self._waiting_confirmation = False
                self._set_input_mode(waiting_confirm=False)
                if self.agent_loop is not None:
                    self.agent_loop.stop()
                if self._agent_task is not None and not self._agent_task.done():
                    self._agent_task.cancel()
                self._agent_task = None
                self._agent_running = False
                self._stop_requested = False
                chat.add_system_message("⏹ 已终止等待确认的任务")
                self._update_header(status="就绪")
            elif self._agent_running:
                # cancel 会在 _process_events 中以 CancelledError 收尾并复位 UI
                self._stop_requested = True
                if self._agent_task is not None and not self._agent_task.done():
                    self._agent_task.cancel()
                else:
                    # 任务已结束但标志未清：直接收尾，避免一直卡在「正在终止」
                    self._finalize_stopped(chat)
                    return
                chat.add_system_message("⏹ 正在终止当前任务...")
            else:
                chat.add_system_message("当前没有正在运行的任务")

        elif command == Command.EXIT:
            chat.add_system_message("正在退出...")
            if self.session:
                from ..session.storage import save_session

                save_session(self.session)
            self.exit()

    def _rebuild_llm_provider(self, candidate) -> None:
        """候选客户端构建成功后再一次性提交配置。"""
        if self.config is None or self.agent_loop is None:
            raise ValueError("Agent 未初始化")
        if self._agent_running or self._waiting_confirmation:
            raise ValueError("请先等待当前任务结束，或使用 /stop")
        provider = create_llm_provider(candidate, get_api_key(candidate.provider))
        old = self.agent_loop.llm_provider
        self.config.llm = candidate
        self.agent_loop.llm_provider = provider
        if self.session is not None:
            self.session.set_model(candidate.model)

        async def close_old():
            try:
                await old.aclose()
            except Exception as exc:
                logger.warning(f"关闭旧 Provider 失败: {exc}")

        task = asyncio.create_task(close_old())
        if not hasattr(self, "_provider_cleanup_tasks"):
            self._provider_cleanup_tasks = set()
        self._provider_cleanup_tasks.add(task)
        task.add_done_callback(self._provider_cleanup_tasks.discard)

    def _handle_model_command(
        self, chat: ChatWidget, header: HeaderWidget, args: str
    ) -> None:
        """列出或切换模型（必要时跨 Provider 重建客户端）"""
        if not self.config:
            chat.add_system_message("Agent 未初始化")
            return

        models = self.config.available_models
        current = self.config.llm.model

        if not args or args == "list":
            lines = [
                f"📦 可用模型（当前: {current} · provider={self.config.llm.provider}）:"
            ]
            for index, model in enumerate(models, start=1):
                inferred = infer_provider_for_model(model) or self.config.llm.provider
                mark = "  ← 当前" if model == current else ""
                lines.append(f"  {index}. {model}  [{inferred}]{mark}")
            lines.append("")
            lines.append("切换: /model <序号> 或 /model <模型名>")
            chat.add_system_message("\n".join(lines))
            return

        target = args
        if args.isdigit():
            index = int(args) - 1
            if index < 0 or index >= len(models):
                chat.add_system_message(f"无效序号: {args}，请输入 1-{len(models)}")
                return
            target = models[index]

        if target not in models:
            chat.add_system_message(f"未知模型: {target}\n使用 /model 查看可用列表")
            return

        old_provider = normalize_provider_name(self.config.llm.provider)
        inferred = infer_provider_for_model(target)
        new_provider = inferred or old_provider
        provider_changed = new_provider != old_provider

        candidate = self.config.llm.model_copy(deep=True)
        candidate.model = target
        if provider_changed:
            apply_provider_defaults(candidate, new_provider)
        try:
            self._rebuild_llm_provider(candidate)
        except Exception as e:
            chat.add_system_message(f"❌ 切换模型失败: {e}")
            return

        self._update_header()
        if provider_changed:
            chat.add_system_message(
                f"✅ 已切换模型: {target}\n   Provider: {old_provider} → {new_provider}"
            )
        else:
            chat.add_system_message(f"✅ 已切换模型: {target}")

    def _handle_provider_command(
        self, chat: ChatWidget, header: HeaderWidget, args: str
    ) -> None:
        """查看或切换 LLM Provider"""
        if not self.config:
            chat.add_system_message("Agent 未初始化")
            return

        current = normalize_provider_name(self.config.llm.provider)
        if not args or args == "list":
            chat.add_system_message(
                "🔌 Provider:\n"
                f"  当前: {current}\n"
                "  可选: openai_compat / anthropic\n"
                "切换: /provider <名称>"
            )
            return

        try:
            target = normalize_provider_name(args)
            if target not in ("openai_compat", "anthropic"):
                raise ValueError(f"未知 provider: {args}")
        except ValueError as e:
            chat.add_system_message(str(e))
            return

        if target == current:
            chat.add_system_message(f"已经是 {current}")
            return

        old = current
        candidate = self.config.llm.model_copy(deep=True)
        apply_provider_defaults(candidate, target)
        try:
            self._rebuild_llm_provider(candidate)
        except Exception as e:
            chat.add_system_message(f"❌ 切换失败: {e}")
            return

        self._update_header()
        chat.add_system_message(
            f"✅ Provider: {old} → {target}\n"
            f"   API: {self.config.llm.api_base}\n"
            f"   模型仍为: {self.config.llm.model}（可用 /model 切换）"
        )

    def _set_input_mode(self, *, waiting_confirm: bool) -> None:
        """切换底部输入框状态"""
        screen = self.screen
        input_widget = screen.query_one("#input", InputWidget)
        if waiting_confirm:
            input_widget.placeholder = INPUT_PLACEHOLDER_CONFIRM
            input_widget.disabled = True
        else:
            input_widget.placeholder = INPUT_PLACEHOLDER
            input_widget.disabled = False

    def _show_confirm_widget(self, tool_name: str, summary: str) -> None:
        """在底部输入区上方的独立槽位显示权限确认（与聊天流分离）"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        if chat._streaming_widget is not None:
            chat.finish_streaming()
        slot = screen.query_one("#confirm-slot", Container)
        # 避免重复挂载
        for child in list(slot.children):
            child.remove()
        slot.mount(ConfirmWidget(tool_name, summary))
        self._set_input_mode(waiting_confirm=True)

    def on_confirm(self, confirmed: bool, allow_session: bool = False) -> None:
        """用户确认/拒绝回调；allow_session=True 表示本会话 WRITE/SHELL 全放行"""
        screen = self.screen
        confirm = screen.query_one(".confirm-inline")
        confirm.remove()

        self._waiting_confirmation = False
        self._set_input_mode(waiting_confirm=False)

        if confirmed and allow_session and self.agent_loop is not None:
            chat = screen.query_one("#chat", ChatWidget)
            chat.add_system_message(
                "已开启：本次会话写入/Shell 将跳过确认（黑名单仍生效）"
            )

        self._run_agent_continue(confirmed=confirmed, allow_session=allow_session)

    def _run_agent(self, user_input: str) -> None:
        """运行 Agent"""
        if self.agent_loop is None:
            return

        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        chat.add_user_message(user_input)
        chat.show_thinking()

        self._update_header(status="运行中")

        self._agent_running = True
        self._stop_requested = False
        self._agent_task = asyncio.create_task(
            self._process_events(self.agent_loop.run(user_input))
        )

    def _run_agent_continue(self, confirmed: bool, allow_session: bool = False) -> None:
        """继续 Agent 执行（权限确认后）"""
        if self.agent_loop is None:
            return

        self._update_header(status="运行中")

        self._agent_running = True
        self._stop_requested = False
        self._agent_task = asyncio.create_task(
            self._process_events(
                self.agent_loop.continue_with_confirmation(
                    confirmed, allow_session=allow_session
                )
            )
        )

    def _finalize_stopped(
        self, chat: ChatWidget, *, message: str = "⏹ 任务已终止"
    ) -> None:
        """stop/cancel 后统一复位 UI 与运行标志"""
        if chat._streaming_widget is not None:
            chat.finish_streaming()
        chat.hide_tool_running()
        chat.hide_thinking()
        chat.add_system_message(message)
        self._update_header(status="就绪")
        self._agent_running = False
        self._stop_requested = False
        self._agent_task = None
        if getattr(self, "agent_loop", None) is not None:
            self.agent_loop.stop()
        elif self.session is not None:
            from ..session.storage import save_session

            save_session(self.session)

    async def _process_events(self, events):
        """处理 Agent 事件流"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)

        pending_tool: dict | None = None

        try:
            async for event in events:
                # 协作式 stop：若 cancel 未立刻打断 await，则在事件边界退出
                if self._stop_requested:
                    self._finalize_stopped(chat)
                    return

                if isinstance(event, TextDelta):
                    if chat._streaming_widget is None:
                        chat.start_streaming()
                    chat.append_streaming(event.content)

                elif isinstance(event, ToolCallStart):
                    tool = self.agent_loop.tool_registry.get(event.name)
                    is_auto = tool and tool.permission_level.value == "read"
                    pending_tool = {
                        "name": event.name,
                        "arguments": event.arguments,
                        "auto": is_auto,
                    }
                    self._update_header(status=f"执行 {event.name}")
                    chat.show_tool_running(event.name, event.arguments)

                elif isinstance(event, ToolCallResult):
                    if pending_tool:
                        chat.add_tool_result(
                            name=pending_tool["name"],
                            arguments=pending_tool["arguments"],
                            auto=pending_tool["auto"],
                            result=event.output,
                            success=event.success,
                        )
                        pending_tool = None
                    else:
                        chat.add_tool_result(
                            event.name,
                            {},
                            auto=True,
                            result=event.output,
                            success=event.success,
                        )
                    self._update_header(status="运行中")

                elif isinstance(event, PermissionRequest):
                    chat.hide_thinking()
                    if chat._streaming_widget is not None:
                        chat.finish_streaming()
                    self._show_confirm_widget(event.name, event.summary)
                    self._waiting_confirmation = True
                    self._update_header(status="等待确认")
                    return

                elif isinstance(event, PermissionDenied):
                    chat.add_permission_denied(event.name)

                elif isinstance(event, AgentFinished):
                    # 结束流式输出
                    if chat._streaming_widget is not None:
                        chat.finish_streaming()
                    elif event.message:
                        chat.add_assistant_message(event.message)
                    self._update_header(status="就绪")
                    self._agent_running = False

                elif isinstance(event, AgentError):
                    chat.add_error(event.message)
                    self._update_header(status="就绪")
                    self._agent_running = False

        except asyncio.CancelledError:
            # Task.cancel() 注入的是 BaseException，不能只靠 except Exception
            self._finalize_stopped(chat)
        except Exception as e:
            if chat._streaming_widget is not None:
                chat.finish_streaming()
            chat.add_error(f"Agent 异常: {e}")
            logger.error(f"Agent 异常: {e}")
            if self.agent_loop is not None:
                try:
                    self.agent_loop.stop("运行异常，操作已终止")
                except OSError as save_error:
                    chat.add_error(f"历史保存失败，内存记录仍保留: {save_error}")
            self._update_header(status="就绪")
            self._agent_running = False
            self._stop_requested = False
            self._agent_task = None

        finally:
            # 关闭暂停在 yield 的生成器，及时释放运行锁（确认态保留待执行调用）。
            await events.aclose()
            if not self._agent_running:
                chat.hide_thinking()

    async def on_unmount(self) -> None:
        """退出前等待运行任务收尾，再释放当前及被替换的客户端。"""
        task = self._agent_task
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        pending = list(getattr(self, "_provider_cleanup_tasks", ()))
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self.agent_loop is not None:
            await self.agent_loop.llm_provider.aclose()
