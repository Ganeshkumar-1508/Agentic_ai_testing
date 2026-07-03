"""Tests for the zombie-session / orphan-container reaper loop.

The reaper runs as a ManagedTask in api/main.py:lifespan and calls two
independent functions:
  1. sweep_orphan_sessions  (async, DB-level)
  2. reap_orphan_containers (sync, Docker CLI-level)

We test each function in isolation plus the wiring loop behaviour.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# sweep_orphan_sessions
# ---------------------------------------------------------------------------


class _FakeDB:
    """Minimal DB with an ``execute`` that returns ``UPDATE N`` strings."""

    def __init__(self, update_count: int = 0, *, raise_on: bool = False) -> None:
        self._pool = object()  # non-None sentinel
        self._update_count = update_count
        self._raise_on = raise_on
        self.last_sql: str = ""
        self.last_args: tuple[Any, ...] = ()

    async def execute(self, sql: str, *args: Any) -> str:
        self.last_sql = sql
        self.last_args = args
        if self._raise_on:
            raise RuntimeError("db down")
        return f"UPDATE {self._update_count}"


async def test_sweep_returns_zero_when_no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """sweep_orphan_sessions returns 0 when DB is not wired."""
    from harness.tools import subagent
    monkeypatch.setattr(subagent, "get_db", lambda: None)
    from harness.tools.subagent import sweep_orphan_sessions
    assert await sweep_orphan_sessions() == 0


async def test_sweep_returns_zero_when_no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """sweep_orphan_sessions returns 0 when pool is None."""
    from harness.tools import subagent

    class _NoPoolDB:
        _pool = None
    monkeypatch.setattr(subagent, "get_db", lambda: _NoPoolDB())
    from harness.tools.subagent import sweep_orphan_sessions
    assert await sweep_orphan_sessions() == 0


async def test_sweep_marks_orphan_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    """When DB reports UPDATE 3, sweep returns 3."""
    from harness.tools import subagent
    fake_db = _FakeDB(update_count=3)
    monkeypatch.setattr(subagent, "get_db", lambda: fake_db)
    from harness.tools.subagent import sweep_orphan_sessions
    result = await sweep_orphan_sessions(max_age_seconds=1800)
    assert result == 3
    assert "UPDATE sessions" in fake_db.last_sql
    assert "orphan-sweep" in fake_db.last_sql
    assert fake_db.last_args[0] == "1800 seconds"


async def test_sweep_survives_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DB error returns 0 instead of crashing."""
    from harness.tools import subagent
    monkeypatch.setattr(subagent, "get_db", lambda: _FakeDB(raise_on=True))
    from harness.tools.subagent import sweep_orphan_sessions
    assert await sweep_orphan_sessions() == 0


async def test_sweep_does_not_target_root_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SQL must filter to parent_session_id IS NOT NULL."""
    from harness.tools import subagent
    fake_db = _FakeDB(update_count=0)
    monkeypatch.setattr(subagent, "get_db", lambda: fake_db)
    from harness.tools.subagent import sweep_orphan_sessions
    await sweep_orphan_sessions()
    assert "parent_session_id IS NOT NULL" in fake_db.last_sql


# ---------------------------------------------------------------------------
# reap_orphan_containers
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def test_reap_returns_zero_when_docker_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `docker ps` returns non-zero, reap returns 0."""
    from harness.backends import docker as docker_mod
    monkeypatch.setattr(
        docker_mod.subprocess, "run",
        lambda *a, **kw: _FakeCompletedProcess(returncode=1),
    )
    from harness.backends.docker import reap_orphan_containers
    assert reap_orphan_containers() == 0


def test_reap_returns_zero_when_no_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If there are no exited containers, reap returns 0."""
    from harness.backends import docker as docker_mod
    monkeypatch.setattr(
        docker_mod.subprocess, "run",
        lambda *a, **kw: _FakeCompletedProcess(returncode=0, stdout=""),
    )
    from harness.backends.docker import reap_orphan_containers
    assert reap_orphan_containers() == 0


def test_reap_removes_old_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Containers older than max_age_seconds are removed."""
    from harness.backends import docker as docker_mod

    def _fake_run(cmd: list[str], **kw: Any) -> _FakeCompletedProcess:
        # docker ps returns two container IDs
        if "ps" in cmd:
            return _FakeCompletedProcess(0, "abc123\ndef456\n")
        # docker inspect for abc123 (old — should be reaped)
        if "inspect" in cmd and "abc123" in cmd:
            old_time = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(seconds=1200)
            ).isoformat()
            return _FakeCompletedProcess(0, old_time)
        # docker inspect for def456 (recent — should NOT be reaped)
        if "inspect" in cmd and "def456" in cmd:
            recent_time = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(seconds=30)
            ).isoformat()
            return _FakeCompletedProcess(0, recent_time)
        # docker rm
        if "rm" in cmd:
            return _FakeCompletedProcess(0)
        return _FakeCompletedProcess(1)

    monkeypatch.setattr(docker_mod.subprocess, "run", _fake_run)
    from harness.backends.docker import reap_orphan_containers
    removed = reap_orphan_containers(max_age_seconds=600)
    assert removed == 1  # only abc123 was old enough


def test_reap_survives_subprocess_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subprocess.TimeoutExpired returns 0, not a crash."""
    from harness.backends import docker as docker_mod
    monkeypatch.setattr(
        docker_mod.subprocess, "run",
        MagicMock(side_effect=subprocess.TimeoutExpired("docker", 15)),
    )
    from harness.backends.docker import reap_orphan_containers
    assert reap_orphan_containers() == 0


# ---------------------------------------------------------------------------
# _reaper_loop wiring — replicate the loop body from api/main.py
# to avoid importing FastAPI (heavy deps not installed locally).
# ---------------------------------------------------------------------------


async def _reaper_loop_body(
    sweep_fn: Any,
    reap_fn: Any,
    max_sleep_cycles: int = 1,
) -> None:
    """Replicate the reaper loop from api/main.py for testing."""
    sleep_count = 0
    while True:
        try:
            n_sessions = await sweep_fn(max_age_seconds=3600)
            if n_sessions:
                logging.getLogger(__name__).info(
                    "Reaper: swept %d orphan session(s)", n_sessions,
                )
        except Exception as exc:
            logging.getLogger(__name__).debug(
                "Reaper session sweep failed: %s", exc,
            )
        try:
            loop = asyncio.get_running_loop()
            n_containers = await loop.run_in_executor(None, reap_fn)
            if n_containers:
                logging.getLogger(__name__).info(
                    "Reaper: reaped %d orphan container(s)", n_containers,
                )
        except Exception as exc:
            logging.getLogger(__name__).debug(
                "Reaper container reap failed: %s", exc,
            )
        sleep_count += 1
        if sleep_count >= max_sleep_cycles:
            return
        await asyncio.sleep(0)


async def test_reaper_loop_calls_both_functions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reaper loop calls sweep_orphan_sessions and
    reap_orphan_containers, and logs their results."""
    sweep_count = [0]
    reap_count = [0]

    async def _fake_sweep(max_age_seconds: int = 3600) -> int:
        sweep_count[0] += 1
        return 2

    def _fake_reap() -> int:
        reap_count[0] += 1
        return 1

    caplog.set_level(logging.INFO)
    await _reaper_loop_body(_fake_sweep, _fake_reap)

    assert sweep_count[0] == 1
    assert reap_count[0] == 1
    assert any("swept 2 orphan session" in r.message for r in caplog.records)
    assert any("reaped 1 orphan container" in r.message for r in caplog.records)


async def test_reaper_loop_survives_sweep_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If sweep_orphan_sessions raises, the loop still calls
    reap_orphan_containers."""
    reap_count = [0]

    async def _explode_sweep(max_age_seconds: int = 3600) -> int:
        raise RuntimeError("db exploded")

    def _fake_reap() -> int:
        reap_count[0] += 1
        return 0

    caplog.set_level(logging.DEBUG)
    await _reaper_loop_body(_explode_sweep, _fake_reap)

    # reap still ran despite sweep failure
    assert reap_count[0] == 1
    # debug-level log about the failure
    assert any("sweep failed" in r.message for r in caplog.records)


async def test_reaper_loop_survives_reap_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If reap_orphan_containers raises, the loop still completes."""
    sweep_count = [0]

    async def _fake_sweep(max_age_seconds: int = 3600) -> int:
        sweep_count[0] += 1
        return 0

    def _explode_reap() -> int:
        raise RuntimeError("docker exploded")

    caplog.set_level(logging.DEBUG)
    await _reaper_loop_body(_fake_sweep, _explode_reap)

    assert sweep_count[0] == 1
    assert any("reap failed" in r.message for r in caplog.records)
