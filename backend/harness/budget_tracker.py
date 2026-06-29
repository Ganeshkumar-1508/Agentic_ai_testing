"""Per-run budget tracking + auto-throttle ladder (Q6).

The 4-step ladder (per `reference/hermes-agent/AGENTS.md:827`
"Hermes `cron.3-minute hard interrupt`" + the broader auto-throttle
pattern):

  step 0: ok
  step 1: HITL  — surface an approval modal for each tool call
  step 2: sequential — demote parallel tool calls to sequential
  step 3: cheaper model — switch the LLM router to a smaller model
  step 4: pause — set the agent's interrupt flag; the run stops

Steps 1-4 are *graduated*: each step buys more headroom at the cost
of more friction. The user is told which step the system is on at
all times via the dashboard's run detail.

This module is the **plumbing**. The policy lives in the budget
configuration (per-run, per-subagent, per-user-per-day). The
`BudgetTracker` here tracks ONE run's spend in memory; the wider
per-user / per-org accounting is done by the existing
`backend/api/routers/cost.py` infrastructure.

The ladder steps themselves are implemented as soft hooks on the
agent:
  - step 1: ``Agent._hitl_gate`` is set; the next tool call goes
    through ``PermissionManager.await_approval`` instead of running
  - step 2: ``Agent._sequential_only`` is set; ``ToolDispatcher``
    runs tool calls one at a time
  - step 3: ``LLMRouter.set_tier("small")`` is called; subsequent
    LLM calls use the smaller model
  - step 4: ``Agent._interrupt_requested`` is set; the loop exits

For v1, the *plumbing* is in place; the per-step hook implementations
are the follow-up (the agent / dispatcher changes are not in this
file — they read the flags set here). The orchestrator's
``run_single`` calls ``BudgetTracker.check_soft_cap()`` every 5
rounds; on a non-zero step, it applies the corresponding flag to
the agent.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ContextVar so the orchestrator can attach a tracker to a
# subagent it spawns via delegate_task. The orchestrator calls
# ``set_current_tracker(t)`` before ``dt.run(...)``; the spawn
# logic in a follow-up reads ``get_current_tracker()`` and calls
# ``subagent.set_budget_tracker(t)`` on the new Agent. Until that
# wiring lands, the tracker is scoped to the orchestrator's own
# direct LLM calls (of which there are none in the common path).
_CURRENT_TRACKER: ContextVar["BudgetTracker | None"] = ContextVar(
    "_CURRENT_BUDGET_TRACKER", default=None
)


def get_current_tracker() -> "BudgetTracker | None":
    return _CURRENT_TRACKER.get()


def set_current_tracker(tracker: "BudgetTracker | None"):
    """Context-manager-like setter. Use as a token-returning helper:
    ``token = set_current_tracker(t); ... ; reset_current_tracker(token)``
    (mirrors the chat-tier override pattern in
    ``harness/agent/tool_dispatch.py``).
    """
    return _CURRENT_TRACKER.set(tracker)


def reset_current_tracker(token) -> None:
    _CURRENT_TRACKER.reset(token)


@dataclass
class BudgetConfig:
    """One run's budget settings. All caps are in USD.

    Defaults are conservative: a single run that costs > $5 is
    almost certainly a runaway; > $1.50 should already trigger
    throttle-step 1 (HITL). Per-user-per-day is enforced at the
    cost-router level, not here.
    """

    run_soft_cap_usd: float = 1.50
    run_hard_cap_usd: float = 5.00
    hitl_threshold_usd: float = 1.00
    sequential_threshold_usd: float = 2.00
    cheaper_model_threshold_usd: float = 3.00
    pause_threshold_usd: float = 4.00


@dataclass
class BudgetSnapshot:
    """What the tracker reports back. Read-only."""

    run_id: str
    session_id: str | None
    spent_usd: float
    soft_cap_usd: float
    hard_cap_usd: float
    throttle_step: int
    hitl_active: bool
    sequential_active: bool
    cheaper_model_active: bool
    pause_requested: bool
    n_llm_calls: int = 0
    n_tool_calls: int = 0


class BudgetTracker:
    """Per-run budget tracker.

    Usage:
        tracker = BudgetTracker(run_id="...", session_id="...")
        # In the LLM call path:
        await tracker.add_cost(model=..., input_tokens=..., output_tokens=...)
        # Every 5 rounds:
        step = tracker.check_soft_cap()
        if step >= 1: agent._hitl_gate = True
        if step >= 2: agent._sequential_only = True
        if step >= 3: llm_router.set_tier("small")
        if step >= 4: agent.request_interrupt()
        # At run start:
        if tracker.hard_cap_exceeded(): abort

    The tracker is *in-memory* per run. It does not write to the DB;
    the existing `_record_cost` in `agent.py:468` writes per-LLM-call
    rows to `token_usage` for analytics / per-user / per-org
    accounting. The tracker is the *enforcement* layer.
    """

    def __init__(
        self,
        run_id: str,
        session_id: str | None = None,
        config: BudgetConfig | None = None,
        spec_id: str = "",
    ) -> None:
        self.run_id = run_id
        self.session_id = session_id
        self.spec_id = spec_id
        self.config = config or BudgetConfig()
        self._spent: float = 0.0
        self._n_llm_calls: int = 0
        self._n_tool_calls: int = 0
        self._throttle_step: int = 0
        self._pause_requested: bool = False

    # ── cost recording ───────────────────────────────────────────────

    async def add_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        pricing_cache: Any | None = None,
    ) -> float:
        """Add the cost of one LLM call. Returns the cost in USD.

        The pricing lookup is best-effort: if the model has no
        rate in the cache, we fall back to a flat $0.15 / 1M input
        and $0.60 / 1M output (a reasonable Sonnet-class default).
        """
        try:
            from harness.cost_tracker import get_pricing_cache
            cache = pricing_cache or get_pricing_cache()
            try:
                rates = await cache.get_rate(model)
            except Exception:
                rates = None
        except Exception:
            rates = None
        if not rates:
            in_rate = 0.15
            out_rate = 0.60
        else:
            in_rate = float(rates.get("input", 0.15))
            out_rate = float(rates.get("output", 0.60))
        cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
        self._spent += cost
        self._n_llm_calls += 1
        return cost

    def add_tool_cost(self) -> None:
        """Increment tool-call counter. Tool calls are cheap; we just
        count them for the snapshot."""
        self._n_tool_calls += 1

    # ── throttle decisions ───────────────────────────────────────────

    def check_soft_cap(self) -> int:
        """Re-evaluate the throttle step from current spend. Returns 0-4.

        Idempotent: each call is a fresh read of ``_spent``. The
        step is sticky — once it climbs to 3, it stays at 3 (or
        climbs further) until the run ends. We don't de-escalate
        mid-run; de-escalation would be confusing for the operator.
        """
        c = self.config
        step = 0
        if self._spent >= c.hitl_threshold_usd:
            step = 1
        if self._spent >= c.sequential_threshold_usd:
            step = 2
        if self._spent >= c.cheaper_model_threshold_usd:
            step = 3
        if self._spent >= c.pause_threshold_usd:
            step = 4
        if step > self._throttle_step:
            logger.info(
                "budget throttle step climbed run=%s spent=$%.4f step=%d->%d",
                self.run_id, self._spent, self._throttle_step, step,
            )
            self._throttle_step = step
        if step >= 4:
            self._pause_requested = True
        return self._throttle_step

    def hard_cap_exceeded(self) -> bool:
        """True if the run has blown past the hard cap. The
        orchestrator should abort the run before this happens."""
        return self._spent >= self.config.run_hard_cap_usd

    def request_pause(self, reason: str = "") -> None:
        """Manually request a pause (e.g. from a hook or HITL deny)."""
        self._pause_requested = True
        self._throttle_step = max(self._throttle_step, 4)
        if reason:
            logger.info("budget pause requested run=%s reason=%s", self.run_id, reason)

    # ── snapshot ─────────────────────────────────────────────────────

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            run_id=self.run_id,
            session_id=self.session_id,
            spent_usd=round(self._spent, 6),
            soft_cap_usd=self.config.run_soft_cap_usd,
            hard_cap_usd=self.config.run_hard_cap_usd,
            throttle_step=self._throttle_step,
            hitl_active=self._throttle_step >= 1,
            sequential_active=self._throttle_step >= 2,
            cheaper_model_active=self._throttle_step >= 3,
            pause_requested=self._pause_requested,
            n_llm_calls=self._n_llm_calls,
            n_tool_calls=self._n_tool_calls,
        )

    async def observe(
        self,
        *,
        agent: Any | None = None,
        llm_router: Any | None = None,
        event_bus: Any | None = None,
    ) -> BudgetSnapshot:
        prev = self._throttle_step
        new = self.check_soft_cap()
        if new == prev:
            return self.snapshot()

        if agent is not None and new >= 1:
            try:
                agent.set_hitl_gate(True)
            except Exception as exc:
                logger.debug(
                    "budget.observe: set_hitl_gate failed: %s", exc,
                )
        if agent is not None and new >= 2:
            try:
                agent.set_sequential_only(True)
            except Exception as exc:
                logger.debug(
                    "budget.observe: set_sequential_only failed: %s", exc,
                )
        if llm_router is not None and new >= 3:
            try:
                llm_router.set_tier("small")
            except Exception as exc:
                logger.debug(
                    "budget.observe: set_tier failed: %s", exc,
                )
        if agent is not None and new >= 4:
            try:
                agent.interrupt()
            except Exception as exc:
                logger.debug(
                    "budget.observe: interrupt failed: %s", exc,
                )

        if event_bus is not None:
            try:
                from harness.core.events import BudgetThrottled
                await event_bus.emit(BudgetThrottled(
                    run_id=self.run_id,
                    session_id=self.session_id or "",
                    spec_id=self.spec_id or "",
                    prev_step=prev,
                    new_step=new,
                    spent_usd=round(self._spent, 6),
                    soft_cap_usd=self.config.run_soft_cap_usd,
                    hitl_active=new >= 1,
                    sequential_active=new >= 2,
                    cheaper_model_active=new >= 3,
                    pause_requested=new >= 4,
                ))
            except Exception as exc:
                logger.debug(
                    "budget.observe: emit BudgetThrottled failed: %s", exc,
                )

        return self.snapshot()
