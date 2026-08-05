"""Textual App 主类 — 事件绑定、Agent Loop 集成"""

import asyncio
from pathlib import Path

from textual.app import App
from textual.widgets import Input

from .screens import MainScreen
from .widgets.header import HeaderWidget
from .widgets.chat import ChatWidget
from .widgets.input import InputWidget, INPUT_PLACEHOLDER, INPUT_PLACEHOLDER_CONFIRM
from .widgets.confirm import ConfirmWidget
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
    """TUI Agent 主应用"""

    CSS = """
    Screen {
        layout: vertical;
    }
    """

    def __init__(self):
        super().__init__()
        self.config: AppConfig | None = None
        self.agent_loop: AgentLoop | None = None
        self.session: SessionManager | None = None
        self._waiting_confirmation: bool = False
        self._agent_running: bool = False
        self._stop_requested: bool = False
        self._agent_task: asyncio.Task | None = None

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

            # 检查是否有历史会话
            from ..session.loader import list_sessions
            sessions = list_sessions()
            if sessions:
                self._selecting_session = True
                chat = screen.query_one("#chat", ChatWidget)
                lines = ["📂 发现历史会话，输入序号恢复，N 新建空会话，直接输入消息新建，或使用 /help /model /exit:"]
                for i, s in enumerate(sessions[:9], 1):
                    preview = s.get("preview", "")
                    preview_part = f' | "{preview}"' if preview else ""
                    lines.append(
                        f"  {i}. {s['last_active']} | {s['model']} | "
                        f"轮次:{s['turn_count']} 消息:{s['msg_count']}{preview_part}"
                    )
                lines.append("  N. 新建空会话")
                chat.add_system_message("\n".join(lines))
                self._pending_sessions = sessions
                return

            self._do_init_agent(api_key)

        except ValueError as e:
            chat = screen.query_one("#chat", ChatWidget)
            chat.add_error(f"配置错误: {e}")
            logger.error(f"启动失败: {e}")

    def _do_init_agent(self, api_key: str, session: SessionManager | None = None) -> None:
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

        header = screen.query_one("#header", HeaderWidget)
        header.update_status(
            model=self.config.llm.model,
            turn=self.session.turn_count,
            max_turns=self.config.max_turns,
        )

        logger.info(f"Agent 初始化完成, model={self.config.llm.model}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理用户输入"""
        if not event.value.strip():
            return

        text = event.value.strip()

        # 会话选择模式
        if getattr(self, '_selecting_session', False):
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
        """处理会话选择输入"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        sessions = getattr(self, '_pending_sessions', [])

        if text.upper() in ("N", "NEW"):
            self._selecting_session = False
            self._pending_sessions = []
            chat.add_system_message("开始新会话")
            self._do_init_agent(get_api_key(self.config.llm.provider))
            return

        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(sessions):
                from ..session.loader import load_session
                session = load_session(sessions[idx]["filepath"], model=self.config.llm.model)
                if session:
                    self._selecting_session = False
                    self._pending_sessions = []
                    chat.add_system_message(f"✅ 已恢复会话 {session.session_id}")
                    self._do_init_agent(get_api_key(self.config.llm.provider), session=session)
                    return
            chat.add_system_message(
                f"无效序号，请输入 1-{min(len(sessions), 9)}，N 新建空会话，或直接输入消息"
            )
            return

        # 任意消息：新建会话并立即发送
        self._selecting_session = False
        self._pending_sessions = []
        self._do_init_agent(get_api_key(self.config.llm.provider))
        self._run_agent(text)

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
  /stop     - 停止当前 Agent 运行
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
                chat.add_system_message("会话选择中，请先用序号恢复或输入消息新建")
                return
            if self.session:
                self.session.clear()
            if self.agent_loop is not None:
                self.agent_loop.permission_guard.reset_session_allow_all()
            chat.clear()
            chat.add_system_message("会话已清空")
            logger.info("会话已清空")

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
  轮次: {self.session.turn_count}/{self.config.max_turns}
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
                    self.agent_loop.permission_guard.deny()
                if self._agent_task is not None:
                    self._agent_task.cancel()
                    self._agent_task = None
                self._agent_running = False
                chat.add_system_message("⏹ 已终止等待确认的任务")
                header.update_status(
                    model=self.config.llm.model,
                    turn=self.session.turn_count if self.session else 0,
                    max_turns=self.config.max_turns,
                    status="🟢 等待输入",
                )
            elif self._agent_running:
                self._stop_requested = True
                if self._agent_task is not None:
                    self._agent_task.cancel()
                chat.add_system_message("⏹ 正在终止当前任务...")
            else:
                chat.add_system_message("当前没有正在运行的任务")

        elif command == Command.EXIT:
            chat.add_system_message("正在退出...")
            if self.session:
                from ..session.storage import save_session
                save_session(self.session)
            self.exit()

    def _rebuild_llm_provider(self) -> None:
        """按当前 config.llm 重建 Provider 并挂到 AgentLoop"""
        if self.config is None or self.agent_loop is None:
            return
        api_key = get_api_key(self.config.llm.provider)
        self.agent_loop.llm_provider = create_llm_provider(self.config.llm, api_key)

    def _handle_model_command(self, chat: ChatWidget, header: HeaderWidget, args: str) -> None:
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
            chat.add_system_message(
                f"未知模型: {target}\n使用 /model 查看可用列表"
            )
            return

        old_provider = normalize_provider_name(self.config.llm.provider)
        inferred = infer_provider_for_model(target)
        new_provider = inferred or old_provider
        provider_changed = new_provider != old_provider

        self.config.llm.model = target
        if provider_changed:
            apply_provider_defaults(self.config.llm, new_provider)
            try:
                self._rebuild_llm_provider()
            except ValueError as e:
                # 回滚 provider，至少保留模型名切换提示
                apply_provider_defaults(self.config.llm, old_provider)
                chat.add_system_message(f"❌ 切换 Provider 失败: {e}")
                return
        elif self.agent_loop is not None:
            self.agent_loop.llm_provider.model = target

        if self.session is not None:
            self.session.set_model(target)

        turn = self.session.turn_count if self.session else 0
        header.update_status(
            model=target,
            turn=turn,
            max_turns=self.config.max_turns,
        )
        if provider_changed:
            chat.add_system_message(
                f"✅ 已切换模型: {target}\n   Provider: {old_provider} → {new_provider}"
            )
        else:
            chat.add_system_message(f"✅ 已切换模型: {target}")

    def _handle_provider_command(self, chat: ChatWidget, header: HeaderWidget, args: str) -> None:
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
        apply_provider_defaults(self.config.llm, target)
        try:
            self._rebuild_llm_provider()
        except ValueError as e:
            apply_provider_defaults(self.config.llm, old)
            chat.add_system_message(f"❌ 切换失败: {e}")
            return

        header.update_status(
            model=self.config.llm.model,
            turn=self.session.turn_count if self.session else 0,
            max_turns=self.config.max_turns,
        )
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
        """在对话流中内联显示权限确认组件"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        if chat._streaming_widget is not None:
            chat.finish_streaming()
        chat.mount(ConfirmWidget(tool_name, summary))
        chat.scroll_end(animate=False)
        self._set_input_mode(waiting_confirm=True)

    def on_confirm(self, confirmed: bool, allow_session: bool = False) -> None:
        """用户确认/拒绝回调；allow_session=True 表示本会话 WRITE/SHELL 全放行"""
        screen = self.screen
        confirm = screen.query_one(".confirm-inline")
        confirm.remove()

        self._waiting_confirmation = False
        self._set_input_mode(waiting_confirm=False)

        if confirmed and allow_session and self.agent_loop is not None:
            self.agent_loop.permission_guard.enable_session_allow_all()
            chat = screen.query_one("#chat", ChatWidget)
            chat.add_system_message("✅ 已开启：本次会话写入/Shell 操作将自动允许")

        self._run_agent_continue(confirmed=confirmed)

    def _run_agent(self, user_input: str) -> None:
        """运行 Agent"""
        if self.agent_loop is None:
            return

        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        header = screen.query_one("#header", HeaderWidget)
        chat.add_user_message(user_input)
        chat.show_thinking()

        header.update_status(
            model=self.config.llm.model,
            turn=self.session.turn_count,
            max_turns=self.config.max_turns,
            status="🔴 运行中",
        )

        self._agent_running = True
        self._stop_requested = False
        self._agent_task = asyncio.create_task(self._process_events(self.agent_loop.run(user_input)))

    def _run_agent_continue(self, confirmed: bool) -> None:
        """继续 Agent 执行（权限确认后）"""
        if self.agent_loop is None:
            return

        screen = self.screen
        header = screen.query_one("#header", HeaderWidget)
        header.update_status(
            model=self.config.llm.model,
            turn=self.session.turn_count,
            max_turns=self.config.max_turns,
            status="🔴 运行中",
        )

        self._agent_running = True
        self._stop_requested = False
        self._agent_task = asyncio.create_task(self._process_events(self.agent_loop.continue_with_confirmation(confirmed)))

    async def _process_events(self, events):
        """处理 Agent 事件流"""
        screen = self.screen
        chat = screen.query_one("#chat", ChatWidget)
        header = screen.query_one("#header", HeaderWidget)

        pending_tool: dict | None = None

        try:
            async for event in events:
                # 每次迭代前检查 stop
                if self._stop_requested:
                    chat.add_system_message("⏹ 任务已终止")
                    header.update_status(
                        model=self.config.llm.model,
                        turn=self.session.turn_count,
                        max_turns=self.config.max_turns,
                        status="🟢 等待输入",
                    )
                    self._agent_running = False
                    self._stop_requested = False
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
                    header.update_status(
                        model=self.config.llm.model,
                        turn=self.session.turn_count,
                        max_turns=self.config.max_turns,
                        status=f"🔴 执行 {event.name}",
                    )
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
                    header.update_status(
                        model=self.config.llm.model,
                        turn=self.session.turn_count,
                        max_turns=self.config.max_turns,
                        status="🔴 运行中",
                    )

                elif isinstance(event, PermissionRequest):
                    chat.hide_thinking()
                    if chat._streaming_widget is not None:
                        chat.finish_streaming()
                    self._show_confirm_widget(event.name, event.summary)
                    self._waiting_confirmation = True
                    header.update_status(
                        model=self.config.llm.model,
                        turn=self.session.turn_count,
                        max_turns=self.config.max_turns,
                        status="🟡 等待确认",
                    )
                    return

                elif isinstance(event, PermissionDenied):
                    chat.add_permission_denied(event.name)

                elif isinstance(event, AgentFinished):
                    # 结束流式输出
                    if chat._streaming_widget is not None:
                        chat.finish_streaming()
                    elif event.message:
                        chat.add_assistant_message(event.message)
                    header.update_status(
                        model=self.config.llm.model,
                        turn=self.session.turn_count,
                        max_turns=self.config.max_turns,
                        status="🟢 等待输入",
                    )
                    self._agent_running = False

                elif isinstance(event, AgentError):
                    chat.add_error(event.message)
                    header.update_status(
                        model=self.config.llm.model,
                        turn=self.session.turn_count,
                        max_turns=self.config.max_turns,
                        status="🟢 等待输入",
                    )
                    self._agent_running = False

        except Exception as e:
            chat.add_error(f"Agent 异常: {e}")
            logger.error(f"Agent 异常: {e}")
            header.update_status(
                model=self.config.llm.model,
                turn=self.session.turn_count,
                max_turns=self.config.max_turns,
                status="🟢 等待输入",
            )
            self._agent_running = False
