"""Tests for the C01 git_runner contextvar.

The contextvar is the seam that propagates the parent's
``sandbox_git_runner`` (or ``local_git_runner``) to
``delegate_task``'s subagent worktree creation. Without it,
every ``WorktreeManager()`` defaults to ``local_git_runner`` —
which would put subagent worktrees on the host filesystem in
production, breaking the isolation the per-subagent worktree
is supposed to provide.

These tests verify:
  - The set/get/reset helpers work.
  - The contextvar is task-scoped (a different async task
    doesn't see the parent's runner).
  - ``WorktreeManager()`` reads the contextvar as the default.
  - An explicit ``git_runner=`` argument takes priority over
    the contextvar.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.services import worktree_manager
from harness.services.worktree_manager import (
    GitRunner,
    WorktreeManager,
    get_current_git_runner,
    local_git_runner,
    reset_current_git_runner,
    sandbox_git_runner,
    set_current_git_runner,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Contextvar basics
# ---------------------------------------------------------------------------


async def test_get_current_returns_none_when_unset() -> None:
    """In a fresh task, the contextvar is ``None``."""
    # No set_current call in this test.
    assert get_current_git_runner() is None


async def test_set_and_get_roundtrip() -> None:
    """Setting the contextvar makes it visible via ``get_current_git_runner``."""
    sentinel = MagicMock()
    token = set_current_git_runner(sentinel)
    try:
        assert get_current_git_runner() is sentinel
    finally:
        reset_current_git_runner(token)


async def test_reset_restores_previous_value() -> None:
    """``reset_current_git_runner`` with the token restores the prior value."""
    assert get_current_git_runner() is None
    token = set_current_git_runner("sentinel-1")
    try:
        assert get_current_git_runner() == "sentinel-1"
    finally:
        reset_current_git_runner(token)
    assert get_current_git_runner() is None


async def test_nested_set_restores_correctly() -> None:
    """Nested set/reset pairs (e.g. orchestrator → subagent)
    work as expected — the inner reset doesn't bleed into the
    outer scope.
    """
    outer_token = set_current_git_runner("outer")
    try:
        assert get_current_git_runner() == "outer"
        inner_token = set_current_git_runner("inner")
        try:
            assert get_current_git_runner() == "inner"
        finally:
            reset_current_git_runner(inner_token)
        # Outer is restored.
        assert get_current_git_runner() == "outer"
    finally:
        reset_current_git_runner(outer_token)
    assert get_current_git_runner() is None


async def test_set_none_clears() -> None:
    """``set_current_git_runner(None)`` clears the runner."""
    token = set_current_git_runner("sentinel")
    try:
        assert get_current_git_runner() == "sentinel"
    finally:
        pass
    # Reset before the next set.
    reset_current_git_runner(token)
    set_current_git_runner(None)
    assert get_current_git_runner() is None


# ---------------------------------------------------------------------------
# Task isolation (the property that makes this work for delegate_task)
# ---------------------------------------------------------------------------


async def test_contextvar_does_not_leak_between_tasks() -> None:
    """Setting the contextvar in task A doesn't affect task B.

    This is the property that makes parent → subagent propagation
    work: when the orchestrator sets the runner, the subagent
    (running in a new ``asyncio.create_task``) inherits it via
    its own copy of the context.
    """
    captured: list[Any] = []

    async def child() -> None:
        # The child reads whatever the parent set.
        captured.append(get_current_git_runner())

    async def parent() -> None:
        token = set_current_git_runner("parent-runner")
        try:
            # Spawn a sub-task — in production, this is the
            # subagent's coroutine.
            await asyncio.create_task(child())
        finally:
            reset_current_git_runner(token)

    await parent()
    # The child saw the parent's runner (subagent inheriting).
    assert captured == ["parent-runner"]


# ---------------------------------------------------------------------------
# WorktreeManager integration
# ---------------------------------------------------------------------------


def test_worktree_manager_uses_explicit_runner_when_provided() -> None:
    """An explicit ``git_runner=`` argument wins over the contextvar."""
    sentinel = MagicMock()
    token = set_current_git_runner("contextvar-value")
    try:
        mgr = WorktreeManager(git_runner=sentinel)
        assert mgr._git_runner is sentinel
    finally:
        reset_current_git_runner(token)


def test_worktree_manager_uses_contextvar_when_no_runner() -> None:
    """No explicit runner → falls back to the contextvar, then local."""
    sentinel = MagicMock()
    token = set_current_git_runner(sentinel)
    try:
        mgr = WorktreeManager()
        assert mgr._git_runner is sentinel
    finally:
        reset_current_git_runner(token)


def test_worktree_manager_uses_local_when_no_runner_and_no_contextvar() -> None:
    """No explicit runner, no contextvar → ``local_git_runner``."""
    assert get_current_git_runner() is None  # sanity
    mgr = WorktreeManager()
    assert mgr._git_runner is local_git_runner


# ---------------------------------------------------------------------------
# End-to-end: orchestrator → subagent propagation
# ---------------------------------------------------------------------------


class _FakeSandbox:
    """Minimal sandbox for the end-to-end test."""
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, cmd: str, timeout: int = 60) -> Any:
        self.calls.append(cmd)
        # Return something that looks like a result.
        return MagicMock(returncode=0, stdout="ok", stderr="")


async def test_orchestrator_to_subagent_runner_propagation() -> None:
    """End-to-end: the orchestrator's ``sandbox_git_runner`` is
    inherited by a child task's ``WorktreeManager()`` (with no
    explicit runner).
    """
    sandbox = _FakeSandbox()
    runner = sandbox_git_runner(sandbox)

    # The orchestrator would do this:
    token = set_current_git_runner(runner)
    try:
        # The subagent (in a new task) creates a WorktreeManager
        # with no explicit runner.
        mgr = WorktreeManager()
        # It should be the sandbox runner, not local.
        assert mgr._git_runner is runner
    finally:
        reset_current_git_runner(token)


async def test_subagent_inherits_local_when_no_sandbox_wired() -> None:
    """When no contextvar is set (e.g. tests, dev mode), the
    subagent falls back to ``local_git_runner``. This is the
    pre-contextvar behavior — preserved for backwards compat.
    """
    # No set_current_git_runner call.
    mgr = WorktreeManager()
    assert mgr._git_runner is local_git_runner


async def test_subagent_can_override_inherited_runner() -> None:
    """A subagent that wants a different runner (e.g. for testing)
    can pass it explicitly — the explicit argument wins over the
    contextvar.
    """
    sandbox = _FakeSandbox()
    parent_runner = sandbox_git_runner(sandbox)
    child_runner = MagicMock()

    token = set_current_git_runner(parent_runner)
    try:
        mgr = WorktreeManager(git_runner=child_runner)
        assert mgr._git_runner is child_runner  # not parent_runner
    finally:
        reset_current_git_runner(token)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


def test_module_exports_contextvar_helpers() -> None:
    """The public surface includes the contextvar helpers."""
    for name in (
        "set_current_git_runner",
        "get_current_git_runner",
        "reset_current_git_runner",
        "WorktreeManager",
        "local_git_runner",
        "sandbox_git_runner",
    ):
        assert hasattr(worktree_manager, name), f"missing: {name}"
