"""Tests for the migrated RunPhase classes (C09).

C09: each inlined step in ``OrchestratorEngine.run_single`` becomes
a :class:`harness.phases.RunPhase`. This file tests the migrated
phases in isolation &mdash; hand-built :class:`RunContext`, mocked
external dependencies, no orchestrator.

The first phase to migrate is :class:`EvidenceBundlePhase` (the
end-of-pipeline bundler). It is a pure, self-contained phase
(no side effects, no writes) which is why it's the proving
ground for the pattern.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.evidence_bundle import EvidenceBundlePhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


@pytest.mark.asyncio
async def test_evidence_bundle_attaches_summary_to_coordinator_result() -> None:
    summary = "### Files Changed\n- `a.py`\n"
    fake_db = MagicMock()
    fake_bundler = MagicMock()
    fake_bundler.build_finding_summary = AsyncMock(return_value=summary)
    with patch("harness.evidence.EvidenceBundler", return_value=fake_bundler), \
         patch("harness.memory.db_context.get_db", return_value=fake_db):
        ctx = _ctx()
        result = await EvidenceBundlePhase().execute(ctx)
    assert result.coordinator_result is not None
    assert result.coordinator_result["evidence_summary"] == summary


@pytest.mark.asyncio
async def test_evidence_bundle_skips_when_no_db() -> None:
    """No DB wired (local dev) — phase skips, ctx unchanged."""
    with patch("harness.memory.db_context.get_db", return_value=None):
        ctx = _ctx()
        result = await EvidenceBundlePhase().execute(ctx)
    assert result is ctx  # same instance, no replace
    assert result.coordinator_result is None


@pytest.mark.asyncio
async def test_evidence_bundle_skips_when_no_session_id() -> None:
    """No session_id (defensive) &mdash; phase skips, ctx unchanged."""
    ctx = _ctx(session_id="")
    result = await EvidenceBundlePhase().execute(ctx)
    assert result is ctx
    assert result.coordinator_result is None


@pytest.mark.asyncio
async def test_evidence_bundle_skips_when_bundler_returns_none() -> None:
    """Bundler returns None (no artifacts) — phase skips, ctx unchanged."""
    fake_db = MagicMock()
    fake_bundler = MagicMock()
    fake_bundler.build_finding_summary = AsyncMock(return_value=None)
    with patch("harness.evidence.EvidenceBundler", return_value=fake_bundler), \
         patch("harness.memory.db_context.get_db", return_value=fake_db):
        ctx = _ctx()
        result = await EvidenceBundlePhase().execute(ctx)
    assert result is ctx
    assert result.coordinator_result is None


@pytest.mark.asyncio
async def test_evidence_bundle_can_skip_catches_exception() -> None:
    """Bundler raises — phase swallows (can_skip=True), ctx unchanged."""
    fake_db = MagicMock()
    fake_bundler = MagicMock()
    fake_bundler.build_finding_summary = AsyncMock(
        side_effect=RuntimeError("db is down"),
    )
    with patch("harness.evidence.EvidenceBundler", return_value=fake_bundler), \
         patch("harness.memory.db_context.get_db", return_value=fake_db):
        ctx = _ctx()
        result = await EvidenceBundlePhase().execute(ctx)
    assert result is ctx
    assert result.coordinator_result is None


@pytest.mark.asyncio
async def test_evidence_bundle_preserves_existing_coordinator_result() -> None:
    """If the ctx already has coordinator_result (e.g. set by an
    earlier phase), the bundler appends — doesn't clobber."""
    summary = "### Files Changed\n- `b.py`\n"
    fake_db = MagicMock()
    fake_bundler = MagicMock()
    fake_bundler.build_finding_summary = AsyncMock(return_value=summary)
    with patch("harness.evidence.EvidenceBundler", return_value=fake_bundler), \
         patch("harness.memory.db_context.get_db", return_value=fake_db):
        ctx = _ctx()
        ctx = replace(ctx, coordinator_result={"existing": "value"})
        result = await EvidenceBundlePhase().execute(ctx)
    assert result.coordinator_result == {
        "existing": "value",
        "evidence_summary": summary,
    }


def test_evidence_bundle_has_can_skip_true() -> None:
    """The phase advertises ``can_skip=True`` so the pipeline
    catches its exceptions and continues."""
    assert EvidenceBundlePhase.can_skip is True


def test_evidence_bundle_phase_name() -> None:
    assert EvidenceBundlePhase.phase_name == "evidence_bundle"


def test_evidence_bundle_satisfies_run_phase_protocol() -> None:
    """The phase implements the RunPhase protocol (duck-typed)."""
    phase: RunPhase = EvidenceBundlePhase()
    assert hasattr(phase, "phase_name")
    assert hasattr(phase, "can_skip")
    assert callable(phase.execute)
