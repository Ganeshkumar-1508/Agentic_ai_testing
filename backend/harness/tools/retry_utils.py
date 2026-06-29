"""Retry utilities with jittered backoff."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable


async def retry_with_backoff(
    fn: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """Retry a coroutine with exponential backoff and jitter."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retryable_exceptions as e:
            last_exc = e
            if attempt < max_retries:
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                jitter = delay * 0.1 * random.random()
                await asyncio.sleep(delay + jitter)
    raise last_exc  # type: ignore


async def retry_with_backoff_sync(
    fn: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> Any:
    """Retry a sync function with backoff (runs in executor)."""
    loop = asyncio.get_event_loop()

    def _run():
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    delay = min(base_delay * (2.0 ** attempt), max_delay)
                    jitter = delay * 0.1 * random.random()
                    time.sleep(delay + jitter)
        raise last_exc  # type: ignore

    return await loop.run_in_executor(None, _run)
