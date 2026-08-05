"""工具基类 + 权限级别定义 + ToolResult 类型"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class PermissionLevel(str, Enum):
    """权限级别"""

    READ = "read"  # 只读操作，自动执行
    WRITE = "write"  # 写入操作，需用户确认
    SHELL = "shell"  # Shell 命令，需用户确认


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    output: str
    error: str = ""

    @classmethod
    def ok(cls, output: str) -> "ToolResult":
        return cls(success=True, output=output)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, output="", error=error)


class ToolBase(ABC):
    """工具抽象基类"""

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)  # JSON Schema 格式
    permission_level: PermissionLevel = PermissionLevel.READ

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具，返回 ToolResult"""
        ...

    def to_openai_schema(self) -> dict:
        """转为 OpenAI function calling schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
