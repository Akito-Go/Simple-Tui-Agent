"""Textual App 主类 — 事件绑定、Agent Loop 集成"""

import asyncio
from time import monotonic
from contextlib import aclosing
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Input, Static

from .screens import MainScreen
from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget, INPUT_PLACEHOLDER, INPUT_PLACEHOLDER_CONFIRM
from .widgets.confirm import ConfirmWidget
from .widgets.choice import ChoiceScreen
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
        Binding("ctrl+c", "copy_or_interrupt", "复制 / 停止", show=False, priority=True),
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
        self._pending_undo = None
        self._exiting = False
        self._exit_armed_at = 0.0
        self._btw_task = None
        self._btw_widget = None

    async def action_copy_or_interrupt(self) -> None:
        selected = self.focused.selected_text if isinstance(self.focused, Input) else None
        selected = selected or self.screen.get_selected_text()
        if selected:
            self.copy_to_clipboard(selected)
            self._exit_armed_at = 0.0
            return
        if isinstance(self.screen, ChoiceScreen) or self._btw_widget is not None or self._pending_undo is not None or self._agent_running or self._waiting_confirmation:
            self._exit_armed_at = 0.0
            self.action_stop_agent()
            return
        field = self.screen.query_one(InputWidget)
        if field.value:
            field.value = ""
            self._exit_armed_at = 0.0
            return
        now = monotonic()
        if self._exit_armed_at and now - self._exit_armed_at <= 2:
            await self.action_exit_app()
        else:
            self._exit_armed_at = now
            self.screen.query_one("#footer-hint").update("再次按 Ctrl+C（2 秒内）退出 · 有选中文本时优先复制")

    async def action_exit_app(self) -> None:
        """先停止任务并保存，再由卸载流程关闭客户端。"""
        if self._exiting:
            return
        self._exiting = True
        await self._close_btw()
        task = self._agent_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            if self.agent_loop is not None:
                self.agent_loop.stop("退出程序，任务已中断")
            elif self.session is not None:
                from ..session.storage import save_session
                save_session(self.session)
        except (OSError, ValueError) as exc:
            logger.error(f"退出时保存失败: {exc}")
        self.exit()

    def _show_choice(self, title, labels, callback, selected=0) -> None:
        def chosen(index):
            if index is not None:
                callback(index)
            if not isinstance(self.screen, ChoiceScreen):
                self.call_after_refresh(lambda: self.screen.query_one(InputWidget).focus() if not isinstance(self.screen, ChoiceScreen) else None)

        self.push_screen(ChoiceScreen(title, labels, selected), chosen)

    def action_stop_agent(self) -> None:
        """Esc 快捷键：终止当前 Agent / 取消待确认操作"""
        if isinstance(self.screen, ChoiceScreen):
            self.screen.dismiss(None)
            return
        if self._btw_widget is not None:
            self.run_worker(self._close_btw(), group="btw-close", exclusive=True)
            return
        if self._pending_undo is not None:
            self._pending_undo = None
            self.screen.query_one(ChatWidget).add_system_message("已取消撤销预览")
            return
        self._handle_command(Command.STOP, "")

    def completion_candidates(self) -> list[str]:
        """返回当前可补全的命令、工具和模型。"""
        commands = [command.value for command in Command]
        tools = list(self.agent_loop.tool_registry._tools) if self.agent_loop else []
        models = self.config.available_models if self.config else []
        return commands + tools + models

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
        self._exit_armed_at = 0.0

        # /stop 优先于所有拦截（运行中/等待确认态均可执行）
        cmd_result = parse_command(text)
        if cmd_result.is_command and cmd_result.command in (Command.STOP, Command.EXIT, Command.BTW):
            self._handle_command(cmd_result.command, cmd_result.args)
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

    def _list_sessions_for_resume(self) -> None:
        """列出可恢复会话并进入选择模式"""
        from ..session.loader import list_sessions

        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        sessions = list_sessions()
        if not sessions:
            chat.add_system_message("暂无历史会话可恢复")
            return

        self._pending_sessions = sessions
        labels = [f"{s['last_active']} · {s['model']} · {s.get('preview', '')[:80]}" for s in sessions]
        self._show_choice("恢复历史会话", labels, self._resume_session_at)

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

        self._pending_sessions = []
        chat.clear()
        self._do_init_agent(
            get_api_key(self.config.llm.provider),
            session=session,
            recent_sessions=list_sessions(),
            show_welcome=True,
        )

    def _cleanup_sessions(self, all_sessions, chat):
        from ..session.loader import list_sessions
        from ..session.cleanup import prepare_cleanup

        current = self.session.session_id if self.session else None
        sessions = [s for s in list_sessions() if s["session_id"] != current]
        if not sessions:
            chat.add_system_message("没有可删除的过去会话（当前会话保留）")
            return

        def preview(ids):
            try:
                plan = prepare_cleanup(ids, current)
            except (OSError, ValueError) as exc:
                chat.add_error(f"无法预览历史清理：{exc}")
                return
            checkpoint_count = len(plan.files) - len(plan.session_ids)
            title = f"永久删除 {len(plan.session_ids)} 个过去会话和 {checkpoint_count} 个关联检查点？\n当前会话保留，重启后仍可恢复。所选历史的恢复与撤销记录将丢失，项目文件不变。"

            def confirm(index):
                if index != 1:
                    return
                try:
                    count = plan.delete(self.session.session_id if self.session else None)
                    self._pending_undo = None
                    self._pending_sessions = []
                    chat.add_system_message(f"已清理 {len(plan.session_ids)} 个过去会话，共删除 {count} 个历史文件。当前会话已保留，重启后仍会出现在历史中。")
                    for welcome in chat.query(WelcomeWidget):
                        from .welcome import _format_recent_activity
                        welcome.query_one('#welcome-recent', Static).update(_format_recent_activity(list_sessions()))
                except (OSError, ValueError) as exc:
                    chat.add_error(f"清理未完成：{exc}")

            self._show_choice(title, ["取消，保留历史", "确认永久删除"], confirm)

        if all_sessions:
            preview([s["session_id"] for s in sessions])
        else:
            self._show_choice("选择要删除的过去会话", [f"{s['last_active']} · {s['model']} · {s['preview']}" for s in sessions], lambda i: preview([sessions[i]['session_id']]))

    async def _close_btw(self):
        task, widget = self._btw_task, self._btw_widget
        self._btw_task = self._btw_widget = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if widget is not None and widget.is_attached:
            await widget.remove()

    def _start_btw(self, question, chat):
        from .btw import build_btw_messages
        if not question:
            chat.add_system_message("用法：/btw <顺便问的问题>；Esc 关闭临时问答")
            return
        if not self.config or not self.agent_loop:
            chat.add_error("Agent 未初始化")
            return
        if self._waiting_confirmation:
            chat.add_system_message("请先处理当前权限确认，再使用 /btw")
            return
        if self._btw_widget is not None:
            chat.add_system_message("请先按 Esc 关闭当前临时问答，再提新问题")
            return
        if len(question) > 8000:
            chat.add_system_message("临时问题过长，请控制在 8000 字符以内")
            return
        messages = build_btw_messages(self.session.build_messages() if self.session else [], question)
        from ..session.compressor import estimate_tokens
        budget = self.config.context_max_tokens - min(2048, self.config.context_max_tokens // 4)
        while messages[1]['content'] and estimate_tokens(messages) > budget:
            messages[1]['content'] = messages[1]['content'][len(messages[1]['content']) // 2 + 1:]
        if estimate_tokens(messages) > budget:
            chat.add_system_message("临时问题超过当前上下文预算，请缩短问题")
            return
        config = self.config.llm.model_copy(deep=True)
        widget = Static(f"顺便问 · {question}\n正在回答…\nEsc 关闭 · 不写入主会话", markup=False)
        self._btw_widget = widget
        self.screen.query_one('#btw-slot').mount(widget)
        self._btw_task = asyncio.create_task(self._answer_btw(config, messages, question, widget))

    async def _answer_btw(self, config, messages, question, widget):
        provider = None
        answer = ""
        try:
            provider = create_llm_provider(config, get_api_key(config.provider))
            async with aclosing(provider.chat(messages, tools=[], stream=True)) as events:
                async for event in events:
                    if event['type'] in {'text_delta', 'text'}:
                        answer += event['content']
                        widget.update(f"顺便问 · {question}\n{answer[:16000]}\nEsc 关闭 · 不写入主会话")
                        if len(answer) > 16000:
                            widget.update(f"顺便问 · {question}\n{answer[:16000]}\n[回答过长，已截断] · Esc 关闭")
                            break
                    elif event['type'] == 'error':
                        raise RuntimeError(event['message'])
                    elif event['type'] == 'finish':
                        break
            if not answer:
                widget.update(f"顺便问 · {question}\n模型没有返回文字；此处不支持工具调用。\nEsc 关闭")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            widget.update(f"临时问答失败：{exc}\nEsc 关闭；主任务不受影响")
        finally:
            if provider is not None:
                try:
                    await provider.aclose()
                except Exception as exc:
                    logger.warning(f"关闭临时问答连接失败：{exc}")

    def _handle_command(self, command: Command, args: str) -> None:
        """处理内置命令"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)

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
  /plan <目标> - 生成执行计划（不修改文件）
  /resume [检查点ID] - 列出或继续未完成任务
  /undo [检查点ID] - 预览撤销文件修改；/undo list 列出检查点
  /undo confirm - 确认已预览的撤销；/undo cancel 取消
  /files    - 查看当前任务文件列表与净变更统计
  /diff [路径] - 查看当前任务全部或指定文件差异
  /sessions delete - 选择并删除历史；/sessions delete all 清理全部非当前会话
  /btw <问题> - 临时旁路问答，不调用工具、不写入主会话

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

        elif command == Command.BTW:
            self._start_btw(args.strip(), chat)

        elif command == Command.PLAN:
            goal = (args or "").strip()
            if not goal:
                chat.add_system_message("用法: /plan <任务目标>")
                return
            if self._agent_running or self._waiting_confirmation:
                chat.add_system_message("请先等待当前任务结束，或使用 /stop")
                return
            self._agent_running = True
            self._update_header(status="规划中")
            chat.add_system_message(f"📋 正在为目标生成计划：{goal}")
            self._agent_task = asyncio.create_task(self._generate_plan(goal, chat))

        elif command in (Command.FILES, Command.DIFF):
            checkpoint = getattr(self.agent_loop, "checkpoint", None)
            if command == Command.FILES and args.strip():
                chat.add_system_message("用法：/files；按文件查看差异请用 /diff <路径>")
            elif checkpoint is None:
                chat.add_system_message("当前没有任务检查点。执行任务或使用 /resume 后可查看文件变更。")
            else:
                try:
                    if command == Command.DIFF:
                        chat.add_diff_report(checkpoint, args.strip())
                    else:
                        chat.add_system_message(checkpoint.change_report())
                except (OSError, ValueError) as exc:
                    chat.add_error(f"无法查看文件变更：{exc}")

        elif command in (Command.RESUME, Command.UNDO):
            self._handle_checkpoint_command(command, args.strip(), chat)

        elif command == Command.CLEAR:
            self._pending_undo = None
            if self._agent_running or self._waiting_confirmation:
                chat.add_system_message("请先停止当前任务")
                return
            self._pending_sessions = []
            if self.session:
                self.session.clear()
            if self.agent_loop is not None:
                self.agent_loop.permission_guard.reset_session_allow_all()
                self.agent_loop.checkpoint = None
                state = getattr(self.agent_loop.tool_registry, "file_state", None)
                if state is not None:
                    state.clear()
                    state.checkpoint = None
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
            if args in ("delete", "delete all"):
                self._cleanup_sessions(args == "delete all", chat)
            elif not args:
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
            self._handle_model_command(chat, args)

        elif command == Command.PROVIDER:
            self._handle_provider_command(chat, args)

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
            self.run_worker(self.action_exit_app(), group="exit", exclusive=True)

    def _handle_checkpoint_command(self, command, args, chat):
        from ..session.checkpoint import Checkpoint, RESUMABLE
        if self.agent_loop is None:
            chat.add_error("Agent 未初始化")
            return
        if self._agent_running or self._waiting_confirmation:
            chat.add_system_message("请先等待当前任务结束，或使用 /stop")
            return
        try:
            if command == Command.RESUME:
                self._pending_undo = None
                if not args:
                    tasks = [cp for cp in Checkpoint.recent() if cp.data["status"] in RESUMABLE]
                    tasks = tasks[:10]
                    if tasks:
                        self._show_choice("继续未完成任务", [f"{cp.data['phase']} · {cp.data['goal'][:80]} · {cp.data['id'][:8]}" for cp in tasks], lambda i: self._handle_checkpoint_command(command, tasks[i].data["id"], chat))
                    else:
                        chat.add_system_message("暂无可恢复任务")
                    return
                checkpoint = Checkpoint.load(args)
                if checkpoint.data["status"] not in RESUMABLE:
                    raise ValueError("该任务不能恢复；使用 /resume 查看未完成任务")
                chat.add_system_message("恢复目标：" + checkpoint.data["goal"] + "\n" + "\n".join(checkpoint.inspect_files()))
                self._agent_running = True
                self._stop_requested = False
                self._update_header(status="恢复中")
                self._agent_task = asyncio.create_task(self._process_events(self.agent_loop.resume(args)))
                return
            if args == "cancel":
                self._pending_undo = None
                chat.add_system_message("已取消撤销预览")
                return
            if args == "confirm":
                if self._pending_undo is None:
                    raise ValueError("请先使用 /undo 预览修改文件")
                checkpoint_id, fingerprint = self._pending_undo
                self._pending_undo = None
                checkpoint = Checkpoint.load(checkpoint_id)
                changes = checkpoint.undo(fingerprint)
                file_state = getattr(self.agent_loop.tool_registry, "file_state", None)
                if file_state is not None:
                    file_state.clear()
                    file_state.checkpoint = None
                if self.agent_loop.checkpoint and self.agent_loop.checkpoint.data["id"] == checkpoint_id:
                    self.agent_loop.checkpoint = None
                notice = "已撤销检查点 " + checkpoint_id + " 的文件修改：" + ", ".join(changes) + "。此前工具结果为历史记录，请重新读取现状。"
                self.session.add_user_message(notice)
                from ..session.storage import save_session
                save_session(self.session)
                chat.add_system_message(notice)
                return
            self._pending_undo = None
            tasks = [cp for cp in Checkpoint.recent() if cp.data["files"] and cp.data["status"] != "undone"]
            if args == "list":
                tasks = tasks[:10]
                if tasks:
                    self._show_choice("选择要预览撤销的任务", [f"{cp.data['goal'][:80]} · {len(cp.data['files'])} 个记录文件" for cp in tasks], lambda i: self._handle_checkpoint_command(command, tasks[i].data["id"], chat))
                else:
                    chat.add_system_message("暂无文件检查点")
                return
            checkpoint = Checkpoint.load(args) if args else (tasks[0] if tasks else None)
            if checkpoint is None:
                raise ValueError("暂无可撤销的文件修改")
            changes = checkpoint.undo_preview()
            if not changes:
                raise ValueError("该检查点没有需要恢复的文件")
            self._pending_undo = (checkpoint.data["id"], checkpoint.fingerprint())
            lines = [f"{'删除新建文件' if checkpoint.data['files'][p]['before'] is None else '恢复原内容和权限'}：{p}" for p in changes]
            chat.add_system_message(f"撤销预览 · {checkpoint.data['id']}\n目标：{checkpoint.data['goal']}\n" + "\n".join(lines) + "\nShell 操作不在撤销范围。输入 /undo confirm 确认，/undo cancel 或 Esc 取消。")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            chat.add_error(f"检查点操作失败: {exc}")

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
        self, chat: ChatWidget, args: str
    ) -> None:
        """列出或切换模型（必要时跨 Provider 重建客户端）"""
        if not self.config:
            chat.add_system_message("Agent 未初始化")
            return

        models = self.config.available_models
        current = self.config.llm.model

        if not args or args == "list":
            if not models:
                chat.add_system_message("暂无可用模型，请先配置模型列表")
                return
            self._show_choice("选择模型", [f"{model}{' · 当前' if model == current else ''}" for model in models], lambda i: self._handle_model_command(chat, models[i]), models.index(current) if current in models else 0)
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
        self, chat: ChatWidget, args: str
    ) -> None:
        """查看或切换 LLM Provider"""
        if not self.config:
            chat.add_system_message("Agent 未初始化")
            return

        current = normalize_provider_name(self.config.llm.provider)
        if not args or args == "list":
            providers = ["openai_compat", "anthropic"]
            self._show_choice("选择 Provider", [f"{p}{' · 当前' if p == current else ''}" for p in providers], lambda i: self._handle_provider_command(chat, providers[i]), providers.index(current))
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

    async def _generate_plan(self, goal: str, chat: ChatWidget) -> None:
        """调用模型生成只读计划，不写入会话，也不提供工具。"""
        messages = [
            {"role": "system", "content": (
                "你是软件开发计划助手。只输出执行计划，不调用工具、不修改文件。"
                "用中文回答，包含：目标理解、步骤、涉及文件或范围、风险、验证方式。"
            )},
            {"role": "user", "content": goal},
        ]
        parts: list[str] = []
        try:
            async with aclosing(self.agent_loop.llm_provider.chat(messages, tools=[], stream=True)) as events:
                async for event in events:
                    if event["type"] in ("text_delta", "text"):
                        parts.append(event["content"])
                    elif event["type"] == "error":
                        raise RuntimeError(event["message"])
                    elif event["type"] == "finish":
                        break
            chat.add_assistant_message(
                f"📋 计划（只规划，不执行）\n目标：{goal}\n\n{''.join(parts).strip()}\n\n发送原任务即可开始执行。"
            )
        except asyncio.CancelledError:
            chat.add_system_message("已取消计划生成")
        except Exception as exc:
            chat.add_error(f"计划生成失败: {exc}")
        finally:
            self._agent_running = False
            self._agent_task = None
            self._update_header(status="就绪")

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
        self._pending_undo = None
        chat.add_user_message(user_input)
        self._show_task_context(chat, user_input)
        chat.show_thinking()

        self._update_header(status="运行中")

        self._agent_running = True
        self._stop_requested = False
        self._agent_task = asyncio.create_task(
            self._process_events(self.agent_loop.run(user_input))
        )

    def _show_task_context(self, chat: ChatWidget, goal: str) -> None:
        """展示当前任务的目标和阶段，避免长任务失去上下文。"""
        chat.add_system_message(f"任务：{goal}\n阶段：分析 · 进度：0/{self.config.max_turns if self.config else 0} 轮")

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
                self.session = self.agent_loop.session
                # 协作式 stop：若 cancel 未立刻打断 await，则在事件边界退出
                if self._stop_requested:
                    self._finalize_stopped(chat)
                    return

                if isinstance(event, TextDelta):
                    if chat._streaming_widget is None:
                        chat.start_streaming()
                    chat.append_streaming(event.content)

                elif isinstance(event, ToolCallStart):
                    pending_tool = {
                        "name": event.name,
                        "arguments": event.arguments,
                    }
                    self.agent_loop.state.phase = "执行工具"
                    self.agent_loop.state.total_tools += 1
                    if event.name in {"write_file", "edit_file"}:
                        path = event.arguments.get("path")
                        if path and path not in self.agent_loop.state.changed_files:
                            self.agent_loop.state.changed_files.append(path)
                    self._update_header(status=f"执行 {event.name} · {self.agent_loop.state.completed_tools}/{self.agent_loop.state.total_tools}")
                    chat.show_tool_running(event.name, event.arguments)

                elif isinstance(event, ToolCallResult):
                    self.agent_loop.state.completed_tools += 1
                    if pending_tool:
                        chat.add_tool_result(
                            name=pending_tool["name"],
                            arguments=pending_tool["arguments"],
                            result=event.output,
                            success=event.success,
                        )
                        pending_tool = None
                    else:
                        chat.add_tool_result(
                            event.name,
                            {},
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
                    checkpoint = getattr(self.agent_loop, "checkpoint", None)
                    if checkpoint and checkpoint.data["files"]:
                        chat.add_system_message(checkpoint.change_report())
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
        await self._close_btw()
        task = self._agent_task
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        pending = list(getattr(self, "_provider_cleanup_tasks", ()))
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        provider = getattr(self.agent_loop, "llm_provider", None)
        if provider is not None and hasattr(provider, "aclose"):
            await provider.aclose()
