"""Exponential-backoff retry decorator."""

from __future__ import annotations

import functools
import time
from typing import Callable, Iterable, Type, TypeVar

T = TypeVar("T")


def with_retry(
    *,
    max_attempts: int = 3,
    backoff: float = 2.0,
    initial_delay: float = 1.0,
    exceptions: Iterable[Type[BaseException]] = (Exception,),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: total attempts (including the first call).
        backoff: multiplier for the delay between attempts.
        initial_delay: delay before the second attempt.
        exceptions: which exception types should trigger a retry.
        on_retry: optional callback(attempt_no, exception, next_delay).
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt >= max_attempts:
                        break
                    if on_retry is not None:
                        on_retry(attempt, e, delay)
                    time.sleep(delay)
                    delay *= backoff
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
