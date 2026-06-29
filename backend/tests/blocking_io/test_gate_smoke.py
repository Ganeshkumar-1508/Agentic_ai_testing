"""Smoke test: blockbuster blocks sync IO on asyncio loop.

Ported from DeerFlow (MIT License, Bytedance Ltd.).
"""

import asyncio
import time

import pytest

try:
    from blockbuster import BlockingError, blockbuster_ctx

    _HAS_BLOCKBUSTER = True
except ImportError:
    _HAS_BLOCKBUSTER = False


def test_module_importable() -> None:
    if not _HAS_BLOCKBUSTER:
        pytest.skip("blockbuster not installed")


def test_blockbuster_context_manager_works() -> None:
    if not _HAS_BLOCKBUSTER:
        pytest.skip("blockbuster not installed")
    with blockbuster_ctx():
        pass


@pytest.mark.asyncio
async def test_async_sleep_allowed() -> None:
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_blocking_sleep_detected() -> None:
    if not _HAS_BLOCKBUSTER:
        pytest.skip("blockbuster not installed")
    with blockbuster_ctx():
        with pytest.raises(BlockingError):
            time.sleep(0.01)
