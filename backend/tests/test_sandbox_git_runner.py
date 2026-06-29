"""Tests for the C01 production git runner.

The orchestrator wires ``sandbox_git_runner(env)`` into the
``WorktreeManager`` so git commands run inside the Docker
sandbox (not on the host). These tests verify the runner
constructs the right command, parses the exit code, and
handles failures.
"""
from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.services.worktree_manager import (
    local_git_runner,
    sandbox_git_runner,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeSandboxResult:
    """Mimics subprocess.CompletedProcess — has stdout, stderr, returncode."""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class _FakeSandbox:
    """Minimal sandbox stand-in with an async ``run`` method."""
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "",
                 raise_exc: bool = False) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raise_exc = raise_exc
        self.calls: list[tuple[str, int]] = []

    async def run(self, cmd: str, timeout: int = 60) -> _FakeSandboxResult:
        self.calls.append((cmd, timeout))
        if self.raise_exc:
            raise RuntimeError("sandbox run failed")
        return _FakeSandboxResult(
            stdout=self.stdout,
            stderr=self.stderr,
            returncode=self.returncode,
        )


# ---------------------------------------------------------------------------
# local_git_runner (sanity)
# ---------------------------------------------------------------------------


async def test_local_git_runner_runs_git_on_host(tmp_path) -> None:
    """Sanity check: local_git_runner actually runs git (via a real
    subprocess) on the host filesystem.
    """
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    code, out, err = await local_git_runner(
        ("rev-parse", "--git-dir"), tmp_path,
    )
    assert code == 0
    assert str(tmp_path) in out or ".git" in out


# ---------------------------------------------------------------------------
# sandbox_git_runner
# ---------------------------------------------------------------------------


async def test_sandbox_runner_builds_correct_command() -> None:
    """The runner prepends ``cd <cwd> &&`` and quotes the args."""
    env = _FakeSandbox(returncode=0, stdout="ok")
    runner = sandbox_git_runner(env)
    code, out, err = await runner(
        ("rev-parse", "--git-dir"), "/workspace/repo",
    )
    assert code == 0
    assert out == "ok"
    # The command should have ``cd /workspace/repo && git rev-parse --git-dir``.
    cmd, _ = env.calls[0]
    assert "cd" in cmd
    assert "/workspace/repo" in cmd
    assert "git" in cmd
    assert "rev-parse" in cmd
    assert "--git-dir" in cmd


async def test_sandbox_runner_quotes_paths_with_spaces() -> None:
    """The runner must handle paths with spaces (the C01 Q3 worktree
    base_dir could be ``/workspace/My Project``).
    """
    env = _FakeSandbox(returncode=0, stdout="ok")
    runner = sandbox_git_runner(env)
    code, _, _ = await runner(
        ("worktree", "list"),
        "/workspace/My Project",
    )
    cmd, _ = env.calls[0]
    # Path with spaces must be quoted (single-quote escape).
    assert "'/workspace/My Project'" in cmd or '"/workspace/My Project"' in cmd


async def test_sandbox_runner_quotes_args_with_spaces() -> None:
    """Git args with spaces (e.g. branch names with spaces) are quoted."""
    env = _FakeSandbox(returncode=0, stdout="ok")
    runner = sandbox_git_runner(env)
    code, _, _ = await runner(
        ("worktree", "add", "-B", "test branch with space", "/path", "HEAD"),
        "/repo",
    )
    cmd, _ = env.calls[0]
    assert "'test branch with space'" in cmd


async def test_sandbox_runner_returns_zero_on_success() -> None:
    env = _FakeSandbox(returncode=0, stdout="out", stderr="")
    runner = sandbox_git_runner(env)
    code, out, err = await runner(("status",), "/repo")
    assert code == 0
    assert out == "out"
    assert err == ""


async def test_sandbox_runner_returns_nonzero_on_failure() -> None:
    env = _FakeSandbox(returncode=128, stdout="", stderr="fatal: bad")
    runner = sandbox_git_runner(env)
    code, out, err = await runner(("worktree", "add"), "/repo")
    assert code == 128
    assert err == "fatal: bad"


async def test_sandbox_runner_handles_exception() -> None:
    """A ``run`` exception (e.g. sandbox unreachable) is treated as
    a non-zero exit; the runner returns ``(1, "", error_message)``.
    """
    env = _FakeSandbox(raise_exc=True)
    runner = sandbox_git_runner(env)
    code, out, err = await runner(("status",), "/repo")
    assert code == 1
    assert out == ""
    assert "sandbox git runner failed" in err


async def test_sandbox_runner_passes_timeout() -> None:
    """The runner passes the timeout to the sandbox ``run`` method
    (so the sandbox can enforce it).
    """
    env = _FakeSandbox(returncode=0, stdout="ok")
    runner = sandbox_git_runner(env)
    await runner(("fetch",), "/repo")
    assert env.calls[0][1] == 60  # the runner's default


async def test_sandbox_runner_strips_trailing_whitespace() -> None:
    env = _FakeSandbox(returncode=0, stdout="  hello  \n", stderr="  ")
    runner = sandbox_git_runner(env)
    _, out, err = await runner(("status",), "/repo")
    assert out == "hello"
    assert err == ""


async def test_sandbox_runner_handles_none_stdout_stderr() -> None:
    """If the sandbox returns ``stdout=None`` (some sandboxes do),
    the runner must not crash.
    """
    class _BrokenSandbox:
        async def run(self, cmd: str, timeout: int = 60) -> Any:
            return _FakeSandboxResult(stdout=None, stderr=None, returncode=0)
    runner = sandbox_git_runner(_BrokenSandbox())
    code, out, err = await runner(("status",), "/repo")
    assert code == 0
    assert out == ""
    assert err == ""


async def test_sandbox_runner_integration_with_worktree_manager(
    tmp_path,
) -> None:
    """End-to-end: the WorktreeManager uses ``sandbox_git_runner`` to
    create a real worktree via a fake sandbox.

    This is the seam that ``orchestrator.py:341`` wires in
    production. The test verifies the runner + manager compose
    correctly (no real git in the sandbox — we just verify the
    command that would be issued).
    """
    import subprocess
    subprocess.run(["git", "init", str(tmp_path), "--initial-branch=main"], check=True, capture_output=True)
    (tmp_path / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True, capture_output=True)

    # Fake sandbox that runs commands locally.
    class _LocalSandbox:
        def __init__(self) -> None:
            self.cwd = str(tmp_path)
            self.commands: list[str] = []

        async def run(self, cmd: str, timeout: int = 60) -> _FakeSandboxResult:
            self.commands.append(cmd)
            # Strip the leading ``cd <cwd> && git`` and run locally.
            import re
            m = re.match(r"^cd '([^']+)' && git (.+)$", cmd)
            if m is None:
                return _FakeSandboxResult(returncode=1, stderr="bad cmd")
            cwd, git_args = m.group(1), m.group(2)
            proc = subprocess.run(
                ["git"] + shlex.split(git_args),
                cwd=cwd, capture_output=True, text=True,
                env={"GIT_TERMINAL_PROMPT": "0"},
            )
            return _FakeSandboxResult(
                stdout=proc.stdout, stderr=proc.stderr,
                returncode=proc.returncode,
            )

    sandbox = _LocalSandbox()
    from harness.services.worktree_manager import (
        WorktreeManager, session_branch, session_slug,
    )
    wt = WorktreeManager(git_runner=sandbox_git_runner(sandbox))
    info = await wt.create_worktree(
        tmp_path, session_slug("abc123"), branch=session_branch("abc123"),
    )
    assert info.path.exists()
    assert info.branch == "testai/session-abc123"
    # The worktree was created via the sandbox runner (no real git
    # was run on the host). The args are shell-quoted, so we check
    # for the substrings "worktree" and "add" near each other (the
    # runner quotes each arg with single quotes).
    worktree_add_called = any(
        "worktree" in c and "add" in c and "testai/session-abc123" in c
        for c in sandbox.commands
    )
    assert worktree_add_called, f"worktree add not in: {sandbox.commands}"
    # And the branch is registered in the local repo.
    proc = subprocess.run(
        ["git", "branch", "--list", "testai/session-abc123"],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert "testai/session-abc123" in proc.stdout
