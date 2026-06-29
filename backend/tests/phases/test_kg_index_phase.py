"""Tests for KGIndexPhase — uses a mock sandbox, tests the real Phase."""

from __future__ import annotations

import pytest

from harness.phases import RunContext
from harness.phases.kg_index import KGIndexPhase


class FakeSandbox:
    async def run(self, command: str, timeout: int = 30):
        return RunResult(stdout="inited", stderr="", returncode=0)


class RunResult:
    def __init__(self, stdout: str, stderr: str, returncode: int):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeDB:
    async def fetchrow(self, query: str, *args):
        return None
    async def fetch(self, query: str, *args):
        return []


@pytest.mark.asyncio
async def test_kg_index_phase_sets_kg_ctx():
    """KGIndexPhase should populate kg_ctx when sandbox is available."""
    phase = KGIndexPhase()
    ctx = RunContext(
        run_id="test",
        session_id="test-session",
        repo_url="https://github.com/org/repo",
        branch="main",
        goal="test goal",
        db=FakeDB(),
        sandbox=FakeSandbox(),
    )
    result = await phase.execute(ctx)
    assert result.kg_ctx is not None
    assert result.repo_url == "https://github.com/org/repo"
    assert result.run_id == "test"


@pytest.mark.asyncio
async def test_kg_index_phase_identity_preserved():
    """KGIndexPhase should preserve identity fields unchanged."""
    phase = KGIndexPhase()
    ctx = RunContext(
        run_id="test", session_id="s", repo_url="https://github.com/org/repo",
        branch="main", goal="test", db=FakeDB(), sandbox=FakeSandbox(),
    )
    result = await phase.execute(ctx)
    assert result.run_id == "test"
    assert result.session_id == "s"
    assert result.repo_url == "https://github.com/org/repo"
    assert result.goal == "test"
    assert result.branch == "main"
