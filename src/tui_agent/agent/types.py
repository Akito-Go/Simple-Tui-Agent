"""Agent 事件类型定义"""

from dataclasses import dataclass


@dataclass
class TextDelta:
    """流式文本片段"""
    content: str


@dataclass
class ToolCallStart:
    """工具调用开始"""
    tool_id: str
    name: str
    arguments: dict


@dataclass
class ToolCallResult:
    """工具执行结果"""
    tool_id: str
    name: str
    success: bool
    output: str


@dataclass
class PermissionRequest:
    """权限确认请求"""
    tool_id: str
    name: str
    arguments: dict
    summary: str  # 操作摘要


@dataclass
class PermissionDenied:
    """权限被拒绝"""
    tool_id: str
    name: str


@dataclass
class AgentFinished:
    """Agent 任务完成"""
    message: str = ""


@dataclass
class AgentError:
    """Agent 错误"""
    message: str


# 联合类型
AgentEvent = TextDelta | ToolCallStart | ToolCallResult | PermissionRequest | PermissionDenied | AgentFinished | AgentError
