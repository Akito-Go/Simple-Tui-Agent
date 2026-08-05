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
        self._session_allow_all: bool = False

    def check(self, tool_call: ToolCall, permission_level: PermissionLevel) -> PermissionDecision:
        """
        检查工具调用是否需要用户确认。

        Args:
            tool_call: 工具调用信息
            permission_level: 工具的权限级别

        Returns:
            ALLOW: 自动放行 (READ，或本会话已全部允许)
            ASK: 需要用户确认 (WRITE/SHELL)
        """
        if permission_level == PermissionLevel.READ or self._session_allow_all:
            return PermissionDecision.ALLOW

        self._pending_confirmation = (tool_call, PermissionDecision.ASK)
        return PermissionDecision.ASK

    def confirm(self) -> PermissionDecision:
        """用户确认单次操作"""
        self._pending_confirmation = None
        return PermissionDecision.ALLOW

    def deny(self) -> PermissionDecision:
        """用户拒绝"""
        self._pending_confirmation = None
        return PermissionDecision.DENY

    def enable_session_allow_all(self) -> None:
        """本次会话内 WRITE/SHELL 跳过确认（Shell 黑名单仍生效）"""
        self._session_allow_all = True
        self._pending_confirmation = None

    def reset_session_allow_all(self) -> None:
        """取消本会话全部允许"""
        self._session_allow_all = False

    @property
    def session_allow_all(self) -> bool:
        return self._session_allow_all

    @property
    def pending_tool_call(self) -> ToolCall | None:
        """当前等待确认的工具调用"""
        if self._pending_confirmation:
            return self._pending_confirmation[0]
        return None
