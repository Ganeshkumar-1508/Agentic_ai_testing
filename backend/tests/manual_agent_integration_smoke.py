"""Integration smoke test: IterationBudget + TurnFinalizer integration.

Verifies the lifted hermes patterns work together at the unit level.
Full Agent.run_stream integration requires the full AgentDependencies
scaffolding (LLM, store, permissions, db) which is exercised in the
end-to-end tests; this smoke covers the two lifted modules in
isolation + a fake-agent integration to confirm the contracts hold.
"""
from __future__ import annotations

import sys

from harness.agent.iteration_budget import IterationBudget
from harness.agent.turn_finalizer import TurnFinalizerResult, finalize_turn
from harness.core.events import AgentCompleted


class _FakeAgent:
    """Stand-in for Agent — exposes the attributes finalize_turn reads."""

    def __init__(self, messages=None, *, persist_raises=False, save_raises=False):
        from harness.llm import ChatMessage
        self._messages = messages if messages is not None else [ChatMessage(role="assistant", content="x")]
        self._persist_raises = persist_raises
        self._save_raises = save_raises
        self.iteration_budget = IterationBudget(10)
        self.session_id = "test"

    def _save_trajectory(self) -> bool:
        if self._save_raises:
            raise RuntimeError("disk full")
        return True

    def _persist_session(self) -> None:
        if self._persist_raises:
            raise RuntimeError("db down")


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] IterationBudget and TurnFinalizerResult import from same package")
    check("both importable", IterationBudget is not None and TurnFinalizerResult is not None)

    print("[2] Agent stub has iteration_budget")
    a = _FakeAgent()
    check("budget exists", isinstance(a.iteration_budget, IterationBudget))
    check("max=10", a.iteration_budget.max_total == 10)

    print("[3] finalize_turn consumes a fake Agent")
    r = finalize_turn(a, agent_id="a1", rounds_completed=2, cancelled=False, max_rounds_reached=False)
    check("event present", r.agent_completed_event is not None)
    check("no errors", len(r.cleanup_errors) == 0)
    check("trajectory saved", r.trajectory_saved is True, f"actual={r.trajectory_saved}")
    check("output_preview from last msg", r.agent_completed_event.output_preview == "x", f"actual={r.agent_completed_event.output_preview!r}")

    print("[4] agent with raised side effects — never-raise invariant")
    a2 = _FakeAgent(messages=[], persist_raises=True, save_raises=True)
    r2 = finalize_turn(a2, agent_id="a2", rounds_completed=0, cancelled=True, max_rounds_reached=True)
    check("event still present", r2.agent_completed_event is not None)
    check("two errors captured", len(r2.cleanup_errors) == 2, f"actual={len(r2.cleanup_errors)} errors={r2.cleanup_errors}")
    check("trajectory_saved False", r2.trajectory_saved is False)
    check("cancelled flag preserved", r2.agent_completed_event.cancelled is True)
    check("max_rounds preview (no msg)", r2.agent_completed_event.output_preview == "Max tool rounds reached.", f"actual={r2.agent_completed_event.output_preview!r}")

    print("[5] combined test: budget reset between turns")
    a3 = _FakeAgent()
    a3.iteration_budget.consume()
    a3.iteration_budget.consume()
    check("used=2 mid-turn", a3.iteration_budget.used == 2)
    a3.iteration_budget.reset(max_total=5)
    check("after reset used=0", a3.iteration_budget.used == 0)
    check("after reset max=5", a3.iteration_budget.max_total == 5)
    r3 = finalize_turn(a3, agent_id="a3", rounds_completed=1, cancelled=False, max_rounds_reached=False)
    check("post-finalize event present", r3.agent_completed_event is not None)
    check("budget unaffected by finalize", a3.iteration_budget.used == 0)

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL AGENT INTEGRATION SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
