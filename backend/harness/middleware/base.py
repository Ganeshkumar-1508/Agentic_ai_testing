"""Base middleware interface and chain runner for TestAI's agent loop.

Design mirrors DeerFlow's AgentMiddleware pattern but adapted for TestAI's
async generator run loop (``run_stream``) instead of LangGraph's node model.

Hooks (called in order by the chain runner):
  on_before_run(user_input)        — start of run_stream()
  on_before_llm(messages, round)   — before LLM call each round
  on_after_llm(tool_calls, round)  — after LLM returns tool_calls
  on_before_tool(name, args)       — before each tool dispatch
  on_after_tool(name, result)      — after each tool result
  on_end_of_round(round)           — end of each round
  on_after_run(result, error)      — end of run_stream()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentMiddleware:
    """Base class for a single middleware.
    
    Subclass and override the hooks you need. Unimplemented hooks
    are no-ops.
    """

    async def on_before_run(self, user_input: str) -> None:
        pass

    async def on_after_run(self, result: str | None, error: str | None) -> None:
        pass

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        """Mutate/return the message list before LLM call, or None for no change."""
        return None

    async def on_after_llm(
        self, tool_calls: list[dict], round_num: int,
    ) -> list[dict] | tuple[list[dict], str] | None:
        """Mutate/return tool_calls after LLM returns, or None for no change.
        
        Can return (tool_calls, forced_text) to force a text answer instead.
        """
        return None

    async def on_before_tool(self, name: str, args: dict) -> bool | None:
        """Return False to block tool execution, None/True to allow."""
        return None

    async def on_after_tool(self, name: str, result: str) -> str | None:
        """Mutate/return the tool result, or None for no change."""
        return None

    async def on_end_of_round(self, round_num: int) -> None:
        pass


class MiddlewareChain:
    """DEPRECATED — use harness.hook.pipeline.HookPipeline instead.

    Ordered pipeline of middlewares. Thread-safe.

    This class is kept for backward compatibility but is no longer used by
    Agent.__init__. New code should use HookPipeline from harness.hook.
    """

    def __init__(self) -> None:
        self._middlewares: list[AgentMiddleware] = []

    def add(self, mw: AgentMiddleware) -> AgentMiddleware:
        self._middlewares.append(mw)
        return mw

    def remove(self, mw: AgentMiddleware) -> None:
        try:
            self._middlewares.remove(mw)
        except ValueError:
            pass

    # ── hooks ──────────────────────────────────────────────────────

    async def on_before_run(self, user_input: str) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_before_run(user_input)
            except Exception as exc:
                logger.warning("Middleware %s.on_before_run failed: %s", type(mw).__name__, exc)

    async def on_after_run(self, result: str | None, error: str | None) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_after_run(result, error)
            except Exception as exc:
                logger.warning("Middleware %s.on_after_run failed: %s", type(mw).__name__, exc)

    async def on_before_llm(self, messages: list, round_num: int) -> list:
        current = messages
        for mw in self._middlewares:
            try:
                result = await mw.on_before_llm(current, round_num)
                if result is not None:
                    current = result
            except Exception as exc:
                logger.warning("Middleware %s.on_before_llm failed: %s", type(mw).__name__, exc)
        return current

    async def on_after_llm(self, tool_calls: list[dict], round_num: int) -> tuple[list[dict], str | None]:
        current_calls = tool_calls
        forced_text: str | None = None
        for mw in self._middlewares:
            try:
                result = await mw.on_after_llm(current_calls, round_num)
                if result is None:
                    continue
                if isinstance(result, tuple):
                    current_calls, forced_text = result
                else:
                    current_calls = result
            except Exception as exc:
                logger.warning("Middleware %s.on_after_llm failed: %s", type(mw).__name__, exc)
        return current_calls, forced_text

    async def on_before_tool(self, name: str, args: dict) -> bool:
        for mw in self._middlewares:
            try:
                allow = await mw.on_before_tool(name, args)
                if allow is False:
                    return False
            except Exception as exc:
                logger.warning("Middleware %s.on_before_tool failed: %s", type(mw).__name__, exc)
        return True

    async def on_after_tool(self, name: str, result: str) -> str:
        current = result
        for mw in self._middlewares:
            try:
                new = await mw.on_after_tool(name, current)
                if new is not None:
                    current = new
            except Exception as exc:
                logger.warning("Middleware %s.on_after_tool failed: %s", type(mw).__name__, exc)
        return current

    async def on_end_of_round(self, round_num: int) -> None:
        for mw in self._middlewares:
            try:
                await mw.on_end_of_round(round_num)
            except Exception as exc:
                logger.warning("Middleware %s.on_end_of_round failed: %s", type(mw).__name__, exc)
