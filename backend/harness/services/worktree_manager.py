"""WorktreeManager — git-worktree isolation for sessions + subagents.

C01 (per docs/2026-06-21-architecture-decision-tree.md#c01):
  Q1: Isolation unit = hybrid (per-session + per-subagent)
  Q2: Physical location = in container's volume at
      ``/workspace/repo/.testai-worktrees/<name>/``
  Q3: Branch naming = ``testai/session-<id>`` and ``testai/sa-<id>``
  Q4: Merge strategy = per-subagent draft PR (via the existing
      ``commit_and_open_pr`` tool)
  Q5: Per-session worktree's role = orchestrator's scratch space
  Q6: Cleanup = auto-remove after PR is opened (or on subagent
      failure)

Ported from OpenHarness' ``openharness/swarm/worktree.py:135`` (the
load-bearing pattern is unchanged; TestAI-specific bits are the
branch naming, the orchestrator integration, and the draft-PR
hookup via the existing ``commit_and_open_pr`` tool).

The WorktreeManager is git-runner-agnostic: it takes a
``git_runner`` callable that runs ``git`` commands and returns
``(returncode, stdout, stderr)``. Production wires this to the
sandbox's ``env.run()``; tests use the local-host runner
(``local_git_runner``).

Public surface (stable):
  WorktreeManager, WorktreeInfo, WorktreeError, validate_worktree_slug,
  GitRunner, local_git_runner, sandbox_git_runner
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contextvar — propagate the parent's git runner to subagents
# ---------------------------------------------------------------------------
#
# C01 (deferred): the orchestrator creates per-subagent worktrees via
# `delegate_task`. The orchestrator itself uses ``sandbox_git_runner``
# (git runs inside the Docker container). The subagent runs in the
# same container but ``delegate_task`` creates a fresh
# ``WorktreeManager()`` which would default to ``local_git_runner``
# (host shell). The worktree would land on the host filesystem
# instead of inside the container.
#
# The fix: the orchestrator sets this contextvar to its
# ``sandbox_git_runner`` before spawning the subagent. The
# subagent's ``WorktreeManager()`` reads it as the default
# runner. Mirrors the C04 ``set_current_kg_context`` pattern
# (see ``services/knowledge_graph_syncer.py``).
#
# Public API:
#   set_current_git_runner(runner)  — set the runner for the
#     current task (and any sub-tasks spawned from it).
#   get_current_git_runner()         — read the runner; returns
#     ``None`` if no runner was set in this context.
#   reset_current_git_runner(token) — restore the previous
#     value (used as a context manager pattern).
#
# ``local_git_runner`` is the fallback when nothing is set —
# same behavior as the pre-contextvar code.

_current_git_runner: contextvars.ContextVar["GitRunner | None"] = (
    contextvars.ContextVar("testai_current_git_runner", default=None)
)


def set_current_git_runner(runner: "GitRunner | None") -> "contextvars.Token":
    """Set the current task's git runner. Returns a token that
    can be passed to :func:`reset_current_git_runner`.

    Pattern: same as :func:`harness.services.knowledge_graph_syncer.
    set_current_kg_context`.
    """
    return _current_git_runner.set(runner)


def get_current_git_runner() -> "GitRunner | None":
    """Return the current task's git runner, or ``None`` if none
    was set. Callers should fall back to :func:`local_git_runner`
    if this returns ``None``.
    """
    return _current_git_runner.get()


def reset_current_git_runner(token: "contextvars.Token") -> None:
    """Restore the previous value (use after :func:`set_current_git_runner`)."""
    _current_git_runner.reset(token)


# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------


_VALID_SEGMENT = re.compile(r"^[a-zA-Z0-9._-]+$")
_MAX_SLUG_LENGTH = 64
_COMMON_SYMLINK_DIRS = ("node_modules", ".venv", "__pycache__", ".tox")


def validate_worktree_slug(slug: str) -> str:
    """Sanitize and validate a worktree slug.

    Rules (matches OpenHarness):
      - Max 64 characters
      - Each '/'-separated segment matches ``[a-zA-Z0-9._-]+``
      - ``.`` and ``..`` segments are rejected (path traversal)
      - No leading/trailing ``/`` (absolute paths rejected)
    """
    if not slug:
        raise ValueError("Worktree slug must not be empty")
    if len(slug) > _MAX_SLUG_LENGTH:
        raise ValueError(
            f"Worktree slug must be {_MAX_SLUG_LENGTH} characters or fewer (got {len(slug)})"
        )
    if slug.startswith("/") or slug.startswith("\\"):
        raise ValueError(f"Worktree slug must not be an absolute path: {slug!r}")
    for segment in slug.split("/"):
        if segment in (".", ".."):
            raise ValueError(
                f'Worktree slug {slug!r}: must not contain "." or ".." path segments'
            )
        if not _VALID_SEGMENT.match(segment):
            raise ValueError(
                f"Worktree slug {slug!r}: each segment must be non-empty and contain only "
                "letters, digits, dots, underscores, and dashes"
            )
    return slug


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorktreeError(RuntimeError):
    """Raised when a git worktree operation fails.

    Carries the failing command + the original stderr so callers
    can surface useful error messages without re-running git.
    """
    def __init__(self, command: str, stderr: str, message: str | None = None) -> None:
        self.command = command
        self.stderr = stderr
        super().__init__(message or f"git {command} failed: {stderr.strip()}")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorktreeInfo:
    """Metadata about a managed git worktree.

    Attributes:
      slug: The validated slug (e.g. ``session-abc123``).
      path: Absolute path to the worktree directory.
      branch: Branch name checked out in the worktree.
      original_path: Absolute path to the main repo the worktree
        was created from.
      created_at: Unix timestamp the worktree was created (or
        resumed from).
      agent_id: Optional identifier of the agent that owns this
        worktree (set by ``delegate_task``).
    """
    slug: str
    path: Path
    branch: str
    original_path: Path
    created_at: float
    agent_id: str | None = None


# ---------------------------------------------------------------------------
# Git runner abstraction
# ---------------------------------------------------------------------------


#: Async git runner signature. Takes ``(args, cwd)`` and returns
#: ``(returncode, stdout, stderr)``. ``args`` is the argv list
#: (without the leading ``git``). ``cwd`` is the working dir.
GitRunner = Callable[[tuple[str, ...], Path], Awaitable[tuple[int, str, str]]]


async def local_git_runner(
    args: tuple[str, ...], cwd: Path,
) -> tuple[int, str, str]:
    """Default git runner: spawns ``git`` on the local host.

    Used in tests. Production callers (orchestrator, delegate_task)
    pass :func:`sandbox_git_runner` instead.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""},
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace").strip(),
        stderr_bytes.decode(errors="replace").strip(),
    )


def sandbox_git_runner(env: Any) -> GitRunner:
    """Build a git runner that executes inside a TestAI sandbox.

    Args:
      env: A ``SandboxEnvironment``-like object with an ``async
        run(cmd: str, timeout: int = ...) -> CompletedProcess``
        method (mirrors ``harness.backends.base.BaseEnvironment``).

    Returns:
      A :data:`GitRunner` that prepends ``cd <cwd> &&`` to each
      ``git`` command and parses the exit code from the
      CompletedProcess.
    """
    async def _run(args: tuple[str, ...], cwd: Path) -> tuple[int, str, str]:
        # Build a single shell command. We don't use ``shell=False``
        # because the sandbox runner is a shell wrapper; using
        # argv form would require changing the signature.
        quoted_args = " ".join(_shell_quote(a) for a in args)
        cmd = f"cd {_shell_quote(str(cwd))} && git {quoted_args}"
        try:
            result = await env.run(cmd, timeout=60)
        except Exception as exc:
            return (1, "", f"sandbox git runner failed: {exc}")
        returncode = getattr(result, "returncode", 0) or 0
        return (
            returncode,
            (getattr(result, "stdout", "") or "").strip(),
            (getattr(result, "stderr", "") or "").strip(),
        )
    return _run


def _shell_quote(s: str) -> str:
    """Single-quote a string for safe inclusion in a shell command.

    Mirrors :func:`_q` in :mod:`commit_and_open_pr_tool` — same
    approach, kept local to avoid a cross-module import.
    """
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def session_slug(session_id: str) -> str:
    """Build the worktree slug for a session.

    Per C01 Q3: ``testai/session-<id>``. We strip the worktree
    prefix from the path; the branch name is built separately
    via :func:`session_branch`.
    """
    return f"session-{session_id}"


def subagent_slug(subagent_id: str) -> str:
    """Build the worktree slug for a subagent.

    Per C01 Q3: ``testai/sa-<id>``. The subagent_id is already
    prefixed ``sa-...`` by the delegate_task tool, so we don't
    re-prefix.
    """
    return f"sa-{subagent_id}" if not subagent_id.startswith("sa-") else subagent_id


def session_branch(session_id: str) -> str:
    """Branch name for the per-session worktree.

    Per C01 Q3: ``testai/session-<id>``.
    """
    return f"testai/session-{session_id}"


def subagent_branch(subagent_id: str) -> str:
    """Branch name for the per-subagent worktree.

    Per C01 Q3: ``testai/sa-<id>``. Strips the ``sa-`` prefix from
    the subagent_id to avoid ``testai/sa-sa-...``.
    """
    if subagent_id.startswith("sa-"):
        subagent_id = subagent_id[3:]
    return f"testai/sa-{subagent_id}"


async def _symlink_common_dirs(repo_path: Path, worktree_path: Path) -> None:
    """Symlink large cache/build dirs from main repo to worktree.

    Mirrors OpenHarness' pattern so per-worktree disk usage stays
    bounded. Failure is non-fatal (some filesystems disallow
    symlinks, e.g. some Windows mounts).
    """
    for dir_name in _COMMON_SYMLINK_DIRS:
        src = repo_path / dir_name
        dst = worktree_path / dir_name
        if dst.exists() or dst.is_symlink():
            continue
        if not src.exists():
            continue
        try:
            dst.symlink_to(src)
        except OSError as exc:
            logger.debug("symlink %s -> %s failed: %s", dst, src, exc)


WORKTREE_INCLUDE_FILENAME = ".worktreeinclude"


def _read_worktree_include(repo_path: Path) -> list[str]:
    """Read ``.worktreeinclude`` from the main repo.

    Format: one path per line, ``#`` comments, blank lines OK.
    Paths are relative to the repo root. The file lists
    additional files/dirs that the worktree should **copy**
    (not symlink) — typically env files, secret files, or
    per-worktree state that should NOT be shared.

    Example::

        # .worktreeinclude
        .env
        .env.local
        secrets/
        config/local.json

    This is the inverse of the symlink list (``_COMMON_SYMLINK_DIRS``)
    — the symlink list is for big directories that are
    safe to share; the include list is for small files that
    need to be per-worktree.
    """
    include_path = repo_path / WORKTREE_INCLUDE_FILENAME
    if not include_path.exists() or not include_path.is_file():
        return []
    try:
        text = include_path.read_text(encoding="utf-8")
    except OSError:
        return []
    paths: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    return paths


async def _copy_included_paths(repo_path: Path, worktree_path: Path) -> None:
    """Copy paths from ``.worktreeinclude`` to the worktree.

    Copies the file or directory tree (recursively). The
    destination is created if missing. Per-worktree state
    is safe to copy — these are usually env files, secret
    files, or local config that shouldn't be shared.

    Files that are git-ignored but still tracked in
    ``.worktreeinclude`` (typical for ``.env``) are the
    primary use case.
    """
    import shutil
    for rel_path in _read_worktree_include(repo_path):
        src = repo_path / rel_path
        dst = worktree_path / rel_path
        if not src.exists():
            continue
        try:
            if src.is_dir():
                if dst.exists():
                    if dst.is_dir():
                        continue
                    dst.unlink()
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except OSError as exc:
            logger.debug(
                "worktreeinclude copy %s -> %s failed: %s",
                src, dst, exc,
            )


async def _remove_symlinks(worktree_path: Path) -> None:
    """Remove symlinks created by :func:`_symlink_common_dirs`.

    Must be called before ``git worktree remove`` so the symlinks
    don't dangle.
    """
    for dir_name in _COMMON_SYMLINK_DIRS:
        dst = worktree_path / dir_name
        if dst.is_symlink():
            try:
                dst.unlink()
            except OSError as exc:
                logger.debug("unlink %s failed: %s", dst, exc)


# ---------------------------------------------------------------------------
# WorktreeManager
# ---------------------------------------------------------------------------


class WorktreeManager:
    """Manage git worktrees for isolated TestAI session + subagent execution.

    Per C01 Q2, worktrees live in the container's volume at
    ``<repo_path>/.testai-worktrees/<slug>/``. The directory is
    namespaced under the repo itself (matches Claude Code's pattern
    of ``.claude/worktrees/``).

    Args:
      git_runner: Async callable that runs git commands. Defaults
        to :func:`local_git_runner` (host shell). Production
        callers should pass :func:`sandbox_git_runner` so the
        operations happen inside the container.
      base_dir: Directory under which all TestAI worktrees are
        created. Defaults to ``<repo_path>/.testai-worktrees``.
        Setting this explicitly is mostly useful for tests.
      symlink_cache_dirs: Whether to symlink ``node_modules`` /
        ``.venv`` / ``__pycache__`` / ``.tox`` from the main repo
        to the worktree (saves disk). Default ``True``.
    """

    def __init__(
        self,
        git_runner: GitRunner | None = None,
        base_dir: Path | None = None,
        *,
        symlink_cache_dirs: bool = True,
    ) -> None:
        # Resolve the git runner in priority order:
        #   1. Explicit ``git_runner`` argument (highest priority)
        #   2. The current task's contextvar (set by the orchestrator
        #      when it creates the per-session worktree, so subagents
        #      inherit the sandbox runner)
        #   3. :func:`local_git_runner` (host shell — tests + dev)
        if git_runner is not None:
            self._git_runner: GitRunner = git_runner
        else:
            ctx_runner = get_current_git_runner()
            self._git_runner: GitRunner = ctx_runner or local_git_runner
        self._explicit_base_dir = base_dir
        self._symlink_cache_dirs = symlink_cache_dirs
        # Per-(repo, slug) lock to serialize concurrent
        # ``create_worktree`` calls for the same slug.
        self._create_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._create_locks_guard = asyncio.Lock()

    def base_dir(self, repo_path: Path) -> Path:
        """Return the base dir for the given repo."""
        if self._explicit_base_dir is not None:
            return self._explicit_base_dir
        return repo_path / ".testai-worktrees"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_worktree(
        self,
        repo_path: Path,
        slug: str,
        *,
        branch: str | None = None,
        agent_id: str | None = None,
        base_ref: str = "HEAD",
    ) -> WorktreeInfo:
        """Create (or resume) a git worktree for ``slug``.

        Idempotent — repeated calls for the same slug return the
        existing worktree's info without re-running
        ``git worktree add``.

        Raises:
          ValueError: invalid slug.
          WorktreeError: the underlying ``git worktree add`` failed,
            or ``repo_path`` is not a git repository.
        """
        validate_worktree_slug(slug)
        repo_path = repo_path.resolve()

        # Verify it's a git repo (cheap pre-check before locking).
        code, _, stderr = await self._git_runner(
            ("rev-parse", "--git-dir"), repo_path,
        )
        if code != 0:
            raise WorktreeError(
                command="rev-parse --git-dir",
                stderr=stderr or f"{repo_path} is not a git repository",
                message=f"Cannot create worktree: {repo_path} is not a git repository",
            )

        # Serialize concurrent creates for the same (repo, slug).
        lock = await self._lock_for(repo_path, slug)
        async with lock:
            return await self._create_worktree_locked(
                repo_path, slug, branch=branch, agent_id=agent_id,
                base_ref=base_ref,
            )

    async def _create_worktree_locked(
        self,
        repo_path: Path,
        slug: str,
        *,
        branch: str | None,
        agent_id: str | None,
        base_ref: str,
    ) -> WorktreeInfo:
        base = self.base_dir(repo_path)
        worktree_path = base / slug
        worktree_branch = branch or f"testai/{slug}"

        # Fast resume: if the worktree directory exists AND is a
        # valid git worktree, return its info without re-running
        # add. We check ``worktree_path.exists()`` first because
        # git's rev-parse requires cwd to be a real directory
        # (Windows raises NotADirectoryError on non-existent cwd).
        if worktree_path.exists():
            code, _, _ = await self._git_runner(
                ("rev-parse", "--git-dir"), worktree_path,
            )
            if code == 0:
                logger.debug(
                    "worktree resume: slug=%s path=%s branch=%s",
                    slug, worktree_path, worktree_branch,
                )
                return WorktreeInfo(
                    slug=slug,
                    path=worktree_path,
                    branch=worktree_branch,
                    original_path=repo_path,
                    created_at=worktree_path.stat().st_mtime,
                    agent_id=agent_id,
                )

        # New worktree: ``-B`` resets an orphan branch left by a
        # prior remove, so we don't end up in "branch already
        # exists" hell. ``git worktree add`` implicitly creates
        # any missing parent directories.
        code, _, stderr = await self._git_runner(
            ("worktree", "add", "-B", worktree_branch,
             str(worktree_path), base_ref),
            repo_path,
        )
        if code != 0:
            raise WorktreeError(
                command=f"worktree add -B {worktree_branch} {worktree_path} {base_ref}",
                stderr=stderr,
            )

        if self._symlink_cache_dirs:
            await _symlink_common_dirs(repo_path, worktree_path)
            await _copy_included_paths(repo_path, worktree_path)

        return WorktreeInfo(
            slug=slug,
            path=worktree_path,
            branch=worktree_branch,
            original_path=repo_path,
            created_at=time.time(),
            agent_id=agent_id,
        )

    async def _lock_for(self, repo_path: Path, slug: str) -> asyncio.Lock:
        """Get or create the per-(repo, slug) lock."""
        key = (str(repo_path), slug)
        async with self._create_locks_guard:
            lock = self._create_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._create_locks[key] = lock
            return lock

    async def remove_worktree(
        self,
        repo_path: Path,
        slug: str,
    ) -> bool:
        """Remove a worktree by slug.

        Returns ``True`` if the worktree was removed, ``False`` if
        it didn't exist.

        Failure mode: if the main repo path is no longer valid
        (e.g. the container was recycled), the ``git worktree
        remove`` command can't be issued. We fall back to
        ``rm -rf`` on the worktree directory.
        """
        validate_worktree_slug(slug)
        repo_path = repo_path.resolve()
        worktree_path = self.base_dir(repo_path) / slug

        if not worktree_path.exists():
            return False

        # Remove symlinks first so they don't dangle.
        await _remove_symlinks(worktree_path)

        code, _, stderr = await self._git_runner(
            ("worktree", "remove", "--force", str(worktree_path)),
            repo_path,
        )
        if code != 0:
            logger.warning(
                "git worktree remove failed for %s: %s — falling back to rm -rf",
                worktree_path, stderr,
            )
            # Fallback: blow away the directory. ``git worktree prune``
            # later cleans up the stale entry in the worktree list.
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception as exc:
                logger.error("rm -rf %s failed: %s", worktree_path, exc)
                return False

        # Always prune so a stale entry doesn't accumulate.
        try:
            await self._git_runner(("worktree", "prune"), repo_path)
        except Exception:
            pass

        return True

    async def list_worktrees(self, repo_path: Path) -> list[WorktreeInfo]:
        """Return :class:`WorktreeInfo` for every TestAI worktree
        under the base dir.

        Reads from the local filesystem (``iterdir`` + ``stat``);
        for production callers using a sandbox runner, the path
        is the host-side path (the sandbox's volume is shared
        with the host). If the sandbox is on a different
        filesystem, callers should adapt this method.
        """
        base = self.base_dir(repo_path)
        if not base.exists():
            return []

        results: list[WorktreeInfo] = []
        for child in base.iterdir():
            if not child.is_dir():
                continue
            code, _, _ = await self._git_runner(
                ("rev-parse", "--git-dir"), child,
            )
            if code != 0:
                continue

            rc, branch_out, _ = await self._git_runner(
                ("rev-parse", "--abbrev-ref", "HEAD"), child,
            )
            branch = branch_out if rc == 0 else "unknown"

            rc2, common_dir, _ = await self._git_runner(
                ("rev-parse", "--git-common-dir"), child,
            )
            if rc2 == 0 and common_dir:
                original_path = Path(common_dir).resolve().parent
            else:
                original_path = repo_path

            results.append(WorktreeInfo(
                slug=child.name,
                path=child,
                branch=branch,
                original_path=original_path,
                created_at=child.stat().st_mtime,
            ))
        return results

    async def cleanup_stale(
        self,
        repo_path: Path,
        active_slugs: set[str] | None = None,
    ) -> list[str]:
        """Remove TestAI worktrees that are no longer active."""
        worktrees = await self.list_worktrees(repo_path)
        removed: list[str] = []
        for info in worktrees:
            if active_slugs is not None and info.slug in active_slugs:
                continue
            ok = await self.remove_worktree(repo_path, info.slug)
            if ok:
                removed.append(info.slug)
        return removed

