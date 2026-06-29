"""HookPipeline — ordered execution of lifecycle hooks.

Wraps ``HookRegistry`` and provides typed methods that mirror the old
``MiddlewareChain`` interface so ``Agent.run_stream`` can switch to the
unified pipeline without changing call sites.

Phase ordering:
  1. Deterministic gates (allow/block/ask)  → HookType.DETERMINISTIC_GATE
  2. Middleware chain                         → HookType.MIDDLEWARE
  3. Plugin hooks                             → HookType.PLUGIN

Usage:
    from harness.hook.pipeline import HookPipeline

    pipeline = HookPipeline()
    pipeline.add_middleware(SomeMiddleware())
    result = await pipeline.on_before_tool("bash", {"command": "rm -rf"})
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from harness.hook.phases import (
    HookType,
    AFTER_RUN,
    AFTER_TOOL,
    AFTER_LLM,
    BEFORE_RUN,
    BEFORE_TOOL,
    BEFORE_LLM,
    END_OF_ROUND,
)
from harness.hook.registry import HookRegistry, get_registry

logger = logging.getLogger(__name__)


async def _maybe_await(handler: Any, **kwargs: Any) -> Any:
    """Call a handler (sync or async) and return its result."""
    if inspect.iscoroutinefunction(handler):
        return await handler(**kwargs)
    return handler(**kwargs)


class HookPipeline:
    """Ordered pipeline of lifecycle hooks. Drop-in superset of MiddlewareChain.

    Delegates to a ``HookRegistry`` for storage, adds typed helper methods
    that match the old ``MiddlewareChain`` call sites in Agent.run_stream,
    and provides ``add_middleware()`` / ``add_gate()`` / ``add_plugin()``
    convenience wrappers that set the correct ``HookType``.

    Each pipeline creates its own private registry by default. Pass a shared
    registry to coordinate between multiple pipelines (e.g. Agent + subagent).
    """

    def __init__(self, registry: HookRegistry | None = None) -> None:
        self._registry = registry or HookRegistry()

    # ── Registration (convenience wrappers) ──────────────────────────

    def add_middleware(self, middleware: Any) -> Any:
        """Register a middleware instance.

        If the middleware has async methods matching the pipeline's hook
        names (on_before_run, on_before_tool, etc.), each is registered
        as a MIDDLEWARE-phase handler.
        """
        _HOOK_METHODS = [
            ("on_before_run", BEFORE_RUN),
            ("on_after_run", AFTER_RUN),
            ("on_before_llm", BEFORE_LLM),
            ("on_after_llm", AFTER_LLM),
            ("on_before_tool", BEFORE_TOOL),
            ("on_after_tool", AFTER_TOOL),
            ("on_end_of_round", END_OF_ROUND),
        ]
        for method_name, event_name in _HOOK_METHODS:
            method = getattr(middleware, method_name, None)
            if method is not None and callable(method):
                self._registry.register(
                    event_name, method, hook_type=HookType.MIDDLEWARE,
                )
        return middleware

    def add_gate(self, handler: Any) -> Any:
        """Register a deterministic gate handler (runs first in pipeline)."""
        self._registry.register(
            BEFORE_TOOL, handler, hook_type=HookType.DETERMINISTIC_GATE,
        )
        return handler

    def add_plugin(self, event: str, handler: Any) -> Any:
        """Register a plugin hook handler (runs last in pipeline)."""
        self._registry.register(event, handler, hook_type=HookType.PLUGIN)
        return handler

    def remove(self, handler: Any) -> None:
        """Remove a handler from all events it's registered on.

        Identity comparison — removes every registration whose handler
        is *handler*.
        """
        for event in self._registry._handlers:
            self._registry.unregister(event, handler)

    # ── Lifecycle hooks (mirror MiddlewareChain interface) ───────────

    async def on_before_run(self, user_input: str) -> None:
        await self._registry.invoke(BEFORE_RUN, user_input=user_input)

    async def on_after_run(self, result: str | None, error: str | None) -> None:
        await self._registry.invoke(AFTER_RUN, result=result, error=error)

    async def on_before_llm(self, messages: list, round_num: int) -> list:
        """Chain each handler's mutated messages into the next.
        Matches MiddlewareChain.on_before_llm legacy behaviour."""
        entries = self._registry._handlers.get(BEFORE_LLM)
        if not entries:
            return messages
        for entry in sorted(entries):
            try:
                mutated = await _maybe_await(entry.handler, messages=messages, round_num=round_num)
                if mutated is not None:
                    messages = mutated
            except Exception as exc:
                logger.warning("Handler %s.on_before_llm failed: %s", entry.handler, exc)
        return messages

    async def on_after_llm(
        self, tool_calls: list[dict], round_num: int,
    ) -> tuple[list[dict], str | None]:
        """Chain each handler's mutated tool_calls into the next."""
        entries = self._registry._handlers.get(AFTER_LLM)
        if not entries:
            return tool_calls, None
        forced_text: str | None = None
        for entry in sorted(entries):
            try:
                result = await _maybe_await(entry.handler, tool_calls=tool_calls, round_num=round_num)
                if result is None:
                    continue
                if isinstance(result, tuple):
                    tool_calls, forced_text = result
                else:
                    tool_calls = result
            except Exception as exc:
                logger.warning("Handler %s.on_after_llm failed: %s", entry.handler, exc)
        return tool_calls, forced_text

    async def on_before_tool(self, name: str, args: dict) -> bool:
        """Chain each handler's decision into the next.
        First False return short-circuits (blocks the tool)."""
        entries = self._registry._handlers.get(BEFORE_TOOL)
        if not entries:
            return True
        for entry in sorted(entries):
            try:
                result = await _maybe_await(entry.handler, name=name, args=args)
                if result is False:
                    return False
            except Exception as exc:
                logger.warning("Handler %s.on_before_tool failed: %s", entry.handler, exc)
        return True

    async def on_after_tool(self, name: str, result: str) -> str:
        """Chain each handler's mutated result into the next."""
        entries = self._registry._handlers.get(AFTER_TOOL)
        if not entries:
            return result
        for entry in sorted(entries):
            try:
                mutated = await _maybe_await(entry.handler, name=name, result=result)
                if mutated is not None:
                    result = mutated
            except Exception as exc:
                logger.warning("Handler %s.on_after_tool failed: %s", entry.handler, exc)
        return result

    async def on_end_of_round(self, round_num: int) -> None:
        await self._registry.invoke(END_OF_ROUND, round_num=round_num)

    # ── Direct registry access (for callers that need it) ────────────

    @property
    def registry(self) -> HookRegistry:
        return self._registry
