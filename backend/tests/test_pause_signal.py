"""Tests for the pause-signal module.

The pause signal is an in-memory flag per spec_id that the
cancel_watcher sets when it observes a "paused" status. The
orchestrator's run_single polls the signal at safe points and
saves a JobCheckpoint before returning.

Public surface tested:
  - set_pause_signal(spec_id)
  - check_pause_signal(spec_id) -> bool
  - clear_pause_signal(spec_id)
  - pause_signal_event(spec_id) -> asyncio.Event
  - signal_count(spec_id) -> int
  - _reset_all_signals()  (test-only)
"""
from __future__ import annotations

import asyncio

import pytest

from harness.services.pause_signal import (
    _reset_all_signals,
    check_pause_signal,
    clear_pause_signal,
    pause_signal_event,
    set_pause_signal,
    signal_count,
)


@pytest.fixture(autouse=True)
def _clean():
    _reset_all_signals()
    yield
    _reset_all_signals()


def test_set_and_check():
    assert check_pause_signal("spec-1") is False
    set_pause_signal("spec-1")
    assert check_pause_signal("spec-1") is True


def test_clear_resets_state():
    set_pause_signal("spec-1")
    assert check_pause_signal("spec-1") is True
    clear_pause_signal("spec-1")
    assert check_pause_signal("spec-1") is False


def test_signals_are_isolated_per_spec():
    set_pause_signal("spec-1")
    assert check_pause_signal("spec-1") is True
    assert check_pause_signal("spec-2") is False


def test_signal_count_tracks_sets():
    assert signal_count("spec-1") == 0
    set_pause_signal("spec-1")
    assert signal_count("spec-1") == 1
    # Idempotent: setting again is a no-op (count stays).
    set_pause_signal("spec-1")
    assert signal_count("spec-1") == 1
    clear_pause_signal("spec-1")
    assert signal_count("spec-1") == 0


def test_clear_unknown_spec_is_safe():
    clear_pause_signal("spec-never-set")  # should not raise


def test_check_unknown_spec_is_safe():
    assert check_pause_signal("spec-never-set") is False


def test_reset_all_signals_clears_everything():
    set_pause_signal("spec-1")
    set_pause_signal("spec-2")
    set_pause_signal("spec-3")
    _reset_all_signals()
    assert check_pause_signal("spec-1") is False
    assert check_pause_signal("spec-2") is False
    assert check_pause_signal("spec-3") is False
    assert signal_count("spec-1") == 0
    assert signal_count("spec-2") == 0
    assert signal_count("spec-3") == 0


@pytest.mark.asyncio
async def test_event_wakes_blocked_coroutine():
    """The signal's asyncio.Event wakes a coroutine that's
    blocked in ``event.wait()``. This is how the orchestrator
    could block on the pause signal in a future sprint
    (today it polls).
    """
    event = pause_signal_event("spec-wait")

    async def waiter():
        await event.wait()
        return "woken"

    waiter_task = asyncio.create_task(waiter())
    # Give the waiter a chance to start waiting.
    await asyncio.sleep(0.01)
    assert not waiter_task.done()

    set_pause_signal("spec-wait")
    result = await asyncio.wait_for(waiter_task, timeout=1.0)
    assert result == "woken"


@pytest.mark.asyncio
async def test_event_clears_after_check():
    """The event is reusable: setting then clearing allows the
    next ``event.wait()`` to block again. Mirrors the typical
    Event.clear() semantics.
    """
    event = pause_signal_event("spec-reuse")

    set_pause_signal("spec-reuse")
    assert event.is_set()
    clear_pause_signal("spec-reuse")
    assert not event.is_set()

    # Now set again — the event should be set again.
    set_pause_signal("spec-reuse")
    assert event.is_set()


def test_event_is_lazy():
    """Calling ``pause_signal_event`` for a new spec_id creates
    the event on first access.
    """
    event = pause_signal_event("spec-lazy")
    assert event is not None
    assert isinstance(event, asyncio.Event)
    # Calling again returns the same event (not a new one).
    event2 = pause_signal_event("spec-lazy")
    assert event is event2
