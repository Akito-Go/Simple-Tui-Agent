"""程序入口 — 支持交互 TUI 与非交互命令行模式。"""



def main():
    """启动 TUI Agent"""
    import argparse
    import asyncio
    import json
    import sys
    from importlib.metadata import version
    from tui_agent.agent.loop import AgentLoop
    from tui_agent.config.loader import get_api_key, load_config
    from tui_agent.permissions.guard import PermissionGuard
    from tui_agent.session.manager import SessionManager
    from tui_agent.tools.builtin import create_default_registry
    from tui_agent.llm.factory import create_llm_provider

    parser = argparse.ArgumentParser(description="STA 终端编码 Agent")
    parser.add_argument("--version", action="version", version=f"STA {version('tui-agent')}")
    parser.add_argument("--setup", action="store_true", help="配置用户级服务商、模型和 API Key")
    parser.add_argument("--prompt", help="非交互执行的任务")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出非交互结果")
    parser.add_argument("--yes", action="store_true", help="自动确认写入和 Shell 操作")
    args = parser.parse_args()
    if args.setup and (args.prompt is not None or args.json or args.yes):
        parser.error("--setup 不能与 --prompt、--json 或 --yes 同时使用")

    def setup():
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            parser.error("配置向导需要交互终端，请在终端运行 sta --setup")
        from tui_agent.config.setup import run_setup
        try:
            run_setup()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消配置。", file=sys.stderr)
            raise SystemExit(130) from None
        except (OSError, ValueError) as exc:
            parser.error(f"配置保存失败：{exc}")

    if args.setup:
        setup()
        return
    if args.prompt is None:
        config = load_config()
        try:
            get_api_key(config.llm.provider)
        except ValueError:
            setup()
            try:
                get_api_key(load_config().llm.provider)
            except ValueError:
                parser.error("当前工作区或环境变量覆盖了用户配置，请检查服务商设置，或运行 sta --setup 配置对应密钥")
    if args.prompt is not None:
        config = load_config()
        session = SessionManager(model=config.llm.model)
        registry = create_default_registry()
        loop = AgentLoop(create_llm_provider(config.llm, get_api_key(config.llm.provider)), registry, PermissionGuard(), session, config.max_turns, config.context_max_tokens)

        async def run_prompt():
            from tui_agent.agent.types import AgentFinished, AgentError, PermissionRequest, TextDelta
            text = []
            events = loop.run(args.prompt)
            async for event in events:
                if isinstance(event, TextDelta): text.append(event.content)
                elif isinstance(event, PermissionRequest):
                    if not args.yes: loop.stop("非交互模式未确认写入或 Shell 操作"); break
                    async for follow in loop.continue_with_confirmation(True, allow_session=True):
                        if isinstance(follow, TextDelta): text.append(follow.content)
                elif isinstance(event, AgentFinished): break
                elif isinstance(event, AgentError): text.append(f"[错误] {event.message}")
            return {"success": not any(t.startswith("[错误]") for t in text), "message": "".join(text), "changed_files": loop.state.changed_files, "phase": loop.state.phase}
        result = asyncio.run(run_prompt())
        print(json.dumps(result, ensure_ascii=False) if args.json else result["message"])
        return
    from tui_agent.tui.app import TuiAgentApp

    app = TuiAgentApp()
    app.run()


if __name__ == "__main__":
    main()
