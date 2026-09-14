"""内置命令处理 — /help /clear /sessions /model /provider /status /exit"""

from dataclasses import dataclass
from enum import Enum


class Command(str, Enum):
    HELP = "/help"
    CLEAR = "/clear"
    SESSIONS = "/sessions"
    MODEL = "/model"
    PROVIDER = "/provider"
    STATUS = "/status"
    STOP = "/stop"
    EXIT = "/exit"
    PLAN = "/plan"
    RESUME = "/resume"
    UNDO = "/undo"
    DIFF = "/diff"
    FILES = "/files"


@dataclass
class CommandResult:
    """命令执行结果"""
    is_command: bool
    command: Command | None = None
    args: str = ""  # 命令参数


def parse_command(text: str) -> CommandResult:
    """
    解析用户输入是否为内置命令。

    Returns:
        CommandResult: 包含是否为命令、命令类型和参数
    """
    text = text.strip()

    for cmd in Command:
        if text == cmd.value:
            return CommandResult(is_command=True, command=cmd)
        if text.startswith(cmd.value + " "):
            args = text[len(cmd.value) + 1 :].strip()
            return CommandResult(is_command=True, command=cmd, args=args)

    return CommandResult(is_command=False)
