"""Smoke test for the turn_finalizer module."""
from __future__ import annotations

import sys

from harness.agent.turn_finalizer import TurnFinalizerResult, finalize_turn
from harness.core.events import AgentCompleted


class _FakeAgent:
    """Minimal stand-in for an Agent — exposes the attributes turn_finalizer reads."""

    def __init__(self, *, messages=None, persist_raises=False, save_raises=False):
        self._messages = messages or []
        self._persist_raises = persist_raises
        self._save_raises = save_raises
        self.persist_called = False
        self.save_called = False

    def _persist_session(self) -> None:
        self.persist_called = True
        if self._persist_raises:
            raise RuntimeError("db connection lost")

    def _save_trajectory(self) -> bool:
        self.save_called = True
        if self._save_raises:
            raise RuntimeError("disk full")
        return True


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] happy path — no side effects raise")
    from harness.llm import ChatMessage
    agent = _FakeAgent(messages=[ChatMessage(role="assistant", content="done")])
    r = finalize_turn(agent, agent_id="a1", rounds_completed=3, cancelled=False, max_rounds_reached=False)
    check("trajectory saved", r.trajectory_saved is True)
    check("persist called", agent.persist_called is True)
    check("no errors", len(r.cleanup_errors) == 0)
    check("event present", r.agent_completed_event is not None)
    check("event has correct agent_id", r.agent_completed_event.agent_id == "a1")
    check("event not cancelled", r.agent_completed_event.cancelled is False)
    check("event rounds=3", r.agent_completed_event.rounds == 3)
    check("event preview='done'", r.agent_completed_event.output_preview == "done")

    print("[2] max_rounds_reached with no messages")
    agent = _FakeAgent(messages=[])
    r = finalize_turn(agent, agent_id="a2", rounds_completed=20, cancelled=False, max_rounds_reached=True)
    check("preview=max rounds", r.agent_completed_event.output_preview == "Max tool rounds reached.")

    print("[3] max_rounds_reached WITH messages — preview wins over max text")
    agent = _FakeAgent(messages=[ChatMessage(role="assistant", content="actual result")])
    r = finalize_turn(agent, agent_id="a3", rounds_completed=20, cancelled=False, max_rounds_reached=True)
    check("preview=actual", r.agent_completed_event.output_preview == "actual result")

    print("[4] persist raises — recorded, never raised out")
    agent = _FakeAgent(persist_raises=True)
    r = finalize_turn(agent, agent_id="a4", rounds_completed=1, cancelled=False, max_rounds_reached=False)
    check("persist error recorded", any(label == "session_persist" for label, _ in r.cleanup_errors))
    check("event still present", r.agent_completed_event is not None)

    print("[5] save_trajectory raises — recorded, never raised out")
    agent = _FakeAgent(save_raises=True)
    r = finalize_turn(agent, agent_id="a5", rounds_completed=1, cancelled=False, max_rounds_reached=False)
    check("trajectory error recorded", any(label == "trajectory_save" for label, _ in r.cleanup_errors))
    check("trajectory_saved still False", r.trajectory_saved is False)
    check("event still present", r.agent_completed_event is not None)

    print("[6] both raise — both recorded, never raised out")
    agent = _FakeAgent(persist_raises=True, save_raises=True)
    r = finalize_turn(agent, agent_id="a6", rounds_completed=1, cancelled=False, max_rounds_reached=False)
    check("two errors", len(r.cleanup_errors) == 2, f"n={len(r.cleanup_errors)}")
    check("event still present", r.agent_completed_event is not None)

    print("[7] cancelled flag propagates to event")
    agent = _FakeAgent()
    r = finalize_turn(agent, agent_id="a7", rounds_completed=1, cancelled=True, max_rounds_reached=False)
    check("cancelled", r.agent_completed_event.cancelled is True)

    print("[8] no _save_trajectory method — skipped silently")
    class _NoTraj:
        def __init__(self):
            self._messages = []
        def _persist_session(self):
            pass
    agent = _NoTraj()
    r = finalize_turn(agent, agent_id="a8", rounds_completed=1, cancelled=False, max_rounds_reached=False)
    check("no trajectory error", not any(label == "trajectory_save" for label, _ in r.cleanup_errors))
    check("trajectory_saved False", r.trajectory_saved is False)
    check("no errors total", len(r.cleanup_errors) == 0)

    print("[9] no _persist_session method — skipped silently")
    class _NoPersist:
        def __init__(self):
            self._messages = []
    agent = _NoPersist()
    r = finalize_turn(agent, agent_id="a9", rounds_completed=1, cancelled=False, max_rounds_reached=False)
    check("no persist error", not any(label == "session_persist" for label, _ in r.cleanup_errors))

    print("[10] TurnFinalizerResult.record() doesn't raise")
    r = TurnFinalizerResult()
    r.record("test_label", RuntimeError("boom"))
    check("error recorded", len(r.cleanup_errors) == 1)
    check("label correct", r.cleanup_errors[0][0] == "test_label")
    check("message format", "RuntimeError" in r.cleanup_errors[0][1])

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL TURN_FINALIZER SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
