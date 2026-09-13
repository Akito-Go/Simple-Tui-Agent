"""会话加载测试"""

import pytest

from tui_agent.session.manager import SessionManager
from tui_agent.session.storage import save_session
from tui_agent.session.loader import list_sessions, load_session


class TestListSessions:
    def test_list_sessions_filters_session_files(self, tmp_path, monkeypatch):
        """仅列出 session_*.jsonl"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.loader.get_log_dir", lambda: log_dir)
        monkeypatch.setattr("tui_agent.session.storage.get_log_dir", lambda: log_dir)

        # 创建 session 文件
        s = SessionManager(session_id="session_test1")
        s.add_user_message("hi")
        save_session(s)

        # 创建非 session 文件
        (log_dir / "agent_2026-01-01.jsonl").write_text('{"type":"log"}\n')

        sessions = list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert "session_test1" in ids
        assert all(not sid.startswith("agent_") for sid in ids)

    def test_list_sessions_empty_dir(self, tmp_path, monkeypatch):
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.loader.get_log_dir", lambda: log_dir)

        sessions = list_sessions()
        assert sessions == []


class TestLoadSession:
    def test_load_session_restores_messages(self, tmp_path, monkeypatch):
        """完整还原会话消息"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.storage.get_log_dir", lambda: log_dir)

        s = SessionManager(session_id="session_restore_test", model="deepseek/deepseek-v4-flash")
        s.add_user_message("hello")
        s.add_assistant_message("hi there")
        s.add_user_message("list files")
        s.add_assistant_message("", tool_calls=[
            {"id": "call_1", "function": {"name": "list_dir", "arguments": '{"path": "."}'}}
        ])
        s.add_tool_result("call_1", "list_dir", "src/\ntests/")
        s.add_assistant_message("Found 2 items.")
        save_session(s)

        restored = load_session(str(log_dir / "session_restore_test.jsonl"), model="deepseek/deepseek-v4-flash")
        assert restored is not None
        messages = restored.build_messages()
        # system + user + assistant + user + assistant(tool_call) + tool + assistant
        assert len(messages) == 7
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_load_session_restores_turn_count(self, tmp_path, monkeypatch):
        """恢复 turn_count"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        monkeypatch.setattr("tui_agent.session.storage.get_log_dir", lambda: log_dir)

        s = SessionManager(session_id="session_turns")
        s.increment_turn()
        s.increment_turn()
        s.increment_turn()
        save_session(s)

        restored = load_session(str(log_dir / "session_turns.jsonl"))
        assert restored is not None
        assert restored.turn_count == 3

    def test_load_nonexistent_file(self):
        session = load_session("/nonexistent/path.jsonl")
        assert session is None

    def test_load_legacy_jsonl_with_empty_tool_call_id(self, tmp_path, monkeypatch):
        """旧日志无 tool_call_id、tool_result 在 assistant 前均可还原"""
        log_dir = tmp_path / ".tui-agent" / "logs"
        log_dir.mkdir(parents=True)
        filepath = log_dir / "session_legacy.jsonl"
        filepath.write_text(
            "\n".join([
                '{"type":"meta","session_id":"session_legacy","model":"deepseek/deepseek-v4-flash","turn_count":1,"timestamp":"t"}',
                '{"type":"user","content":"list files","timestamp":"t"}',
                '{"type":"tool_call","tool_call_id":"","name":"list_dir","arguments":"{\\"path\\": \\".\\"}","timestamp":"t"}',
                '{"type":"tool_result","tool_call_id":"","name":"list_dir","result":"src/","timestamp":"t"}',
                '{"type":"assistant","content":"done","timestamp":"t"}',
            ]) + "\n",
            encoding="utf-8",
        )

        restored = load_session(str(filepath), model="deepseek/deepseek-v4-flash")
        messages = restored.build_messages()
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["tool_calls"][0]["id"] == "call_1"
        assert messages[3]["role"] == "tool"
        assert messages[3]["tool_call_id"] == "call_1"
        assert messages[4]["content"] == "done"

    def test_load_skips_orphan_tool_results(self, tmp_path):
        """跳过无对应 tool_call 的孤立 tool_result（旧重复写入日志）"""
        filepath = tmp_path / "session_orphan.jsonl"
        filepath.write_text(
            "\n".join([
                '{"type":"meta","session_id":"session_orphan","model":"m","turn_count":0,"timestamp":"t"}',
                '{"type":"user","content":"hi","timestamp":"t"}',
                '{"type":"tool_call","tool_call_id":"","name":"list_dir","arguments":"{}","timestamp":"t"}',
                '{"type":"tool_result","tool_call_id":"","name":"list_dir","result":"a","timestamp":"t"}',
                '{"type":"tool_result","tool_call_id":"","name":"list_dir","result":"dup","timestamp":"t"}',
                '{"type":"tool_result","tool_call_id":"","name":"list_dir","result":"dup2","timestamp":"t"}',
                '{"type":"assistant","content":"ok","timestamp":"t"}',
            ]) + "\n",
            encoding="utf-8",
        )

        restored = load_session(str(filepath))
        tool_messages = [m for m in restored.build_messages() if m["role"] == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["content"] == "a"

    def test_load_merges_consecutive_assistant_messages(self, tmp_path):
        """JSONL 中穿插的纯 assistant 行应合并，避免 API bad_request"""
        filepath = tmp_path / "session_merge.jsonl"
        filepath.write_text(
            "\n".join([
                '{"type":"meta","session_id":"session_merge","model":"m","turn_count":0,"timestamp":"t"}',
                '{"type":"user","content":"hi","timestamp":"t"}',
                '{"type":"tool_call","tool_call_id":"","name":"list_dir","arguments":"{}","timestamp":"t"}',
                '{"type":"assistant","content":"part one","timestamp":"t"}',
                '{"type":"tool_result","tool_call_id":"","name":"list_dir","result":"ok","timestamp":"t"}',
                '{"type":"assistant","content":"part two","timestamp":"t"}',
                '{"type":"assistant","content":"part three","timestamp":"t"}',
            ]) + "\n",
            encoding="utf-8",
        )

        restored = load_session(str(filepath))
        messages = restored.build_messages()
        prev = None
        for msg in messages:
            role = msg.get("role")
            if role == "assistant" and prev == "assistant":
                pytest.fail("存在连续 assistant 消息")
            prev = role

        assistants = [m for m in messages if m["role"] == "assistant"]
        assert len(assistants) == 2
        assert assistants[0]["tool_calls"]
        assert "part two" in assistants[1]["content"]
        assert "part three" in assistants[1]["content"]

    def test_load_new_format_content_before_tool_call(self, tmp_path):
        """新 JSONL 格式：assistant 文本在 tool_call 之前"""
        filepath = tmp_path / "session_newfmt.jsonl"
        filepath.write_text(
            "\n".join([
                '{"type":"meta","session_id":"session_newfmt","model":"m","turn_count":0,"timestamp":"t"}',
                '{"type":"user","content":"hi","timestamp":"t"}',
                '{"type":"assistant","content":"先看目录","timestamp":"t"}',
                '{"type":"tool_call","tool_call_id":"call_1","name":"list_dir","arguments":"{}","timestamp":"t"}',
                '{"type":"tool_result","tool_call_id":"call_1","name":"list_dir","result":"ok","timestamp":"t"}',
            ]) + "\n",
            encoding="utf-8",
        )

        restored = load_session(str(filepath))
        messages = restored.build_messages()
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "先看目录"
        assert messages[2]["tool_calls"][0]["id"] == "call_1"
        assert messages[3]["role"] == "tool"
