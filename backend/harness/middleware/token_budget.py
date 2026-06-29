"""Token budget middleware — ported from DeerFlow's TokenBudgetMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_WARN_MSG = (
    "[TOKEN BUDGET WARNING] Used {used:,} of {budget:,} {reason} "
    "token budget ({percent:.0f}%). Wrap up now."
)
_EXCEEDED_MSG = (
    "[TOKEN BUDGET EXCEEDED] {reason} token usage ({used:,}) "
    "exceeded limit ({budget:,}). Producing final answer."
)


@dataclass
class TokenBudgetConfig:
    enabled: bool = True
    max_tokens: int = 100_000
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    warn_threshold: float = 0.8
    hard_stop_threshold: float = 0.95


class _Usage:
    input: int = 0
    output: int = 0
    total: int = 0


class TokenBudgetMiddleware(AgentMiddleware):
    """Enforce per-run token budget limits with warn + hard-stop."""

    def __init__(self, config: TokenBudgetConfig | None = None) -> None:
        self._config = config or TokenBudgetConfig()
        self._usage = _Usage()
        self._warned = False
        self._pending_warnings: list[str] = []

    async def on_before_run(self, user_input: str) -> None:
        self._usage = _Usage()
        self._warned = False
        self._pending_warnings = []
        self._est_input = len(user_input) // 4

    async def on_after_run(self, result: str | None, error: str | None) -> None:
        self._pending_warnings = []

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        if not self._config.enabled:
            return None

        est_prompt = sum(len(str(getattr(m, "content", "") or "")) for m in messages) // 4
        self._usage.input = max(self._usage.input, est_prompt)

        if not self._pending_warnings:
            return None

        text = "\n\n".join(self._pending_warnings)
        self._pending_warnings = []
        from harness.core.events import ChatMessage
        return list(messages) + [ChatMessage(role="user", content=text)]

    async def on_after_llm(
        self, tool_calls: list[dict], round_num: int,
    ) -> tuple[list[dict], str] | None:
        if not self._config.enabled:
            return None

        est_output = sum(
            len(json.dumps(tc.get("function", tc), default=str)) for tc in (tool_calls or [])
        ) // 4
        self._usage.output += est_output
        self._usage.total = self._usage.input + self._usage.output

        if self._usage.total <= 0:
            return None

        fractions = [("total", self._usage.total, self._config.max_tokens)]
        if self._config.max_input_tokens:
            fractions.append(("input", self._usage.input, self._config.max_input_tokens))
        if self._config.max_output_tokens:
            fractions.append(("output", self._usage.output, self._config.max_output_tokens))

        highest = 0.0
        trigger_reason = ""
        trigger_used = 0
        trigger_budget = 0

        for reason, used, limit in fractions:
            frac = used / limit if limit > 0 else 0
            if frac > highest:
                highest = frac
                trigger_reason = reason
                trigger_used = used
                trigger_budget = limit

        if highest >= self._config.hard_stop_threshold:
            logger.warning("Token budget hard-stop: %s limit exceeded", trigger_reason)
            return [], _EXCEEDED_MSG.format(
                reason=trigger_reason, used=trigger_used, budget=trigger_budget,
            )

        if highest >= self._config.warn_threshold and not self._warned:
            self._warned = True
            self._pending_warnings.append(_WARN_MSG.format(
                reason=trigger_reason, used=trigger_used,
                budget=trigger_budget, percent=highest * 100,
            ))

        return None
