"""超时控制 + 指数退避重试"""

import asyncio
from typing import Callable, Awaitable, TypeVar

T = TypeVar("T")

# 可重试的错误类型
RETRYABLE_ERRORS = (
    asyncio.TimeoutError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    OSError,
)


def _extract_status_code(error: Exception) -> int | None:
    """从 SDK 异常中提取 HTTP 状态码（若有）"""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(error, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def is_retryable(error: Exception) -> bool:
    """判断错误是否可重试（网络/超时/429/5xx；不含认证等 4xx）"""
    status = _extract_status_code(error)
    if status is not None:
        if status in (408, 429, 500, 502, 503, 504):
            return True
        if 400 <= status < 500:
            return False
    return isinstance(error, RETRYABLE_ERRORS)


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    """
    带指数退避的重试执行。

    Args:
        fn: 异步可调用对象
        max_retries: 最大重试次数
        base_delay: 基础延迟 (秒)，每次重试延迟翻倍

    Returns:
        函数返回值

    Raises:
        最后一次尝试的异常（如果所有重试都失败）
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries and is_retryable(e):
                delay = base_delay * (2**attempt)
                await asyncio.sleep(delay)
            else:
                raise

    # 理论上不会到这里，但保留作为安全措施
    assert last_error is not None
    raise last_error
