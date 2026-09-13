"""工具注册表 — 管理工具生命周期和 Schema 暴露"""

from .base import ToolBase, ToolResult
from .output import budget_result


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

    def validate(self, name: str, arguments: object) -> str | None:
        tool = self.get(name)
        if tool is None:
            return f"未知工具: {name}"
        if not isinstance(arguments, dict):
            return "工具参数必须是 JSON 对象"
        schema = tool.parameters
        for key in schema.get("required", []):
            if key not in arguments:
                return f"缺少参数: {key}"
        for key, value in arguments.items():
            prop = schema.get("properties", {}).get(key)
            if prop is None:
                return f"未知参数: {key}"
            kind = prop.get("type")
            if kind == "string" and not isinstance(value, str):
                return f"参数 {key} 必须是字符串"
            if kind == "integer" and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                return f"参数 {key} 必须是整数"
        return None

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """执行指定工具"""
        error = self.validate(name, arguments)
        if error:
            return ToolResult.fail(error)
        tool = self.get(name)
        try:
            result = await tool.execute(**arguments)
            if result.success:
                result.output = budget_result(result.output)
            else:
                result.error = budget_result(result.error)
            return result
        except Exception as e:
            return ToolResult.fail(f"工具执行异常: {str(e)}")
