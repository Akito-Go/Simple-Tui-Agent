"""程序入口 — python -m tui_agent"""

import sys


def main():
    """启动 TUI Agent"""
    from tui_agent.tui.app import TuiAgentApp

    app = TuiAgentApp()
    app.run()


if __name__ == "__main__":
    main()
