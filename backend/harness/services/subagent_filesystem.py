"""Per-subagent worktree isolation (C6).

Each write-capable subagent gets its own git worktree so parallel
subagents don't collide on the same filesystem.

Two adapters at one seam:
  - ``WorktreeFilesystem`` — creates a git worktree per subagent,
    merges back on completion, auto-cleanups on exit.
  - ``SharedFilesystem`` — today's behavior (all subagents share
    the same working tree). Used for explore (read-only) subagents
    and in tests.

The ``factory_wrapper`` seam in ``Subagent.spawn()`` is the
integration point: the orchestrator passes a wrapper that creates
the filesystem for each spawned subagent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def subagent_worktree_slug(subagent_id: str) -> str:
    """Slug for a per-subagent worktree directory.

    Mirrors :func:`harness.services.worktree_manager.subagent_slug`.
    """
    return f"agent-{subagent_id}" if not subagent_id.startswith("agent-") else subagent_id


def subagent_worktree_branch(subagent_id: str) -> str:
    """Branch name for a per-subagent worktree.

    Mirrors :func:`harness.services.worktree_manager.subagent_branch`.
    """
    clean_id = subagent_id.replace("agent-", "sa-", 1) if subagent_id.startswith("agent-") else subagent_id
    if clean_id.startswith("sa-"):
        clean_id = clean_id[3:]
    return f"testai/sa-{clean_id}"


# ---------------------------------------------------------------------------
# Merge result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeResult:
    """Outcome of merging a subagent's worktree back to the parent."""
    success: bool
    subagent_id: str
    n_commits: int = 0
    conflict_files: list[str] | None = None
    error: str = ""


# ---------------------------------------------------------------------------
# SubagentFilesystem Protocol
# ---------------------------------------------------------------------------


class SubagentFilesystem(Protocol):
    """Isolation strategy for a single subagent.

    Each subagent gets its own filesystem context. The orchestrator
    creates one per spawned subagent and wires it via the
    ``factory_wrapper`` seam.
    """

    async def setup(self, subagent_id: str, repo_path: Path, parent_branch: str) -> Path:
        """Prepare the subagent's working directory.

        Returns the absolute path the subagent should work in.
        """
        ...

    async def merge_back(
        self, subagent_id: str, repo_path: Path,
        session_id: str = "",
    ) -> MergeResult:
        """Merge the subagent's changes back to the parent branch.

        When ``session_id`` is provided, the merge checks the
        subagent's per-tool-call ``rca_verdict`` for DEFECT verdicts.
        If DEFECT found, the merge is blocked (the subagent produced
        real bugs). If only FLAKY, the merge proceeds with a warning.

        Called after the subagent completes. Returns a MergeResult.
        """
        ...

    async def cleanup(self, subagent_id: str, repo_path: Path) -> None:
        """Remove the subagent's worktree.

        Called regardless of success or failure.
        """
        ...


# ---------------------------------------------------------------------------
# SharedFilesystem — today's behavior (no isolation)
# ---------------------------------------------------------------------------


class SharedFilesystem:
    """No isolation: all subagents write to the same working tree.

    The default adapter. Suitable for explore (read-only) subagents
    and test environments.
    """

    async def setup(self, subagent_id: str, repo_path: Path, parent_branch: str) -> Path:
        return repo_path

    async def merge_back(
        self, subagent_id: str, repo_path: Path,
        session_id: str = "",
    ) -> MergeResult:
        return MergeResult(success=True, subagent_id=subagent_id)

    async def cleanup(self, subagent_id: str, repo_path: Path) -> None:
        pass


# ---------------------------------------------------------------------------
# WorktreeFilesystem — git worktree per subagent
# ---------------------------------------------------------------------------


class WorktreeFilesystem:
    """Each subagent gets its own git worktree.

    Uses ``WorktreeManager`` for the underlying git operations.
    On completion, attempts a fast-forward merge back to the parent
    branch. On conflict, returns a ``MergeResult`` with conflict
    details.
    """

    def __init__(
        self,
        git_runner: Any | None = None,
    ) -> None:
        self._git_runner = git_runner
        self._manager: Any = None

    async def _get_manager(self, repo_path: Path) -> Any:
        if self._manager is None:
            from harness.services.worktree_manager import WorktreeManager
            self._manager = WorktreeManager(
                git_runner=self._git_runner,
                base_dir=repo_path / ".testai-worktrees",
            )
        return self._manager

    async def setup(self, subagent_id: str, repo_path: Path, parent_branch: str) -> Path:
        slug = subagent_worktree_slug(subagent_id)
        branch = subagent_worktree_branch(subagent_id)
        mgr = await self._get_manager(repo_path)
        info = await mgr.create_worktree(
            repo_path, slug,
            branch=branch,
            agent_id=subagent_id,
            base_ref=parent_branch,
        )
        return info.path

    async def merge_back(
        self, subagent_id: str, repo_path: Path,
        session_id: str = "",
    ) -> MergeResult:
        branch = subagent_worktree_branch(subagent_id)
        mgr = await self._get_manager(repo_path)

        # C5/C6: check per-tool-call verdicts before merging.
        # If the subagent produced DEFECT verdicts, block the merge.
        if session_id:
            defect, flaky = await self._collect_verdicts(session_id)
            if defect:
                return MergeResult(
                    success=False, subagent_id=subagent_id,
                    error=f"Merge blocked: subagent produced {defect} DEFECT and {flaky} FLAKY verdicts. Fix defects before merging.",
                    conflict_files=[],
                )

        n_commits = await self._count_commits(repo_path, branch)

        code, stdout, stderr = await mgr._git_runner(
            ("merge", "--ff-only", branch), repo_path,
        )
        if code != 0:
            conflict_files = await self._detect_conflicts(repo_path)
            return MergeResult(
                success=False,
                subagent_id=subagent_id,
                n_commits=n_commits,
                conflict_files=conflict_files,
                error=stderr[:500],
            )
        return MergeResult(
            success=True,
            subagent_id=subagent_id,
            n_commits=n_commits,
        )

    @staticmethod
    async def _collect_verdicts(session_id: str) -> tuple[int, int]:
        """Count DEFECT and FLAKY verdicts from a subagent's artifacts.

        Returns ``(defect_count, flaky_count)``.
        """
        try:
            from harness.memory.db_context import get_db
            import json as _json
            db = get_db()
            if db is None:
                return 0, 0
            rows = await db.fetch(
                "SELECT payload::text FROM agent_artifacts "
                "WHERE session_id = $1 AND kind = 'tool_call'",
                session_id,
            )
            defect = 0
            flaky = 0
            for r in rows or []:
                try:
                    payload = r["payload"]
                    if isinstance(payload, str):
                        payload = _json.loads(payload)
                    verdict_data = (payload or {}).get("rca_verdict") or {}
                    v = str(verdict_data.get("verdict", "") or "")
                    if v == "defect":
                        defect += 1
                    elif v == "flaky":
                        flaky += 1
                except Exception:
                    continue
            return defect, flaky
        except Exception:
            return 0, 0

    async def cleanup(self, subagent_id: str, repo_path: Path) -> None:
        slug = subagent_worktree_slug(subagent_id)
        mgr = await self._get_manager(repo_path)
        try:
            await mgr.remove_worktree(repo_path, slug)
        except Exception as exc:
            logger.debug("worktree cleanup failed for %s: %s", subagent_id, exc)

    async def _count_commits(self, repo_path: Path, branch: str) -> int:
        mgr = await self._get_manager(repo_path)
        code, stdout, _ = await mgr._git_runner(
            ("rev-list", "--count", f"HEAD..{branch}"), repo_path,
        )
        return int(stdout.strip()) if code == 0 and stdout.strip() else 0

    async def _detect_conflicts(self, repo_path: Path) -> list[str]:
        mgr = await self._get_manager(repo_path)
        code, stdout, _ = await mgr._git_runner(
            ("diff", "--name-only", "--diff-filter=U"), repo_path,
        )
        if code != 0 or not stdout.strip():
            return []
        return stdout.strip().split("\n")


# ---------------------------------------------------------------------------
# Factory — decides which adapter to use based on toolset
# ---------------------------------------------------------------------------

_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "apply_patch", "write",
    "edit", "create_file", "delete_file", "rename_file",
    "bash",  # bash can write to files too
})


def requires_isolation(toolsets: list[str] | None = None) -> bool:
    """Return True if this subagent needs a dedicated worktree.

    Explore subagents (read-only tools) don't need isolation.
    Fix / test-writer / doc-updater subagents (write tools) do.
    """
    if not toolsets:
        return False
    return any(t in toolset for toolset in toolsets for t in _WRITE_TOOLS)


def filesystem_for_toolset(
    toolsets: list[str] | None = None,
    git_runner: Any | None = None,
) -> SubagentFilesystem:
    """Factory: return the right filesystem adapter for the toolset."""
    if requires_isolation(toolsets):
        return WorktreeFilesystem(git_runner=git_runner)
    return SharedFilesystem()
