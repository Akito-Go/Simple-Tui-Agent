"""工具系统测试 — 7 个工具的正常执行、错误处理、参数校验"""

import pytest

from tui_agent.tools.list_dir import ListDirTool
from tui_agent.tools.read_file import ReadFileTool
from tui_agent.tools.glob_search import GlobSearchTool
from tui_agent.tools.grep_search import GrepSearchTool
from tui_agent.tools.write_file import WriteFileTool
from tui_agent.tools.edit_file import EditFileTool
from tui_agent.tools.shell_exec import ShellExecTool
from tui_agent.tools.registry import ToolRegistry
from tui_agent.tools.base import PermissionLevel


class TestListDir:
    @pytest.mark.asyncio
    async def test_list_dir(self, temp_workspace):
        tool = ListDirTool()
        result = await tool.execute(path=str(temp_workspace))
        assert result.success
        assert "main.py" in result.output
        assert "src/" in result.output

    @pytest.mark.asyncio
    async def test_list_nonexistent(self):
        tool = ListDirTool()
        result = await tool.execute(path="./nonexistent_dir_12345")
        assert not result.success
        assert "不存在" in result.error

    def test_permission_level(self):
        assert ListDirTool.permission_level == PermissionLevel.READ


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_full_file(self, temp_workspace):
        tool = ReadFileTool()
        result = await tool.execute(path=str(temp_workspace / "main.py"))
        assert result.success
        assert "print('hello')" in result.output

    @pytest.mark.asyncio
    async def test_read_line_range(self, temp_workspace):
        tool = ReadFileTool()
        result = await tool.execute(
            path=str(temp_workspace / "utils.py"), start_line=1, end_line=1
        )
        assert result.success
        assert "def add" in result.output

    @pytest.mark.asyncio
    async def test_read_nonexistent(self):
        tool = ReadFileTool()
        result = await tool.execute(path="./nonexistent.txt")
        assert not result.success


class TestGlobSearch:
    @pytest.mark.asyncio
    async def test_glob_py_files(self, temp_workspace):
        tool = GlobSearchTool()
        result = await tool.execute(pattern=f"{temp_workspace}/**/*.py")
        assert result.success
        assert "main.py" in result.output
        assert "utils.py" in result.output

    @pytest.mark.asyncio
    async def test_glob_no_match(self, temp_workspace):
        tool = GlobSearchTool()
        result = await tool.execute(pattern=f"{temp_workspace}/**/*.rs")
        assert result.success
        assert "无匹配" in result.output


class TestGrepSearch:
    @pytest.mark.asyncio
    async def test_grep_function_def(self, temp_workspace):
        tool = GrepSearchTool()
        result = await tool.execute(pattern="def add", path=str(temp_workspace))
        assert result.success
        assert "def add" in result.output

    @pytest.mark.asyncio
    async def test_grep_no_match(self, temp_workspace):
        tool = GrepSearchTool()
        result = await tool.execute(
            pattern="nonexistent_pattern_xyz", path=str(temp_workspace)
        )
        assert result.success
        assert "无匹配" in result.output


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_create_new_file(self, temp_workspace):
        tool = WriteFileTool()
        filepath = temp_workspace / "new_file.py"
        result = await tool.execute(path=str(filepath), content="print('hello')")
        assert result.success
        assert filepath.exists()
        assert filepath.read_text() == "print('hello')"

    @pytest.mark.asyncio
    async def test_overwrite_file(self, temp_workspace):
        tool = WriteFileTool()
        filepath = temp_workspace / "main.py"
        result = await tool.execute(path=str(filepath), content="new content")
        assert result.success
        assert filepath.read_text() == "new content"

    def test_permission_level(self):
        assert WriteFileTool.permission_level == PermissionLevel.WRITE


class TestEditFile:
    @pytest.mark.asyncio
    async def test_replace_string(self, temp_workspace):
        tool = EditFileTool()
        filepath = temp_workspace / "src" / "lib.py"
        result = await tool.execute(
            path=str(filepath),
            old_string="VERSION = '1.0'",
            new_string="VERSION = '2.0'",
        )
        assert result.success
        assert "VERSION = '2.0'" in filepath.read_text()

    @pytest.mark.asyncio
    async def test_old_string_not_found(self, temp_workspace):
        tool = EditFileTool()
        result = await tool.execute(
            path=str(temp_workspace / "main.py"),
            old_string="nonexistent_content",
            new_string="replacement",
        )
        assert not result.success
        assert "未找到" in result.error


class TestShellExec:
    @pytest.mark.asyncio
    async def test_echo(self):
        tool = ShellExecTool()
        result = await tool.execute(command="echo hello")
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_command_fails(self):
        tool = ShellExecTool()
        result = await tool.execute(command="nonexistent_command_xyz 2>&1")
        assert not result.success
        assert "退出码" in result.error

    def test_permission_level(self):
        assert ShellExecTool.permission_level == PermissionLevel.SHELL


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = ListDirTool()
        registry.register(tool)
        assert registry.get("list_dir") is tool

    def test_to_openai_schemas(self):
        registry = ToolRegistry()
        registry.register(ListDirTool())
        registry.register(ReadFileTool())
        schemas = registry.to_openai_schemas()
        assert len(schemas) == 2
        assert schemas[0]["name"] == "list_dir"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("unknown_tool", {})
        assert not result.success
        assert "未知工具" in result.error


async def test_grep_filters_literal_case_and_nested_paths(temp_workspace):
    from pathlib import Path
    root = Path(temp_workspace)
    (root / 'nested').mkdir(exist_ok=True)
    (root / 'nested' / 'chosen.py').write_text('A[B]\naXb\n')
    (root / 'other.txt').write_text('A[B]\n')
    tool = GrepSearchTool()
    result = await tool.execute('a[b]', glob='*.py', literal=True, ignore_case=True)
    assert result.success
    assert 'chosen.py:1:' in result.output
    assert 'other.txt' not in result.output and 'aXb' not in result.output
    result = await tool.execute('A[B]', glob='nested/**/*.py', literal=True)
    assert result.success and 'chosen.py' in result.output
    result = await tool.execute('a[b]', glob='*.py', literal=True)
    assert 'chosen.py' not in result.output


@pytest.mark.parametrize("encoding", ["cp1252", "gbk"])
async def test_search_worker_uses_utf8(temp_workspace, monkeypatch, encoding):
    monkeypatch.setenv("PYTHONIOENCODING", encoding)
    (temp_workspace / "chinese.txt").write_text("中文内容\n", encoding="utf-8")
    result = await GrepSearchTool().execute("中文", path=str(temp_workspace))
    assert result.success, result.error
    assert "中文内容" in result.output
    result = await GlobSearchTool().execute(pattern="*.no-such-extension")
    assert result.success, result.error
    assert "无匹配" in result.output
