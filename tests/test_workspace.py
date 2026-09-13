"""工作区沙箱测试"""

import pytest

from tui_agent.tools.workspace import (
    get_workspace_root,
    set_workspace_root,
    reset_workspace_root,
    resolve_in_workspace,
)
from tui_agent.tools.read_file import ReadFileTool
from tui_agent.tools.write_file import WriteFileTool
from tui_agent.tools.shell_exec import ShellExecTool


@pytest.fixture
def workspace(tmp_path):
    reset_workspace_root()
    set_workspace_root(tmp_path)
    yield tmp_path
    reset_workspace_root()


class TestWorkspaceResolve:
    def test_relative_path_inside(self, workspace):
        (workspace / "a.py").write_text("ok")
        resolved, err = resolve_in_workspace("a.py")
        assert err is None
        assert resolved == (workspace / "a.py").resolve()

    def test_traversal_blocked(self, workspace):
        outside = workspace.parent / "outside.txt"
        outside.write_text("secret")
        _, err = resolve_in_workspace(f"../{outside.name}")
        assert err is not None
        assert "工作区" in err

    def test_absolute_outside_blocked(self, workspace):
        outside = workspace.parent / "totally_outside" / "secret.txt"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("secret")
        _, err = resolve_in_workspace(str(outside))
        assert err is not None


class TestWorkspaceTools:
    @pytest.mark.asyncio
    async def test_read_outside_workspace(self, workspace):
        outside = workspace.parent / "outside_read.txt"
        outside.write_text("secret")
        tool = ReadFileTool()
        result = await tool.execute(path=str(outside))
        assert not result.success
        assert "工作区" in result.error

    @pytest.mark.asyncio
    async def test_write_outside_workspace(self, workspace):
        target = workspace.parent / "outside_write.txt"
        tool = WriteFileTool()
        result = await tool.execute(path=str(target), content="x")
        assert not result.success
        assert "工作区" in result.error

    @pytest.mark.asyncio
    async def test_shell_cwd_outside_workspace(self, workspace):
        tool = ShellExecTool()
        result = await tool.execute(command="echo hi", cwd=str(workspace.parent))
        assert not result.success
        assert "工作区" in result.error

    @pytest.mark.asyncio
    async def test_shell_defaults_to_workspace(self, workspace):
        (workspace / "marker.txt").write_text("in workspace")
        tool = ShellExecTool()
        result = await tool.execute(command="pwd")
        assert result.success
        assert str(get_workspace_root()) in result.output
