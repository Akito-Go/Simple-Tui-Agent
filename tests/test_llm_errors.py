"""服务过载重试及错误提示去重。"""

import pytest

from tui_agent.llm.errors import format_llm_error
from tui_agent.llm.retry import is_retryable, with_retry


class StatusError(Exception):
    def __init__(self, status):
        super().__init__('Our servers are currently overloaded. Please try again later.')
        self.status_code = status


@pytest.mark.parametrize('status,expected', [(529, True), (503, True), (500, True), (429, True), (408, True), (401, False), (403, False), (400, False)])
def test_status_retry_classification(status, expected):
    assert is_retryable(StatusError(status)) is expected


async def test_overload_retries_and_respects_limit():
    attempts = 0
    async def request():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise StatusError(529)
        return 'ok'
    assert await with_retry(request, max_retries=2, base_delay=0) == 'ok'
    assert attempts == 3
    attempts = 0
    with pytest.raises(StatusError):
        await with_retry(request, max_retries=1, base_delay=0)
    assert attempts == 2


def test_error_prefix_is_idempotent_and_overload_is_readable():
    error = format_llm_error(StatusError(529))
    assert '模型服务暂时过载' in error
    assert format_llm_error(RuntimeError(error)) == error
    assert format_llm_error(RuntimeError('LLM 请求失败: LLM 请求失败: detail')) == 'LLM 请求失败: detail'
