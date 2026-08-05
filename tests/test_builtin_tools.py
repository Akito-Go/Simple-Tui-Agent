"""内置工具注册测试"""

from tui_agent.tools.builtin import create_default_registry


def test_create_default_registry_has_seven_tools():
    registry = create_default_registry()
    names = set(registry.list_names())
    assert names == {
        "list_dir",
        "read_file",
        "glob_search",
        "grep_search",
        "write_file",
        "edit_file",
        "shell_exec",
    }
