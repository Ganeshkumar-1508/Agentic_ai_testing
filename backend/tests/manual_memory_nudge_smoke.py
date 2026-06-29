"""Smoke test: 30-turn memory nudge (hermes pattern).

Verifies the per-turn counter + interval fire via the extracted
``check_memory_nudge(agent)`` helper. Also verifies the
``TurnContext.should_review_memory`` field.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] defaults — _memory_nudge_interval=30, _turns_since_memory=0")
    from harness.agent.turn_context import TurnContext, check_memory_nudge
    agent = SimpleNamespace(_memory_nudge_interval=30, _turns_since_memory=0)
    check("default interval is 30", agent._memory_nudge_interval == 30)
    check("initial counter is 0", agent._turns_since_memory == 0)

    print("[2] fire pattern — runs 1..29 → False, run 30 → True")
    for i in range(1, 30):
        agent._turns_since_memory = i - 1
        fired = check_memory_nudge(agent)
        check(f"  turn {i} fires={fired}", fired is False, f"counter={agent._turns_since_memory}")
    check("after 29 turns counter is 29", agent._turns_since_memory == 29,
          f"actual={agent._turns_since_memory}")

    fired = check_memory_nudge(agent)
    check("turn 30 fires=True", fired is True)
    check("counter resets to 0 after fire", agent._turns_since_memory == 0,
          f"actual={agent._turns_since_memory}")

    print("[3] subsequent turn after fire — False again")
    fired = check_memory_nudge(agent)
    check("turn 31 fires=False", fired is False)
    check("counter is 1", agent._turns_since_memory == 1)

    print("[4] interval=0 disables the nudge")
    agent2 = SimpleNamespace(_memory_nudge_interval=0, _turns_since_memory=0)
    fired_any = False
    for i in range(1, 50):
        agent2._turns_since_memory = i - 1
        if check_memory_nudge(agent2):
            fired_any = True
            check(f"  interval=0 must never fire (fired at turn {i})", False)
            break
    if not fired_any:
        check("interval=0 never fires over 50 turns", True)

    print("[5] interval=3 — fires on every 3rd turn")
    agent3 = SimpleNamespace(_memory_nudge_interval=3, _turns_since_memory=0)
    fired_at = []
    for i in range(1, 11):
        if check_memory_nudge(agent3):
            fired_at.append(i)
    check("fires at turn 3", 3 in fired_at, f"fired_at={fired_at}")
    check("fires at turn 6", 6 in fired_at, f"fired_at={fired_at}")
    check("fires at turn 9", 9 in fired_at, f"fired_at={fired_at}")
    check("does not fire at turn 4", 4 not in fired_at, f"fired_at={fired_at}")
    check("does not fire at turn 5", 5 not in fired_at, f"fired_at={fired_at}")

    print("[6] interval=2 — fires twice in 5 turns")
    agent4 = SimpleNamespace(_memory_nudge_interval=2, _turns_since_memory=0)
    fires4 = []
    for i in range(1, 6):
        if check_memory_nudge(agent4):
            fires4.append(i)
    check("fires at 2 and 4", fires4 == [2, 4], f"got {fires4}")

    print("[7] TurnContext dataclass has should_review_memory field")
    ctx = TurnContext(agent_id="a1", user_input="x", should_review_memory=True)
    check("field set", ctx.should_review_memory is True)
    check("default is False", TurnContext(agent_id="a1", user_input="x").should_review_memory is False)

    print("[8] agent without _turns_since_memory — treated as 0 (no AttributeError)")
    agent5 = SimpleNamespace(_memory_nudge_interval=3)
    # No _turns_since_memory attribute at all
    fired = check_memory_nudge(agent5)
    check("first call fires=False (counter was 0)", fired is False)
    check("counter initialized to 1", getattr(agent5, "_turns_since_memory", None) == 1)

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL MEMORY NUDGE SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
