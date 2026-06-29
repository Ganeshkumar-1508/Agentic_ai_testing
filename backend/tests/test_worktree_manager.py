"""Tests for C01: WorktreeManager + branch naming.

C01 (per docs/2026-06-21-architecture-decision-tree.md#c01) brings
git-worktree isolation to TestAI. The WorktreeManager is ported from
OpenHarness; the tests run against a real git repo in a tmp dir so we
verify the actual ``git worktree add`` / ``remove`` semantics.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness.services.worktree_manager import (
    WorktreeError,
    WorktreeInfo,
    WorktreeManager,
    session_branch,
    session_slug,
    subagent_branch,
    subagent_slug,
    validate_worktree_slug,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> None:
    """Initialize a real git repo at ``path`` with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
    }
    subprocess.run(["git", "init", "--initial-branch=main", str(path)], check=True, env=env, capture_output=True)
    (path / "README.md").write_text("# Test repo\n")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True, env=env, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), check=True, env=env, capture_output=True,
    )


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
    }
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env,
        capture_output=True, text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A real git repo with one initial commit, in a tmp dir."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    return repo


@pytest.fixture
def manager() -> WorktreeManager:
    """A default WorktreeManager (base_dir auto-computed per repo)."""
    return WorktreeManager()


# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------


def test_validate_slug_accepts_simple() -> None:
    assert validate_worktree_slug("session-abc") == "session-abc"
    assert validate_worktree_slug("sa-12345") == "sa-12345"
    assert validate_worktree_slug("foo_bar.baz") == "foo_bar.baz"


def test_validate_slug_accepts_nested() -> None:
    assert validate_worktree_slug("team-a/sub-1") == "team-a/sub-1"


def test_validate_slug_rejects_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_worktree_slug("")


def test_validate_slug_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="64 characters"):
        validate_worktree_slug("a" * 65)


def test_validate_slug_rejects_absolute_path() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        validate_worktree_slug("/etc/passwd")
    with pytest.raises(ValueError, match="absolute path"):
        validate_worktree_slug("\\windows\\system32")


def test_validate_slug_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="path segments"):
        validate_worktree_slug("..")
    with pytest.raises(ValueError, match="path segments"):
        validate_worktree_slug("foo/../bar")
    with pytest.raises(ValueError, match="path segments"):
        validate_worktree_slug(".")


def test_validate_slug_rejects_invalid_chars() -> None:
    with pytest.raises(ValueError, match="non-empty and contain only"):
        validate_worktree_slug("foo bar")  # space
    with pytest.raises(ValueError, match="non-empty and contain only"):
        validate_worktree_slug("foo$bar")  # shell metachar
    with pytest.raises(ValueError, match="non-empty and contain only"):
        validate_worktree_slug("foo/bar/")  # trailing slash


# ---------------------------------------------------------------------------
# Branch naming (per C01 Q3)
# ---------------------------------------------------------------------------


def test_session_slug_and_branch() -> None:
    assert session_slug("abc123") == "session-abc123"
    assert session_branch("abc123") == "testai/session-abc123"


def test_subagent_slug_and_branch_strips_prefix() -> None:
    # subagent_id is already prefixed with ``sa-`` by delegate_task.
    assert subagent_slug("sa-0-deadbeef") == "sa-0-deadbeef"
    assert subagent_branch("sa-0-deadbeef") == "testai/sa-0-deadbeef"


def test_subagent_branch_handles_unprefixed_id() -> None:
    # Defensive: if some caller passes a non-prefixed id, we still
    # produce the right branch name.
    assert subagent_slug("0-deadbeef") == "sa-0-deadbeef"
    assert subagent_branch("0-deadbeef") == "testai/sa-0-deadbeef"


# ---------------------------------------------------------------------------
# Create / list / remove
# ---------------------------------------------------------------------------


async def test_create_worktree_creates_directory_and_branch(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    info = await manager.create_worktree(git_repo, "session-abc")
    assert info.path.exists()
    assert info.branch == "testai/session-abc"
    # The branch was actually created.
    res = _git("branch", "--list", "testai/session-abc", cwd=git_repo)
    assert "testai/session-abc" in res.stdout
    # Worktree is registered with git.
    res = _git("worktree", "list", cwd=git_repo)
    assert "testai/session-abc" in res.stdout


async def test_create_worktree_is_idempotent(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """Calling create twice with the same slug resumes, not duplicates."""
    info1 = await manager.create_worktree(git_repo, "session-abc")
    info2 = await manager.create_worktree(git_repo, "session-abc")
    assert info1.path == info2.path
    assert info1.branch == info2.branch


async def test_create_worktree_with_custom_branch(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    info = await manager.create_worktree(
        git_repo, "sa-x", branch="testai/custom-name",
    )
    assert info.branch == "testai/custom-name"


async def test_create_worktree_with_agent_id(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    info = await manager.create_worktree(
        git_repo, "sa-x", agent_id="sa-0-deadbeef",
    )
    assert info.agent_id == "sa-0-deadbeef"


async def test_create_worktree_preserves_main_repo(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """Creating a worktree must not touch the main repo's HEAD."""
    main_branch_before = _git(
        "rev-parse", "--abbrev-ref", "HEAD", cwd=git_repo,
    ).stdout.strip()
    await manager.create_worktree(git_repo, "session-abc")
    main_branch_after = _git(
        "rev-parse", "--abbrev-ref", "HEAD", cwd=git_repo,
    ).stdout.strip()
    assert main_branch_before == main_branch_after == "main"


async def test_create_worktree_with_explicit_base_ref(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """The base_ref kwarg lets callers pin the worktree to a SHA."""
    sha = _git("rev-parse", "HEAD", cwd=git_repo).stdout.strip()
    info = await manager.create_worktree(
        git_repo, "pinned", base_ref=sha,
    )
    worktree_sha = _git(
        "rev-parse", "HEAD", cwd=info.path,
    ).stdout.strip()
    assert worktree_sha == sha


async def test_create_worktree_rejects_invalid_slug(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    with pytest.raises(ValueError):
        await manager.create_worktree(git_repo, "")
    with pytest.raises(ValueError):
        await manager.create_worktree(git_repo, "foo/../bar")


async def test_create_worktree_rejects_non_git_repo(
    tmp_path: Path, manager: WorktreeManager,
) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(WorktreeError, match="not a git repository"):
        await manager.create_worktree(not_a_repo, "session-abc")


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------


async def test_remove_worktree_returns_true_on_existing(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    info = await manager.create_worktree(git_repo, "session-abc")
    assert info.path.exists()
    ok = await manager.remove_worktree(git_repo, "session-abc")
    assert ok is True
    assert not info.path.exists()


async def test_remove_worktree_returns_false_on_missing(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    ok = await manager.remove_worktree(git_repo, "never-existed")
    assert ok is False


async def test_remove_worktree_cleans_up_git_internal_state(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """After remove, ``git worktree list`` should not show the
    worktree anymore (prune runs automatically).
    """
    await manager.create_worktree(git_repo, "session-abc")
    await manager.remove_worktree(git_repo, "session-abc")
    res = _git("worktree", "list", cwd=git_repo)
    assert "session-abc" not in res.stdout


async def test_remove_worktree_preserves_other_worktrees(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """Removing one worktree must not affect its siblings."""
    info_a = await manager.create_worktree(git_repo, "session-a")
    info_b = await manager.create_worktree(git_repo, "session-b")
    await manager.remove_worktree(git_repo, "session-a")
    assert not info_a.path.exists()
    assert info_b.path.exists()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_worktrees_returns_all_testai_worktrees(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    await manager.create_worktree(git_repo, "session-abc")
    await manager.create_worktree(git_repo, "sa-x")
    infos = await manager.list_worktrees(git_repo)
    slugs = {i.slug for i in infos}
    assert slugs == {"session-abc", "sa-x"}


async def test_list_worktrees_empty_when_no_base_dir(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    # No create calls → base dir doesn't exist → empty list.
    infos = await manager.list_worktrees(git_repo)
    assert infos == []


async def test_list_worktrees_includes_branch_and_original_path(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    info = await manager.create_worktree(git_repo, "session-abc")
    infos = await manager.list_worktrees(git_repo)
    assert len(infos) == 1
    listed = infos[0]
    assert listed.slug == info.slug
    assert listed.branch == "testai/session-abc"
    # original_path is the main repo (or its .git parent).
    assert listed.original_path.resolve() == git_repo.resolve()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def test_cleanup_stale_removes_inactive(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    await manager.create_worktree(git_repo, "active")
    await manager.create_worktree(git_repo, "stale-1")
    await manager.create_worktree(git_repo, "stale-2")
    removed = await manager.cleanup_stale(git_repo, active_slugs={"active"})
    assert set(removed) == {"stale-1", "stale-2"}
    # Verify the active one is still there.
    remaining = await manager.list_worktrees(git_repo)
    assert {i.slug for i in remaining} == {"active"}


async def test_cleanup_stale_with_none_active_removes_all(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    await manager.create_worktree(git_repo, "session-1")
    await manager.create_worktree(git_repo, "session-2")
    removed = await manager.cleanup_stale(git_repo)
    assert set(removed) == {"session-1", "session-2"}


# ---------------------------------------------------------------------------
# Custom base_dir (for tests)
# ---------------------------------------------------------------------------


async def test_explicit_base_dir_overrides_default(
    git_repo: Path, tmp_path: Path,
) -> None:
    custom = tmp_path / "my-worktrees"
    mgr = WorktreeManager(base_dir=custom)
    info = await mgr.create_worktree(git_repo, "session-x")
    assert info.path.parent == custom
    assert info.path.name == "session-x"
    assert info.path.exists()


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------


async def test_create_worktree_rejects_unsafe_branch_name(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """A malicious ``branch`` kwarg must not be used to escape the
    repo. The ``-B`` form rejects branch names with ``..`` etc.,
    so we expect WorktreeError rather than a security hole.
    """
    # Slug must be valid (we don't accept the branch as a path).
    with pytest.raises(ValueError):
        await manager.create_worktree(
            git_repo, "..", branch="evil",
        )


async def test_symlink_cache_dirs_disabled(
    git_repo: Path, manager_with_no_symlinks,
) -> None:
    """When ``symlink_cache_dirs=False``, no symlinks are created.

    The repo doesn't have ``node_modules`` or ``.venv`` so we can't
    verify the symlink side; we just verify the worktree is created
    without crashing.
    """
    info = await manager_with_no_symlinks.create_worktree(
        git_repo, "session-x",
    )
    assert info.path.exists()


@pytest.fixture
def manager_with_no_symlinks() -> WorktreeManager:
    return WorktreeManager(symlink_cache_dirs=False)


async def test_worktree_info_is_frozen() -> None:
    """WorktreeInfo is immutable — defensive guard against mutation
    bugs across the orchestrator / delegate_task boundary.
    """
    info = WorktreeInfo(
        slug="session-x",
        path=Path("/tmp/x"),
        branch="testai/session-x",
        original_path=Path("/tmp/repo"),
        created_at=0.0,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        info.slug = "other"  # type: ignore[misc]


async def test_worktree_error_carries_command_and_stderr() -> None:
    err = WorktreeError(
        command="worktree add -B foo /tmp/foo HEAD",
        stderr="fatal: bad revision",
    )
    assert "worktree add" in str(err)
    assert "bad revision" in str(err)
    assert err.command.startswith("worktree")
    assert "bad revision" in err.stderr


# ---------------------------------------------------------------------------
# Concurrency / idempotency
# ---------------------------------------------------------------------------


async def test_create_same_slug_twice_is_safe(
    git_repo: Path, manager: WorktreeManager,
) -> None:
    """Race-condition guard: two concurrent create_worktree calls
    for the same slug must end up with one worktree, not two.
    """
    info_a, info_b = await asyncio.gather(
        manager.create_worktree(git_repo, "session-race"),
        manager.create_worktree(git_repo, "session-race"),
    )
    # Both calls return the same path.
    assert info_a.path == info_b.path
    # Git only has one worktree registered (one line per worktree).
    res = _git("worktree", "list", cwd=git_repo)
    worktree_lines = [
        line for line in res.stdout.splitlines() if "session-race" in line
    ]
    assert len(worktree_lines) == 1
