"""Tests for the C02 team auto-dissolve sweeper.

Mirrors the test pattern used for the kanban review agent
(no asyncio-test for that one either — we test the function
directly with a fake app + in-memory store).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from harness.services import team_sweeper
from harness.services.team_sweeper import (
    SWEEPER_INTERVAL_SECONDS,
    run_team_sweeper,
    start_team_sweeper,
    stop_team_sweeper,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeApp:
    """Minimal app stand-in with the attributes sweeper reads."""
    def __init__(self, db: Any) -> None:
        self.state = MagicMock()
        self.state.db = db


class _FakeDB:
    """Minimal DB stand-in for the sweeper tests.

    The sweeper just calls ``TeamService.cleanup_completed`` which
    in turn queries the DB. We don't exercise the full SQL surface
    here (that's covered by ``test_team_service.py``); we just
    ensure the sweeper calls ``cleanup_completed`` at the right
    cadence and survives errors.
    """
    def __init__(self, raise_on_cleanup: bool = False) -> None:
        self._pool = MagicMock()
        self.raise_on_cleanup = raise_on_cleanup
        self.cleanup_calls: list[int] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        # Mirror the real cleanup query enough that the sweeper
        # thinks it ran. We return an empty list (= no teams to
        # dissolve) so the sweeper loop just continues.
        if "from teams t" in sql and "join team_members" in sql:
            self.cleanup_calls.append(0)
            if self.raise_on_cleanup:
                raise RuntimeError("db error")
            return []
        return []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        return None

    async def execute(self, sql: str, *args: Any) -> None:
        return None


@pytest.fixture
def reset_sweeper_module_state() -> Any:
    """Reset the module-level task/stop_event between tests so
    the singleton doesn't leak state.
    """
    team_sweeper._task = None
    team_sweeper._stop_event = None
    yield
    team_sweeper._task = None
    team_sweeper._stop_event = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_constants() -> None:
    """The default cadence is 60s (mirrors the kanban review agent)."""
    assert SWEEPER_INTERVAL_SECONDS == 60.0


async def test_start_returns_task(reset_sweeper_module_state) -> None:
    db = _FakeDB()
    app = _FakeApp(db)
    task = start_team_sweeper(app)
    assert task is not None
    assert task.get_name() == "team-sweeper"
    # Idempotent: a second call returns the same task.
    task2 = start_team_sweeper(app)
    assert task2 is task
    # Cleanup.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    team_sweeper._task = None
    team_sweeper._stop_event = None


async def test_stop_is_safe_when_never_started(
    reset_sweeper_module_state,
) -> None:
    """``stop_team_sweeper`` is a no-op when nothing was started."""
    await stop_team_sweeper()  # should not raise
    # Module state is still None.
    assert team_sweeper._task is None
    assert team_sweeper._stop_event is None


async def test_stop_cancels_running_sweeper(
    reset_sweeper_module_state,
) -> None:
    db = _FakeDB()
    app = _FakeApp(db)
    task = start_team_sweeper(app)
    # Wait a tick so the task is scheduled.
    await asyncio.sleep(0.05)
    # Stop — should cancel the task.
    await stop_team_sweeper()
    assert team_sweeper._task is None
    assert team_sweeper._stop_event is None


# ---------------------------------------------------------------------------
# Loop behavior
# ---------------------------------------------------------------------------


async def test_sweeper_calls_cleanup_completed(
    reset_sweeper_module_state,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The loop calls ``TeamService.cleanup_completed()`` on every
    cycle. We patch it to count invocations.
    """
    call_count = [0]

    async def _fake_cleanup(self: Any) -> list[str]:
        call_count[0] += 1
        return []

    monkeypatch.setattr(
        "harness.services.team_service.TeamService.cleanup_completed",
        _fake_cleanup,
    )

    db = _FakeDB()
    app = _FakeApp(db)
    # Run a few cycles manually (we don't want to wait 60s for the
    # real default).
    caplog.set_level(logging.INFO)
    sweeper_task = asyncio.create_task(
        run_team_sweeper(app, interval=0.05, initial_delay=0),
    )
    # Let it run a few cycles.
    await asyncio.sleep(0.25)
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass
    assert call_count[0] >= 2  # at least 2 cycles in 250ms


async def test_sweeper_survives_db_errors(
    reset_sweeper_module_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient DB error in ``cleanup_completed`` must NOT kill
    the sweeper loop — it logs and continues.
    """
    call_count = [0]

    async def _exploding_cleanup(self: Any) -> list[str]:
        call_count[0] += 1
        raise RuntimeError("transient db error")

    monkeypatch.setattr(
        "harness.services.team_service.TeamService.cleanup_completed",
        _exploding_cleanup,
    )

    db = _FakeDB()
    app = _FakeApp(db)
    sweeper_task = asyncio.create_task(
        run_team_sweeper(app, interval=0.05, initial_delay=0),
    )
    # Let it run a few cycles. Each cycle should raise + recover.
    await asyncio.sleep(0.25)
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass
    # We got past several cycles despite the error.
    assert call_count[0] >= 2


async def test_sweeper_skips_when_no_db(
    reset_sweeper_module_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the app's DB isn't wired, the sweeper just sleeps (it
    doesn't crash waiting for the DB to appear).
    """
    class _NoDBApp:
        def __init__(self) -> None:
            self.state = MagicMock()
            self.state.db = None

    app = _NoDBApp()
    sweeper_task = asyncio.create_task(
        run_team_sweeper(app, interval=0.05, initial_delay=0),
    )
    await asyncio.sleep(0.15)
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass
    # No assertion — we just verify the loop didn't crash.


async def test_sweeper_cancellation_exits_cleanly(
    reset_sweeper_module_state,
) -> None:
    """Cancelling the sweeper task while it's sleeping should exit
    cleanly without an exception.
    """
    db = _FakeDB()
    app = _FakeApp(db)
    sweeper_task = asyncio.create_task(
        run_team_sweeper(app, interval=0.1),
    )
    await asyncio.sleep(0.05)  # let it start
    sweeper_task.cancel()
    # Should re-raise CancelledError but not other exceptions.
    with pytest.raises(asyncio.CancelledError):
        await sweeper_task


# ---------------------------------------------------------------------------
# Log output
# ---------------------------------------------------------------------------


async def test_sweeper_logs_dissolved_count(
    reset_sweeper_module_state,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When cleanup_completed returns non-empty, the sweeper logs
    the count + team ids.
    """
    async def _fake_cleanup(self: Any) -> list[str]:
        return ["team-abc", "team-def"]

    monkeypatch.setattr(
        "harness.services.team_service.TeamService.cleanup_completed",
        _fake_cleanup,
    )

    db = _FakeDB()
    app = _FakeApp(db)
    caplog.set_level(logging.INFO)
    sweeper_task = asyncio.create_task(
        run_team_sweeper(app, interval=0.05, initial_delay=0),
    )
    await asyncio.sleep(0.15)
    sweeper_task.cancel()
    try:
        await sweeper_task
    except asyncio.CancelledError:
        pass
    # The log line should mention both team ids.
    assert any("team-abc" in r.message for r in caplog.records)
    assert any("team-def" in r.message for r in caplog.records)
