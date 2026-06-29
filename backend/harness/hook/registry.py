"""Unified HookRegistry — single registry for all agent lifecycle hooks.

Replaces the three overlapping systems:
  1. harness/middleware/base.py  (MiddlewareChain)
  2. harness/_hook_system.py     (HookRegistry for plugins)
  3. harness/hook_registry.py    (HookRegistry for deterministic gates)

Pattern: Hermes Agent's single HookRegistry (reference/hermes-agent/gateway/hooks.py)
with phase ordering added so the three existing systems merge without behavioural
change. Each handler is stored with a HookType that determines execution order.

Usage:
    from harness.hook.registry import registry as hook_registry

    # Register a middleware-style handler
    hook_registry.register("before_tool", my_handler, HookType.MIDDLEWARE)

    # Register a deterministic gate (runs first)
    hook_registry.register("before_tool", gate_handler, HookType.DETERMINISTIC_GATE)

    # Register a plugin hook (runs last)
    hook_registry.register("pre_tool_call", plugin_handler, HookType.PLUGIN)

    # Fire an event (handlers execute in HookType order)
    await hook_registry.invoke("before_tool", name="bash", args={...})
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from harness.hook.phases import ALL_EVENTS, HookType

logger = logging.getLogger(__name__)


HookHandler = Callable[..., Any]


@dataclass(order=True)
class _Entry:
    """Internal registry entry, sortable by (hook_type, registration_order)."""

    hook_type: int
    registration_order: int
    handler: HookHandler = field(compare=False)


class HookRegistry:
    """Thread-safe registry for lifecycle hook handlers.

    Each handler is stored with a ``HookType`` that determines which phase
    it executes in. Within the same phase, handlers fire in registration order.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[_Entry]] = {}
        self._counter: int = 0

    def register(
        self,
        event: str,
        handler: HookHandler,
        hook_type: HookType = HookType.MIDDLEWARE,
    ) -> None:
        """Register a handler for *event*.

        If *event* is not in ``ALL_EVENTS``, a warning is logged and the
        registration is ignored (prevents silent typos).
        """
        if event not in ALL_EVENTS:
            logger.warning(
                "HookRegistry.register: unknown event '%s' (known=%d)",
                event, len(ALL_EVENTS),
            )
            return
        entry = _Entry(
            hook_type=int(hook_type),
            registration_order=self._counter,
            handler=handler,
        )
        self._counter += 1
        self._handlers.setdefault(event, []).append(entry)

    def unregister(self, event: str, handler: HookHandler) -> None:
        """Remove a handler for *event* (identity comparison)."""
        entries = self._handlers.get(event)
        if entries is None:
            return
        self._handlers[event] = [e for e in entries if e.handler is not handler]

    def clear(self) -> None:
        self._handlers.clear()

    def clear_event(self, event: str) -> None:
        """Remove all handlers for a single event."""
        self._handlers.pop(event, None)

    # ── Dispatch ─────────────────────────────────────────────────────

    async def invoke(self, event: str, **kwargs: Any) -> list[Any]:
        """Call all handlers for *event* in HookType order.

        Supports both sync and async handlers (auto-detected via
        ``inspect.iscoroutinefunction``). Each handler is wrapped in its
        own try/except so a misbehaving handler cannot break the chain.

        Returns a list of non-None return values, in handler execution order.
        """
        entries = self._handlers.get(event)
        if not entries:
            return []
        sorted_entries = sorted(entries)
        results: list[Any] = []
        for entry in sorted_entries:
            try:
                if inspect.iscoroutinefunction(entry.handler):
                    ret = await entry.handler(**kwargs)
                else:
                    ret = entry.handler(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as exc:
                logger.warning(
                    "Hook '%s' handler %s raised: %s",
                    event, getattr(entry.handler, "__name__", repr(entry.handler)),
                    exc,
                )
        return results

    async def invoke_blocking(self, event: str, **kwargs: Any) -> str | None:
        """Invoke ``before_tool`` handlers and return the first block message.

        Handlers whose return is a dict with ``{"action": "block", "message": ...}``
        cause an early return (the first block wins). Returns ``None`` when
        no handler blocks.
        """
        entries = self._handlers.get(event)
        if not entries:
            return None
        sorted_entries = sorted(entries)
        for entry in sorted_entries:
            try:
                if inspect.iscoroutinefunction(entry.handler):
                    ret = await entry.handler(**kwargs)
                else:
                    ret = entry.handler(**kwargs)
                if isinstance(ret, dict) and ret.get("action") == "block":
                    msg = ret.get("message", "")
                    if isinstance(msg, str) and msg:
                        return msg
            except Exception as exc:
                logger.warning(
                    "Hook '%s' handler %s raised: %s",
                    event, getattr(entry.handler, "__name__", repr(entry.handler)),
                    exc,
                )
        return None

    async def invoke_transform(self, event: str, text: str, **kwargs: Any) -> str:
        """Invoke ``transform_*`` handlers, return the first non-None replacement.

        Returns the original text when no handler transforms it.
        """
        entries = self._handlers.get(event)
        if not entries:
            return text
        sorted_entries = sorted(entries)
        for entry in sorted_entries:
            try:
                if inspect.iscoroutinefunction(entry.handler):
                    ret = await entry.handler(text=text, **kwargs)
                else:
                    ret = entry.handler(text=text, **kwargs)
                if isinstance(ret, str) and ret:
                    return ret
            except Exception as exc:
                logger.warning(
                    "Hook '%s' handler %s raised: %s",
                    event, getattr(entry.handler, "__name__", repr(entry.handler)),
                    exc,
                )
        return text

    # ── Inspection ───────────────────────────────────────────────────

    def list_handlers(self, event: str | None = None) -> list[dict[str, Any]]:
        """Return metadata about registered handlers for debugging."""
        result: list[dict[str, Any]] = []
        for ev, entries in self._handlers.items():
            if event is not None and ev != event:
                continue
            for entry in sorted(entries):
                result.append({
                    "event": ev,
                    "hook_type": HookType(entry.hook_type).name,
                    "handler": getattr(entry.handler, "__name__", repr(entry.handler)),
                })
        return result

    def has_handlers(self, event: str) -> bool:
        """True if at least one handler is registered for *event*."""
        entries = self._handlers.get(event)
        return bool(entries)


# ── Module-level singleton ─────────────────────────────────────────────

_registry: HookRegistry | None = None


def get_registry() -> HookRegistry:
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry


def reset_registry_for_tests() -> None:
    global _registry
    _registry = None
