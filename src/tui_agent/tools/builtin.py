"""内置工具注册"""

from .edit_file import EditFileTool
from .glob_search import GlobSearchTool
from .grep_search import GrepSearchTool
from .list_dir import ListDirTool
from .read_file import ReadFileTool
from .registry import ToolRegistry
from .shell_exec import ShellExecTool
from .write_file import WriteFileTool


def create_default_registry() -> ToolRegistry:
    """创建并注册全部内置工具"""
    registry = ToolRegistry()
    for tool in (
        ListDirTool(),
        ReadFileTool(),
        GlobSearchTool(),
        GrepSearchTool(),
        WriteFileTool(),
        EditFileTool(),
        ShellExecTool(),
    ):
        registry.register(tool)
    return registry
