"""Smoke test for IterationBudget."""
from __future__ import annotations

import sys
import threading

from harness.agent.iteration_budget import IterationBudget


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] basic consume")
    b = IterationBudget(3)
    check("c1", b.consume() is True)
    check("c2", b.consume() is True)
    check("c3", b.consume() is True)
    check("c4 exhausted", b.consume() is False)
    check("used=3", b.used == 3)
    check("remaining=0", b.remaining == 0)

    print("[2] refund")
    b.refund()
    check("after refund used=2", b.used == 2)
    check("remaining=1", b.remaining == 1)
    check("can consume again", b.consume() is True)
    check("consume exhausts", b.consume() is False)

    print("[2b] refund at 0 is no-op")
    b2 = IterationBudget(2)
    b2.consume()
    b2.consume()
    check("exhausted", b2.used == 2)
    b2.refund()
    check("refund from 2 = 1", b2.used == 1)
    b2.refund()
    b2.refund()
    check("stays at 0", b2.used == 0)

    print("[3] reset")
    b.reset(max_total=5)
    check("used=0 after reset", b.used == 0)
    check("max_total=5", b.max_total == 5)

    print("[4] reset without max")
    b.reset()
    check("max_total still 5", b.max_total == 5)

    print("[5] thread-safety")
    b.reset(max_total=1000)
    consumed = []

    def worker() -> None:
        for _ in range(100):
            if b.consume():
                consumed.append(1)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("exactly 1000 consumed", b.used == 1000, f"used={b.used}")
    check("1000 success markers", len(consumed) == 1000, f"n={len(consumed)}")

    print("[6] invalid max_total")
    try:
        IterationBudget(0)
        check("rejected", False)
    except ValueError:
        check("rejected", True)

    print("[7] negative max_total")
    try:
        IterationBudget(-5)
        check("rejected", False)
    except ValueError:
        check("rejected", True)

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL ITERATION BUDGET SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
