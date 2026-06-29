"""Tests for RunSummaryPhase."""

from __future__ import annotations

import pytest

from harness.phases import RunContext
from harness.phases.run_summary import RunSummaryPhase


class FakeDB:
    def __init__(self):
        self.executed = []

    async def execute(self, query: str, *args):
        self.executed.append((query, args))


@pytest.mark.asyncio
async def test_run_summary_phase_skips_without_coordinator_result():
    phase = RunSummaryPhase()
    ctx = RunContext(run_id="test", session_id="s", db=FakeDB())
    result = await phase.execute(ctx)
    assert result is not None
    assert len(result.errors) == 0  # skipped


@pytest.mark.asyncio
async def test_run_summary_phase_stores_summary():
    phase = RunSummaryPhase()
    db = FakeDB()
    ctx = RunContext(
        run_id="r1", session_id="s1", repo_url="https://github.com/org/repo",
        goal="fix all lint errors", branch="main", db=db,
        coordinator_result={"success": True, "task_count": 3},
    )
    result = await phase.execute(ctx)
    assert len(result.errors) == 1
    assert "run_summary" in result.errors[0]
