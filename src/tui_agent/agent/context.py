"""上下文组装 — 系统提示 + 历史消息 + 用户输入"""

from ..session.manager import SessionManager


def build_context(session: SessionManager, user_input: str) -> list[dict]:
    """
    组装完整上下文：
    1. 添加用户输入到会话
    2. 返回完整消息列表
    """
    session.add_user_message(user_input)
    return session.build_messages()
