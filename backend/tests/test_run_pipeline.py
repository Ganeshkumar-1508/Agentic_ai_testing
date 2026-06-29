"""Tests for the RunPipeline iteration engine (C09)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.pipeline import RunPipeline, _append_error


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="", branch="", goal="",
    )
    base.update(overrides)
    return RunContext(**base)


class _StubPhase(RunPhase):
    """A phase that records its execution and transforms ctx."""

    def __init__(
        self,
        name: str,
        mutator: Any | None = None,
        error: Exception | None = None,
        can_skip: bool = False,
    ) -> None:
        self.phase_name = name
        self.can_skip = can_skip
        self._mutator = mutator
        self._error = error
        self.calls: list[RunContext] = []

    async def execute(self, ctx: RunContext) -> RunContext:
        self.calls.append(ctx)
        if self._error is not None:
            raise self._error
        if self._mutator is not None:
            return self._mutator(ctx)
        return ctx


@pytest.mark.asyncio
async def test_pipeline_runs_phases_in_order() -> None:
    order: list[str] = []
    a = _StubPhase("a", mutator=lambda c: (order.append("a") or c))
    b = _StubPhase("b", mutator=lambda c: (order.append("b") or c))
    c = _StubPhase("c", mutator=lambda c: (order.append("c") or c))

    pipeline = RunPipeline(orchestrator=MagicMock(), phases=[a, b, c])
    result = await pipeline.run(_ctx())

    assert order == ["a", "b", "c"]
    assert result["_pipeline_completed"] is True


@pytest.mark.asyncio
async def test_pipeline_threads_context_through_phases() -> None:
    """Each phase sees the previous phase's output as its input."""
    def add_field(ctx: RunContext) -> RunContext:
        return replace(ctx, errors=ctx.errors + ("marker",))

    a = _StubPhase("a", mutator=add_field)
    b = _StubPhase("b")
    c = _StubPhase("c")

    pipeline = RunPipeline(orchestrator=MagicMock(), phases=[a, b, c])
    await pipeline.run(_ctx())

    assert a.calls[0].errors == ()
    assert b.calls[0].errors == ("marker",)
    assert c.calls[0].errors == ("marker",)


@pytest.mark.asyncio
async def test_pipeline_fails_fast_on_non_skippable_phase() -> None:
    a = _StubPhase("a")
    boom = _StubPhase("b", error=RuntimeError("kaboom"), can_skip=False)
    c = _StubPhase("c")

    pipeline = RunPipeline(orchestrator=MagicMock(), phases=[a, boom, c])
    with pytest.raises(RuntimeError, match="kaboom"):
        await pipeline.run(_ctx())
    # c must not have run.
    assert c.calls == []


@pytest.mark.asyncio
async def test_pipeline_continues_on_skippable_phase_failure() -> None:
    a = _StubPhase("a")
    boom = _StubPhase("b", error=RuntimeError("transient"), can_skip=True)
    c = _StubPhase("c")

    pipeline = RunPipeline(orchestrator=MagicMock(), phases=[a, boom, c])
    result = await pipeline.run(_ctx())

    assert c.calls != [], "skippable phase failure must not block later phases"
    assert result["_pipeline_completed"] is True
    # The error is appended to ctx.errors for diagnostics.
    assert any("transient" in e for e in result["_ctx"].errors)


@pytest.mark.asyncio
async def test_pipeline_calls_pause_checkpoint_between_phases() -> None:
    orchestrator = MagicMock()
    orchestrator.pause_checkpoint = AsyncMock(return_value=None)
    a = _StubPhase("a")
    b = _StubPhase("b")

    pipeline = RunPipeline(orchestrator=orchestrator, phases=[a, b])
    await pipeline.run(_ctx())

    # After phase a (post_a), after phase b (post_b).
    assert orchestrator.pause_checkpoint.await_count == 2
    orchestrator.pause_checkpoint.assert_any_await(
        run_id="run-1", session_id="sess-1", phase="a",
    )
    orchestrator.pause_checkpoint.assert_any_await(
        run_id="run-1", session_id="sess-1", phase="b",
    )


@pytest.mark.asyncio
async def test_pipeline_returns_paused_dict_when_pause_fires() -> None:
    orchestrator = MagicMock()
    paused_dict = {"_pipeline_paused": True, "phase": "a"}
    orchestrator.pause_checkpoint = AsyncMock(return_value=paused_dict)
    a = _StubPhase("a")
    b = _StubPhase("b")

    pipeline = RunPipeline(orchestrator=orchestrator, phases=[a, b])
    result = await pipeline.run(_ctx())

    assert result == paused_dict
    # b must not have run.
    assert b.calls == []


@pytest.mark.asyncio
async def test_pipeline_continues_when_pause_checkpoint_raises() -> None:
    """A buggy pause_checkpoint must not break the run."""
    orchestrator = MagicMock()
    orchestrator.pause_checkpoint = AsyncMock(
        side_effect=RuntimeError("checkpoint crashed"),
    )
    a = _StubPhase("a")
    b = _StubPhase("b")

    pipeline = RunPipeline(orchestrator=orchestrator, phases=[a, b])
    result = await pipeline.run(_ctx())

    assert result["_pipeline_completed"] is True
    assert b.calls != []


@pytest.mark.asyncio
async def test_pipeline_skips_pause_when_orchestrator_has_no_method() -> None:
    """An orchestrator without pause_checkpoint runs the full pipeline."""
    orchestrator = MagicMock(spec=[])  # no attributes
    a = _StubPhase("a")
    b = _StubPhase("b")

    pipeline = RunPipeline(orchestrator=orchestrator, phases=[a, b])
    result = await pipeline.run(_ctx())

    assert result["_pipeline_completed"] is True


@pytest.mark.asyncio
async def test_pipeline_calls_on_phase_complete_hook() -> None:
    """The optional hook fires after each successful phase."""
    hook = AsyncMock()
    a = _StubPhase("a")
    b = _StubPhase("b")

    pipeline = RunPipeline(
        orchestrator=MagicMock(), phases=[a, b],
        on_phase_complete=hook,
    )
    await pipeline.run(_ctx())

    assert hook.await_count == 2
    hook.assert_any_await("a", a.calls[0])
    hook.assert_any_await("b", b.calls[0])


@pytest.mark.asyncio
async def test_pipeline_continues_when_hook_raises() -> None:
    """A buggy hook must not block later phases."""
    hook = AsyncMock(side_effect=RuntimeError("hook crashed"))
    a = _StubPhase("a")
    b = _StubPhase("b")

    pipeline = RunPipeline(
        orchestrator=MagicMock(), phases=[a, b],
        on_phase_complete=hook,
    )
    result = await pipeline.run(_ctx())

    assert result["_pipeline_completed"] is True
    assert b.calls != []


def test_append_error_preserves_existing_errors() -> None:
    ctx = _ctx()
    ctx2 = _append_error(ctx, "first")
    ctx3 = _append_error(ctx2, "second")
    assert ctx.errors == ()
    assert ctx2.errors == ("first",)
    assert ctx3.errors == ("first", "second")
    # immutability: original ctx is unchanged.
    assert ctx.errors == ()


def test_pipeline_with_empty_phase_list_returns_immediately() -> None:
    pipeline = RunPipeline(orchestrator=MagicMock(), phases=[])
    import asyncio
    result = asyncio.run(pipeline.run(_ctx()))
    assert result["_pipeline_completed"] is True
