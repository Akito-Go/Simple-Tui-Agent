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


def is_retryable(error: Exception) -> bool:
    """判断错误是否可重试（仅网络/超时错误，不含认证错误）"""
    # HTTP 4xx 错误不应重试
    if hasattr(error, "status_code"):
        status = getattr(error, "status_code", 0)
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
