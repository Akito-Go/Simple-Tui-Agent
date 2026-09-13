"""统一自动执行与确认后执行，保证每次调用只记录一次结果。"""

from ..permissions.guard import ToolCall
from ..session.manager import SessionManager
from ..tools.registry import ToolRegistry
from .types import ToolCallResult


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, session: SessionManager):
        self.registry = registry
        self.session = session

    def record(self, call: ToolCall, success: bool, output: str) -> ToolCallResult:
        self.session.add_tool_result(call.id, call.name, output)
        return ToolCallResult(call.id, call.name, success, output)

    async def execute(self, call: ToolCall) -> ToolCallResult:
        result = await self.registry.execute(call.name, call.arguments)
        return self.record(
            call,
            result.success,
            result.output if result.success else f"[错误] {result.error}",
        )
