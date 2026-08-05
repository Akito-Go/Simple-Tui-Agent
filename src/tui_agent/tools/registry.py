"""工具注册表 — 管理工具生命周期和 Schema 暴露"""

from .base import ToolBase, ToolResult


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolBase | None:
        """获取工具"""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def to_openai_schemas(self) -> list[dict]:
        """将所有工具转为 OpenAI function calling schema 数组"""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """执行指定工具"""
        tool = self.get(name)
        if tool is None:
            return ToolResult.fail(f"未知工具: {name}")
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return ToolResult.fail(f"工具执行异常: {str(e)}")
