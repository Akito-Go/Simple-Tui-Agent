"""目录浏览工具"""


from .base import ToolBase, ToolResult, PermissionLevel
from .workspace import resolve_in_workspace


class ListDirTool(ToolBase):
    name = "list_dir"
    description = "列出指定目录下的文件和子目录列表"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要列出的目录路径，默认为当前目录",
            }
        },
        "required": [],
    }
    permission_level = PermissionLevel.READ

    async def execute(self, path: str = "./") -> ToolResult:
        try:
            p, err = resolve_in_workspace(path)
            if err:
                return ToolResult.fail(err)
            assert p is not None
            if not p.exists():
                return ToolResult.fail(f"目录不存在: {path}")
            if not p.is_dir():
                return ToolResult.fail(f"路径不是目录: {path}")

            items = []
            for item in sorted(p.iterdir()):
                suffix = "/" if item.is_dir() else ""
                items.append(f"{item.name}{suffix}")

            max_items = 100
            if len(items) > max_items:
                shown = items[:max_items]
                footer = f"\n(共 {len(items)} 项，显示前 {max_items} 项)"
                return ToolResult.ok("\n".join(shown) + footer)

            return ToolResult.ok("\n".join(items) if items else "(空目录)")
        except PermissionError as e:
            return ToolResult.fail(f"权限不足: {e}")
        except Exception as e:
            return ToolResult.fail(f"列出目录失败: {e}")
