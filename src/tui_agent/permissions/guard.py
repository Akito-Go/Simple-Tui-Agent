"""权限守卫 — READ 自动放行，WRITE/SHELL 请求确认"""

from dataclasses import dataclass

from .policy import PermissionLevel, PermissionDecision


@dataclass
class ToolCall:
    """工具调用信息"""
    id: str
    name: str
    arguments: dict


class PermissionGuard:
    """权限守卫 — 根据工具权限级别决定是否放行"""

    def __init__(self):
        self._pending_confirmation: tuple[ToolCall, PermissionDecision] | None = None

    def check(self, tool_call: ToolCall, permission_level: PermissionLevel) -> PermissionDecision:
        """
        检查工具调用是否需要用户确认。

        Args:
            tool_call: 工具调用信息
            permission_level: 工具的权限级别

        Returns:
            ALLOW: 自动放行 (READ)
            ASK: 需要用户确认 (WRITE/SHELL)
        """
        if permission_level == PermissionLevel.READ:
            return PermissionDecision.ALLOW
        else:
            self._pending_confirmation = (tool_call, PermissionDecision.ASK)
            return PermissionDecision.ASK

    def confirm(self) -> PermissionDecision:
        """用户确认"""
        self._pending_confirmation = None
        return PermissionDecision.ALLOW

    def deny(self) -> PermissionDecision:
        """用户拒绝"""
        self._pending_confirmation = None
        return PermissionDecision.DENY

    @property
    def pending_tool_call(self) -> ToolCall | None:
        """当前等待确认的工具调用"""
        if self._pending_confirmation:
            return self._pending_confirmation[0]
        return None
