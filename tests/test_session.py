"""会话管理测试 — 消息累积、上下文组装、JSONL 持久化"""

import json
import pytest

from tui_agent.session.manager import SessionManager
from tui_agent.session.storage import save_session


class TestSessionManager:
    def test_initial_state(self):
        session = SessionManager(model="deepseek/deepseek-v4-flash")
        messages = session.build_messages()
        assert len(messages) == 1  # 系统提示
        assert messages[0]["role"] == "system"
        assert "deepseek/deepseek-v4-flash" in messages[0]["content"]
        assert "Claude" in messages[0]["content"]
        assert session.turn_count == 0

    def test_system_prompt_discourages_idle_tool_use(self):
        prompt = SessionManager.build_system_prompt("test-model")
        assert "不要调用任何工具" in prompt
        assert "主动扫描整个仓库" in prompt
        assert "会自动执行" in prompt

    def test_set_model_updates_system_prompt(self):
        session = SessionManager(model="moonshot/kimi-k2.5")
        session.set_model("xiaomi/mimo-v2.5-pro")
        prompt = session.build_messages()[0]["content"]
        assert "xiaomi/mimo-v2.5-pro" in prompt
        assert "moonshot/kimi-k2.5" not in prompt

    def test_add_user_message(self):
        session = SessionManager()
        session.add_user_message("hello")
        messages = session.build_messages()
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_add_assistant_message(self):
        session = SessionManager()
        session.add_assistant_message("hi there")
        messages = session.build_messages()
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "hi there"

    def test_add_tool_result(self):
        session = SessionManager()
        session.add_tool_result("call_1", "list_dir", "src/\ntests/")
        messages = session.build_messages()
        assert messages[1]["role"] == "tool"
        assert messages[1]["name"] == "list_dir"
        assert "src/" in messages[1]["content"]

    def test_multi_turn_context(self):
        session = SessionManager()
        session.add_user_message("list files")
        session.add_assistant_message("", tool_calls=[
            {"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}
        ])
        session.add_tool_result("call_1", "list_dir", "src/\ntests/")
        session.add_assistant_message("Found 2 items.")

        messages = session.build_messages()
        # system + user + assistant(tool_call) + tool + assistant
        assert len(messages) == 5

    def test_clear_session(self):
        session = SessionManager()
        session.add_user_message("hello")
        session.add_assistant_message("hi")
        session.clear()

        messages = session.build_messages()
        assert len(messages) == 1  # 只有系统提示
        assert session.turn_count == 0

    def test_increment_turn(self):
        session = SessionManager()
        session.increment_turn()
        session.increment_turn()
        assert session.turn_count == 2

    def test_to_log_records(self):
        session = SessionManager()
        session.add_user_message("hello")
        session.add_assistant_message("hi there")

        records = session.to_log_records()
        # meta + user + assistant
        assert len(records) == 3
        assert records[0]["type"] == "meta"
        assert records[1]["type"] == "user"
        assert records[2]["type"] == "assistant"

    def test_to_log_records_tool_call_id(self):
        session = SessionManager()
        session.add_assistant_message("先看目录", tool_calls=[
            {"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "./"}'}}
        ])
        session.add_tool_result("call_1", "list_dir", "src/")

        records = session.to_log_records()
        types = [r["type"] for r in records if r["type"] != "meta"]
        assert types == ["assistant", "tool_call", "tool_result"]
        tool_call_records = [r for r in records if r["type"] == "tool_call"]
        tool_result_records = [r for r in records if r["type"] == "tool_result"]
        assert len(tool_call_records) == 1
        assert tool_call_records[0]["tool_call_id"] == "call_1"
        assert len(tool_result_records) == 1
        assert tool_result_records[0]["tool_call_id"] == "call_1"

    def test_to_log_records_incremental(self):
        session = SessionManager()
        session.add_user_message("msg1")
        session.add_assistant_message("reply1")

        # 首次导出
        records1 = session.to_log_records(since_index=1)
        assert len(records1) >= 2

        # 模拟已保存
        session._saved_message_count = 3  # system(0) + user(1) + assistant(2)

        session.add_user_message("msg2")
        records2 = session.to_log_records(since_index=3)
        # 只包含 msg2，不含 meta（since_index > 1）
        assert len(records2) == 1
        assert records2[0]["content"] == "msg2"


class TestSessionStorage:
    def test_save_session(self, tmp_path, monkeypatch):
        """测试会话持久化"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.storage.get_log_dir", lambda: log_dir)

        session = SessionManager(session_id="test_session")
        session.add_user_message("hello")
        session.add_assistant_message("hi")

        filepath = save_session(session)
        assert filepath.exists()

        with open(filepath, "r") as f:
            lines = f.readlines()
        # meta + user + assistant
        assert len(lines) == 3
        for line in lines:
            record = json.loads(line)
            assert "type" in record
            assert "timestamp" in record

    def test_save_session_incremental(self, tmp_path, monkeypatch):
        """测试增量保存不重复"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.storage.get_log_dir", lambda: log_dir)

        session = SessionManager(session_id="test_inc")
        session.add_user_message("msg1")
        session.add_assistant_message("reply1")

        # 第一次保存
        save_session(session)
        # 第二次保存（新增消息）
        session.add_user_message("msg2")
        session.add_assistant_message("reply2")
        save_session(session)

        with open(log_dir / "test_inc.jsonl", "r") as f:
            lines = f.readlines()
        # meta + user1 + assistant1 + user2 + assistant2 = 5
        assert len(lines) == 5
        user_msgs = [json.loads(l)["content"] for l in lines if json.loads(l)["type"] == "user"]
        assert user_msgs == ["msg1", "msg2"]

    def test_save_session_incremental_with_tool_calls(self, tmp_path, monkeypatch):
        """含 tool_call 的 assistant 消息增量保存不应重复"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.storage.get_log_dir", lambda: log_dir)

        session = SessionManager(session_id="test_tool_inc")
        session.add_user_message("list")
        session.add_assistant_message("ok", tool_calls=[
            {"id": "call_1", "function": {"name": "list_dir", "arguments": "{}"}}
        ])
        session.add_tool_result("call_1", "list_dir", "src/")
        save_session(session)

        session.add_user_message("next")
        save_session(session)

        with open(log_dir / "test_tool_inc.jsonl", "r") as f:
            lines = f.readlines()
        users = [json.loads(l)["content"] for l in lines if json.loads(l)["type"] == "user"]
        assert users == ["list", "next"]
        assert len(lines) == 6  # meta + 4 from first save + 1 user
