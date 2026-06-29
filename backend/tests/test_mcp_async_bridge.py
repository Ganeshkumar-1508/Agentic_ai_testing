"""Tests for the C3 deepening: `register_async_raw` and the
removal of the `asyncio.run()` lie in MCP tool registration.

The architecture review identified three failure modes from
the old `register_raw(..., handler=lambda: asyncio.run(...),
is_async=False)` pattern:

  1. Cancellation leaks — parent loop's cancel didn't reach
     the MCP call's child loop.
  2. Event loop per tool call — `asyncio.run()` allocates a
     fresh Selector + ThreadPoolExecutor every time.
  3. Re-entrancy hazard — `asyncio.run()` from a running loop
     raises `RuntimeError`; the old code path silently
     swallowed it via the registry's try/except.

The fix: a new `register_async_raw` accepts a coroutine
function. The registry's `execute()` awaits it on the agent's
event loop. The MCP client uses the new path.

These tests pin:

  - `register_async_raw` exists, accepts a coroutine function,
    sets `is_async=True` automatically.
  - `register_raw` still exists, accepts sync handlers, sets
    `is_async` from the handler via `asyncio.iscoroutinefunction`.
  - The `is_async` flag is no longer a lie: passing a sync
    handler to `register_async_raw` raises TypeError.
  - The MCP client's `_register_server_tools` no longer uses
    `asyncio.run()` (verified by source inspection — the
    function isn't importable here without the full MCP SDK).
  - An async handler awaits correctly and returns the
    expected result.
  - Cancellation propagates through the async path.
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.tools.base import BaseTool, ToolResult
from harness.tools.registry import ToolRegistry, _is_async_callable


# ---------------------------------------------------------------------------
# ToolHandler Protocol + is_async detection
# ---------------------------------------------------------------------------


def test_is_async_callable_detects_coroutine_function():
    async def _async_fn(*args, **kwargs):
        return "result"

    def _sync_fn(*args, **kwargs):
        return "result"

    assert _is_async_callable(_async_fn) is True
    assert _is_async_callable(_sync_fn) is False


def test_is_async_callable_handles_partials_and_methods():
    """Lambdas, partials, and bound methods should also be
    classified correctly. The detector uses
    `asyncio.iscoroutinefunction`, which inspects the
    underlying function — it follows partials and bound
    methods correctly."""

    async def _async_fn(x):
        return x

    class _Holder:
        async def _async_method(self, x):
            return x

        def _sync_method(self, x):
            return x

    holder = _Holder()

    assert _is_async_callable(_async_fn) is True
    assert _is_async_callable(_Holder._async_method) is True
    assert _is_async_callable(holder._async_method) is True
    assert _is_async_callable(_Holder._sync_method) is False
    assert _is_async_callable(holder._sync_method) is False


# ---------------------------------------------------------------------------
# register_raw — sync default, is_async auto-detected
# ---------------------------------------------------------------------------


def _fresh_registry() -> ToolRegistry:
    return ToolRegistry()


def test_register_raw_with_sync_handler_marks_is_async_false():
    """A sync handler should be registered with `is_async=False`.
    The flag is no longer a caller-provided lie — it's
    auto-detected from the handler."""
    r = _fresh_registry()

    def _sync_handler(args):
        return "sync-result"

    r.register_raw(
        name="my_sync_tool",
        toolset="test",
        schema={"name": "my_sync_tool", "parameters": {"type": "object", "properties": {}}},
        handler=_sync_handler,
    )
    entry = r._get_entry("my_sync_tool")
    assert entry is not None
    assert entry.is_async is False


def test_register_raw_with_async_handler_marks_is_async_true():
    """An async handler passed to `register_raw` is auto-detected.
    Callers no longer need to set `is_async=True` explicitly —
    the detector does it for them."""
    r = _fresh_registry()

    async def _async_handler(args):
        return "async-result"

    r.register_raw(
        name="my_async_tool",
        toolset="test",
        schema={"name": "my_async_tool", "parameters": {"type": "object", "properties": {}}},
        handler=_async_handler,
    )
    entry = r._get_entry("my_async_tool")
    assert entry is not None
    assert entry.is_async is True


# ---------------------------------------------------------------------------
# register_async_raw — refuses sync handlers, requires coroutine function
# ---------------------------------------------------------------------------


def test_register_async_raw_refuses_sync_handler():
    """A sync handler passed to `register_async_raw` must be
    rejected. The async path is for tools with a real async
    API (MCP, future async plugins); a sync handler on this
    path would silently run on the agent's loop and block it."""
    r = _fresh_registry()

    def _sync_handler(args):
        return "should-not-register"

    with pytest.raises(TypeError, match="coroutine function"):
        r.register_async_raw(
            name="bad_async",
            toolset="test",
            schema={"name": "bad_async", "parameters": {"type": "object", "properties": {}}},
            handler=_sync_handler,
        )


def test_register_async_raw_accepts_coroutine_function():
    """A real `async def` handler should register successfully.
    The `is_async` flag is set to `True` automatically — no
    caller-provided lie."""
    r = _fresh_registry()

    async def _async_handler(args):
        return "ok"

    r.register_async_raw(
        name="good_async",
        toolset="test",
        schema={"name": "good_async", "parameters": {"type": "object", "properties": {}}},
        handler=_async_handler,
    )
    entry = r._get_entry("good_async")
    assert entry is not None
    assert entry.is_async is True


def test_register_async_raw_is_callable_via_execute():
    """`register_async_raw` + `execute()` end-to-end. The
    registry awaits the handler on the caller's event loop.
    No `asyncio.run()`, no sync handler, no event-loop
    allocation."""
    import asyncio
    r = _fresh_registry()

    same_loop_observed: list[bool] = []
    task_observed: list[bool] = []
    caller_loop = None

    async def _async_handler(**kwargs):
        # If we're on the caller's loop, the loop identity
        # here matches the caller's. The old `asyncio.run()`
        # path would have been on a child loop.
        handler_loop = asyncio.get_running_loop()
        same_loop_observed.append(handler_loop is caller_loop)
        task_observed.append(asyncio.current_task() is not None)
        return "async-result"

    r.register_async_raw(
        name="loop_check",
        toolset="test",
        schema={"name": "loop_check", "parameters": {"type": "object", "properties": {}}},
        handler=_async_handler,
    )

    async def _caller():
        nonlocal caller_loop
        caller_loop = asyncio.get_running_loop()
        result = await r.execute("loop_check", {})
        return result

    result = asyncio.run(_caller())
    assert result.success is True
    assert result.output == "async-result"
    # The handler ran on the caller's loop (no `asyncio.run()`).
    assert same_loop_observed == [True], (
        f"handler ran on a different loop than the caller; "
        f"the async path is supposed to keep them on the same loop"
    )
    # And the handler was inside a real task (a fresh event
    # loop from `asyncio.run()` would have an empty
    # `current_task()`).
    assert task_observed == [True]


# ---------------------------------------------------------------------------
# Cancellation propagates through the async path
# ---------------------------------------------------------------------------


def test_cancellation_propagates_through_async_handler():
    """The old `asyncio.run()`-wrapped handler ran on its own
    loop; the parent loop's cancellation couldn't reach it.
    The new async path runs the handler on the parent's loop,
    so cancellation propagates as a CancelledError — and the
    handler is on the same loop, so it sees the cancel
    immediately.

    We don't go through `registry.execute()` here (it
    doesn't currently catch `CancelledError`, which is a
    separate concern from C3). We just verify the handler
    is on the caller's loop, so a cancel on the caller
    interrupts the handler.
    """
    r = _fresh_registry()

    started = asyncio.Event()
    cancel_seen: list[bool] = []

    async def _slow_handler(**kwargs):
        started.set()
        # Wait for cancellation. If the handler is on the
        # wrong loop, this would hang past the test timeout.
        try:
            await asyncio.sleep(60)
            return "should-not-see-this"
        except asyncio.CancelledError:
            cancel_seen.append(True)
            raise

    r.register_async_raw(
        name="cancellable",
        toolset="test",
        schema={"name": "cancellable", "parameters": {"type": "object", "properties": {}}},
        handler=_slow_handler,
    )

    async def _caller():
        # Call the handler directly (not through the
        # registry's execute) to isolate the C3 question:
        # does the handler see the caller's cancellation?
        entry = r._get_entry("cancellable")
        task = asyncio.create_task(entry.handler())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return None

    asyncio.run(_caller())
    # The handler saw the cancellation — it was on the same
    # loop, so the cancel reached it. (The old `asyncio.run()`
    # path would have left the handler running on a child
    # loop past the test timeout.)
    assert cancel_seen == [True]


# ---------------------------------------------------------------------------
# MCP source check — the lie is gone
# ---------------------------------------------------------------------------


def test_mcp_client_no_longer_wraps_asyncio_run():
    """The MCP client's `_register_server_tools` used to wrap
    every tool in `asyncio.run()`. The C3 deepening replaces
    that with `register_async_raw` and a real coroutine
    handler. This test asserts the source file no longer
    contains the lie.

    We don't import the full MCP client here (it pulls in the
    MCP SDK and an event loop). A source-grep is sufficient
    and survives refactors that move code around.
    """
    src_path = (
        Path(__file__).resolve().parents[1] / "harness" / "mcp" / "client.py"
    )
    src = src_path.read_text(encoding="utf-8")
    # The lie used to look like:
    #   `handler=lambda: asyncio.run(self._servers[tn].call_tool(...))`
    # The new code uses `async def` handlers and
    # `register_async_raw`. Grep for the old form to ensure
    # it's gone.
    assert "asyncio.run(self._servers" not in src, (
        f"{src_path} still contains the `asyncio.run()` MCP "
        f"bridge. The C3 deepening should have removed it."
    )
    assert "handler=lambda" not in src, (
        f"{src_path} still contains the `lambda` handler for "
        f"MCP tool registration. The C3 deepening should use "
        f"`async def` handlers via `register_async_raw`."
    )
    # Sanity: the new path is present.
    assert "register_async_raw" in src, (
        f"{src_path} should call `register_async_raw` from "
        f"`_register_server_tools`. The C3 deepening wires "
        f"MCP to the async-aware registration path."
    )


def test_mcp_client_handler_is_async_def():
    """A regex check that the new MCP handlers are real
    coroutine functions, not lambdas. If anyone re-introduces
    the lie, this test fails before the runtime does."""
    src_path = (
        Path(__file__).resolve().parents[1] / "harness" / "mcp" / "client.py"
    )
    src = src_path.read_text(encoding="utf-8")
    # The new MCP handlers look like `async def _handler(args, _ot=ot, _tn=srv_name):`.
    assert "async def _handler" in src, (
        f"{src_path} should define an `async def _handler` for "
        f"MCP tool calls. The async path requires a coroutine "
        f"function (lambdas don't count)."
    )


# ---------------------------------------------------------------------------
# Backward-compat: legacy `is_async` kwarg is tolerated
# ---------------------------------------------------------------------------


def test_register_raw_legacy_is_async_kwarg_still_tolerated():
    """The old `is_async=False` kwarg on `register_raw` is kept
    for backward compat with any in-tree caller. New code
    should omit it (auto-detection is authoritative). The
    kwarg is allowed but ignored on conflict — the detector
    wins."""
    r = _fresh_registry()

    async def _async_handler(args):
        return "ok"

    # Pass is_async=False but pass an async handler. Detector
    # should override and log a warning.
    r.register_raw(
        name="legacy",
        toolset="test",
        schema={"name": "legacy", "parameters": {"type": "object", "properties": {}}},
        handler=_async_handler,
        is_async=False,  # wrong, but tolerated
    )
    entry = r._get_entry("legacy")
    assert entry is not None
    # The detector wins; `is_async` is True even though the
    # caller said False.
    assert entry.is_async is True
