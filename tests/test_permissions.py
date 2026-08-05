"""权限控制测试 — 只读自动执行、写入需确认、拒绝后不执行"""

import pytest

from tui_agent.permissions.guard import PermissionGuard, ToolCall
from tui_agent.permissions.policy import PermissionLevel, PermissionDecision


class TestPermissionGuard:
    def test_read_auto_allow(self):
        guard = PermissionGuard()
        tool_call = ToolCall(id="call_1", name="list_dir", arguments={"path": "./"})
        decision = guard.check(tool_call, PermissionLevel.READ)
        assert decision == PermissionDecision.ALLOW

    def test_write_requires_confirmation(self):
        guard = PermissionGuard()
        tool_call = ToolCall(id="call_1", name="write_file", arguments={"path": "test.py", "content": "x"})
        decision = guard.check(tool_call, PermissionLevel.WRITE)
        assert decision == PermissionDecision.ASK
        assert guard.pending_tool_call is not None
        assert guard.pending_tool_call.name == "write_file"

    def test_shell_requires_confirmation(self):
        guard = PermissionGuard()
        tool_call = ToolCall(id="call_1", name="shell_exec", arguments={"command": "ls"})
        decision = guard.check(tool_call, PermissionLevel.SHELL)
        assert decision == PermissionDecision.ASK

    def test_user_confirm(self):
        guard = PermissionGuard()
        tool_call = ToolCall(id="call_1", name="write_file", arguments={"path": "test.py", "content": "x"})
        guard.check(tool_call, PermissionLevel.WRITE)
        decision = guard.confirm()
        assert decision == PermissionDecision.ALLOW
        assert guard.pending_tool_call is None

    def test_user_deny(self):
        guard = PermissionGuard()
        tool_call = ToolCall(id="call_1", name="write_file", arguments={"path": "test.py", "content": "x"})
        guard.check(tool_call, PermissionLevel.WRITE)
        decision = guard.deny()
        assert decision == PermissionDecision.DENY
        assert guard.pending_tool_call is None

    def test_multiple_reads_all_auto(self):
        guard = PermissionGuard()
        for name in ["list_dir", "read_file", "glob_search", "grep_search"]:
            tool_call = ToolCall(id="call_1", name=name, arguments={})
            decision = guard.check(tool_call, PermissionLevel.READ)
            assert decision == PermissionDecision.ALLOW, f"{name} should be auto-allowed"
