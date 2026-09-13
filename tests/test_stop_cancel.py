"""Esc//stop 取消：CancelledError 必须复位运行状态，避免卡在「正在终止」"""

import asyncio
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from tui_agent.tui.app import TuiAgentApp


class _FakeChat:
    def __init__(self) -> None:
        self._streaming_widget = object()
        self.messages: list[str] = []
        self.finished = False
        self.tool_running = True

    def finish_streaming(self) -> str:
        self.finished = True
        self._streaming_widget = None
        return ""

    def add_system_message(self, message: str) -> None:
        self.messages.append(message)

    def add_error(self, message: str) -> None:
        self.messages.append(message)

    def start_streaming(self) -> None:
        self._streaming_widget = object()

    def append_streaming(self, text: str) -> None:
        pass

    def show_tool_running(self, *args, **kwargs) -> None:
        pass

    def add_tool_result(self, *args, **kwargs) -> None:
        pass

    def add_permission_denied(self, *args, **kwargs) -> None:
        pass

    def add_assistant_message(self, *args, **kwargs) -> None:
        pass

    def hide_tool_running(self) -> None:
        self.tool_running = False

    def hide_thinking(self) -> None:
        pass


@pytest.mark.asyncio
async def test_process_events_cancel_resets_running_flag():
    """cancel 注入 CancelledError 后应复位 _agent_running，并提示已终止"""
    app = TuiAgentApp.__new__(TuiAgentApp)
    app.config = None
    app.agent_loop = None
    app.session = None
    app._waiting_confirmation = False
    app._agent_running = True
    app._stop_requested = True
    app._agent_task = None
    app._welcome_shown = False
    app._update_header = MagicMock()  # type: ignore[method-assign]

    fake_chat = _FakeChat()
    fake_screen = MagicMock()
    fake_screen.query_one.return_value = fake_chat

    async def hanging_events():
        await asyncio.Event().wait()
        yield  # pragma: no cover

    with patch.object(TuiAgentApp, "screen", new_callable=PropertyMock) as mock_screen:
        mock_screen.return_value = fake_screen
        task = asyncio.create_task(app._process_events(hanging_events()))
        app._agent_task = task
        await asyncio.sleep(0)
        task.cancel()
        await task

    assert app._agent_running is False
    assert app._stop_requested is False
    assert app._agent_task is None
    assert fake_chat.finished is True
    assert fake_chat.tool_running is False
    assert any("终止" in m for m in fake_chat.messages)


@pytest.mark.asyncio
async def test_finalize_stopped_clears_flags():
    app = TuiAgentApp.__new__(TuiAgentApp)
    app.config = None
    app.session = None
    app._agent_running = True
    app._stop_requested = True
    app._agent_task = object()  # type: ignore[assignment]
    app._update_header = MagicMock()  # type: ignore[method-assign]

    chat = _FakeChat()
    app._finalize_stopped(chat)  # type: ignore[arg-type]

    assert app._agent_running is False
    assert app._stop_requested is False
    assert app._agent_task is None
    assert any("终止" in m for m in chat.messages)
