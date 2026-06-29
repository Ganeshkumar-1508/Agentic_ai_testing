"""Slash command system for TestAI.

Pattern from Claude Code (src/types/command.ts):
  - Three execution flavors: local (side effect), prompt (synthetic message), modal (UI)
  - Lazy loading: metadata is always available, implementation deferred
  - isEnabled() getter: re-evaluated on every render
  - Registry as simple array, no register() calls

When a user types /help, /clear, /cost — no token is sent to the LLM.
The harness intercepts, dispatches, and responds. This is the user's
direct control surface over the agent session.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SlashCommand:
    """A single slash command definition.

    Flavors:
      - local: side effect, returns text. Model never sees it.
      - prompt: generates content injected as a user message. Model sees it.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        *,
        aliases: tuple[str, ...] = (),
        flavor: str = "local",
        is_hidden: bool = False,
        is_enabled: Callable[[], bool] | None = None,
        argument_hint: str = "",
    ):
        self.name = name
        self.description = description
        self.aliases = aliases
        self.flavor = flavor  # "local" | "prompt"
        self.is_hidden = is_hidden
        self._is_enabled = is_enabled
        self.argument_hint = argument_hint
        self._handler: Callable | None = None

    def is_enabled(self) -> bool:
        if self._is_enabled is not None:
            return self._is_enabled()
        return True

    def handler(self, fn):
        """Set the handler function. Returns self for chaining."""
        self._handler = fn
        return self

    async def run(self, args: str = "", **kwargs: Any) -> str:
        if self._handler is None:
            return f"Command /{self.name} not implemented."
        import asyncio
        if asyncio.iscoroutinefunction(self._handler):
            return await self._handler(args, **kwargs)
        return self._handler(args, **kwargs)


# ── Registry ──────────────────────────────────────────────────────────

_registry: dict[str, SlashCommand] = {}
_by_name: dict[str, SlashCommand] = {}


def register(cmd: SlashCommand) -> SlashCommand:
    _by_name[cmd.name] = cmd
    _registry[cmd.name] = cmd
    for alias in cmd.aliases:
        _registry[alias] = cmd
    return cmd


def get(name: str) -> SlashCommand | None:
    return _registry.get(name.lstrip("/"))


def list_all() -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for name, cmd in _registry.items():
        if cmd.name in seen:
            continue
        seen.add(cmd.name)
        if cmd.is_hidden:
            continue
        if not cmd.is_enabled():
            continue
        result.append({
            "name": cmd.name,
            "description": cmd.description,
            "flavor": cmd.flavor,
            "aliases": list(cmd.aliases),
            "argument_hint": cmd.argument_hint,
        })
    return sorted(result, key=lambda c: c["name"])


async def dispatch(name: str, args: str = "", **kwargs: Any) -> str:
    cmd = get(name)
    if cmd is None:
        return f"Unknown command: /{name}. Try /help for available commands."
    if not cmd.is_enabled():
        return f"Command /{name} is not available."
    try:
        return await cmd.run(args, **kwargs)
    except Exception as e:
        logger.warning("Command /%s failed: %s", name, e)
        return f"Error executing /{name}: {e}"
