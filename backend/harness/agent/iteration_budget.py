"""Thread-safe per-agent iteration counter.

Lifted from reference/hermes-agent/agent/iteration_budget.py (62 LoC, MIT).
Each agent (parent or subagent) owns an IterationBudget. The parent
budget is capped at ``max_iterations`` (default 90). Each subagent
gets an independent budget capped at ``delegation.max_iterations``
(default 50) — total iterations across parent + subagents can
exceed the parent's cap.

``execute_code`` (programmatic tool calling) iterations are refunded
via :meth:`refund` so they don't eat into the budget.
"""
from __future__ import annotations

import threading


class IterationBudget:
    """Thread-safe iteration counter for an agent."""

    def __init__(self, max_total: int) -> None:
        if max_total < 1:
            raise ValueError(f"max_total must be >= 1, got {max_total}")
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)

    def reset(self, max_total: int | None = None) -> None:
        with self._lock:
            self._used = 0
            if max_total is not None:
                if max_total < 1:
                    raise ValueError(f"max_total must be >= 1, got {max_total}")
                self.max_total = max_total

    def __repr__(self) -> str:
        return f"IterationBudget(used={self.used}, max_total={self.max_total})"


__all__ = ["IterationBudget"]
