"""上下文压缩测试"""

import pytest

from tui_agent.session.manager import SessionManager
from tui_agent.session.compressor import estimate_tokens


class TestEstimateTokens:
    def test_estimate_small(self):
        msgs = [{"role": "system", "content": "hello"}]
        assert estimate_tokens(msgs) > 0

    def test_estimate_grows_with_messages(self):
        small = [{"role": "user", "content": "hi"}]
        large = [{"role": "user", "content": "hi"}] * 100
        assert estimate_tokens(large) > estimate_tokens(small) * 10

    def test_cjk_counts_higher_than_ascii(self):
        ascii_msg = [{"role": "user", "content": "abcd" * 20}]
        cjk_msg = [{"role": "user", "content": "中文测试内容示例" * 5}]
        assert estimate_tokens(cjk_msg) > estimate_tokens(ascii_msg)


class TestCompressIfNeeded:
    @pytest.mark.asyncio
    async def test_below_threshold_skips(self):
        """未超阈值不压缩"""
        session = SessionManager()
        session.add_user_message("hi")
        session.add_assistant_message("hello")

        from tui_agent.session.compressor import compress_if_needed
        # 使用 Mock provider
        from tests.conftest import MockLLMProvider
        provider = MockLLMProvider()

        result = await compress_if_needed(session, provider, threshold=99999)
        assert result is False
        assert len(session.messages) == 3  # system + user + assistant

    @pytest.mark.asyncio
    async def test_above_threshold_compresses(self):
        """超阈值触发压缩"""
        session = SessionManager()
        # 添加大量消息模拟超阈值
        for i in range(50):
            session.add_user_message(f"message {i}")
            session.add_assistant_message(f"reply {i}")

        from tui_agent.session.compressor import compress_if_needed
        from tests.conftest import MockLLMProvider, MockLLMResponse
        provider = MockLLMProvider()
        provider.set_responses([MockLLMResponse(content="这是摘要")])

        original_count = len(session.messages)
        result = await compress_if_needed(session, provider, threshold=100)
        assert result is True
        assert len(session.messages) < original_count

    @pytest.mark.asyncio
    async def test_preserves_recent_turns(self):
        """保留最近 2 轮对话"""
        session = SessionManager()
        # 前 10 轮
        for i in range(10):
            session.add_user_message(f"old {i}")
            session.add_assistant_message(f"old reply {i}")
        # 最近 2 轮
        session.add_user_message("recent 1")
        session.add_assistant_message("recent reply 1")
        session.add_user_message("recent 2")
        session.add_assistant_message("recent reply 2")

        from tui_agent.session.compressor import compress_if_needed
        from tests.conftest import MockLLMProvider, MockLLMResponse
        provider = MockLLMProvider()
        provider.set_responses([MockLLMResponse(content="摘要内容")])

        await compress_if_needed(session, provider, threshold=100)

        messages = session.build_messages()
        # 最近 2 轮应该保留
        assert any("recent 1" in str(m) for m in messages)
        assert any("recent 2" in str(m) for m in messages)
