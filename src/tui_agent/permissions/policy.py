"""权限策略定义"""

from enum import Enum


class PermissionLevel(str, Enum):
    """权限级别 — 与 tools/base.py 保持一致"""
    READ = "read"
    WRITE = "write"
    SHELL = "shell"


class PermissionDecision(str, Enum):
    """权限决策结果"""
    ALLOW = "allow"  # 允许执行
    DENY = "deny"  # 拒绝执行
    ASK = "ask"  # 需要用户确认
