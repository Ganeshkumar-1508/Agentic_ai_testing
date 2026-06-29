"""Cross-repo change coordination model and logic.

Enables one TestAI run to coordinate changes across multiple repositories,
creating linked PRs with Depends-On headers following the industry convention
(from Mergify, Zuul CI, depends-on-action, Claude Code Toolkit, Tembo).

API Body Example:
    POST /api/jobs (with a JobSpec whose context.repos has this shape)
    {
        "repos": [
            {"url": "https://github.com/org/shared-lib", "token": "ghp_xxx", "branch": "main"},
            {"url": "https://github.com/org/service-a", "token": "ghp_yyy", "branch": "main"},
        ],
        "requirements": "Add authentication middleware to shared-lib and update service-a to use it"
    }
"""

from __future__ import annotations
import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class RepoChangeStatus(enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    COMMITTED = "committed"
    PR_CREATED = "pr_created"
    FAILED = "failed"


@dataclass
class RepoConfig:
    """Configuration for a single repository in a multi-repo change set."""
    url: str                          # Full clone URL (https://github.com/org/repo)
    token: str | None = None          # Per-repo auth token
    branch: str = "main"              # Target branch
    provider: str = ""                # "github", "gitlab", "bitbucket" — auto-detected from URL
    dependencies: list[str] = field(default_factory=list)  # List of repo URLs this repo depends on

    def __post_init__(self):
        if not self.provider:
            self.provider = self._detect_provider()

    def _detect_provider(self) -> str:
        if "github.com" in self.url:
            return "github"
        elif "gitlab.com" in self.url:
            return "gitlab"
        elif "bitbucket.org" in self.url:
            return "bitbucket"
        return "github"  # default


@dataclass
class RepoChange:
    """Tracks a single repo's change within a multi-repo operation."""
    repo: RepoConfig
    status: RepoChangeStatus = RepoChangeStatus.PENDING
    branch_name: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    pr_number: int = 0
    diff_summary: str = ""
    error: str | None = None


@dataclass
class CrossRepoChange:
    """A coordinated change spanning multiple repositories.

    Follows the CrossRepoChange entity pattern from Tembo and Claude Code Toolkit.
    Uses Depends-On header convention from Mergify/Zuul CI (de facto standard).
    """
    id: str                                            # Unique ID (e.g., "testai-crc-{timestamp}")
    description: str                                   # User's requirements
    repo_changes: list[RepoChange] = field(default_factory=list)
    status: str = "pending"                            # "pending" | "in_progress" | "all_prs_created" | "partial" | "failed"
    created_at: float = 0.0
    error: str | None = None

    @property
    def dependency_order(self) -> list[RepoChange]:
        """Return repo changes in topological dependency order.

        Uses a simple DAG sort: if repo-B depends on repo-A, repo-A comes first.
        Falls back to insertion order if no dependencies specified.
        """
        # Build adjacency list
        by_url = {c.repo.url: c for c in self.repo_changes}
        visited = set()
        ordered = []

        def visit(change: RepoChange):
            if change.repo.url in visited:
                return
            visited.add(change.repo.url)
            for dep_url in change.repo.dependencies:
                if dep_url in by_url:
                    visit(by_url[dep_url])
            ordered.append(change)

        for change in self.repo_changes:
            visit(change)

        return ordered

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API responses."""
        return {
            "id": self.id,
            "description": self.description[:200],
            "status": self.status,
            "repo_changes": [
                {
                    "url": rc.repo.url,
                    "status": rc.status.value,
                    "branch": rc.branch_name,
                    "pr_url": rc.pr_url,
                    "pr_number": rc.pr_number,
                    "diff_summary": rc.diff_summary[:500] if rc.diff_summary else "",
                    "error": rc.error,
                }
                for rc in self.repo_changes
            ],
            "dependency_order": [rc.repo.url for rc in self.dependency_order],
            "created_at": self.created_at,
            "error": self.error,
        }


def build_depends_on_block(
    repo_change: RepoChange,
    all_changes: list[RepoChange],
    change_id: str = "",
) -> str:
    """Build the Depends-On and Cross-Repo-Change-ID block for a PR body.

    Follows the industry convention from Mergify, Zuul CI, and depends-on-action.
    Every PR in a cross-repo change set gets this block.

    Example output:
    ```
    ---
    Cross-Repo-Change-ID: testai-crc-1712345678
    Cross-Repo-Changes: 2
    This-PR: https://github.com/org/shared-lib/pull/42
    Depends-On: https://github.com/org/service-a/pull/43
    Merge-Order: shared-lib, service-a
    ```
    """
    lines = [
        "---",
        f"Cross-Repo-Change-ID: {change_id}",
        f"Cross-Repo-Changes: {len(all_changes)}",
        "",
        "This PR is part of a coordinated multi-repo change set.",
        "Merge in the following order to avoid CI breakage:",
    ]
    for i, rc in enumerate(all_changes):
        prefix = "  " if rc.repo.url != repo_change.repo.url else "→ "
        lines.append(f"{prefix}{i+1}. {rc.repo.url}")
    lines.append("")
    depends_urls = [
        rc.pr_url for rc in all_changes
        if rc.pr_url and rc.repo.url != repo_change.repo.url
    ]
    if depends_urls:
        lines.append("Depends-On:")  # Mergify/Zuul convention
        for url in depends_urls:
            lines.append(f"- {url}")
    return "\n".join(lines)


def coordinate_multi_repo_results(
    run_id: str,
    repo_results: list[dict[str, Any]],
) -> CrossRepoChange:
    """Build a CrossRepoChange from run_multi results.

    Takes the per-repo results from OrchestratorEngine.run_multi and produces
    a coordinated CrossRepoChange with dependency ordering and Depends-On blocks.
    This is the missing link between run_multi and cross-repo PR coordination.

    Args:
        run_id: The parent run ID.
        repo_results: List of result dicts from run_multi, each containing
                      repo, success, board_id, session_id, error.

    Returns:
        A CrossRepoChange with dependency-ordered repo_changes.
    """
    change_id = f"testai-crc-{int(datetime.now(timezone.utc).timestamp())}"
    repo_changes = []
    for i, r in enumerate(repo_results):
        repo_changes.append(RepoChange(
            repo=RepoConfig(url=r.get("repo", ""), branch=r.get("branch", "main")),
            status=RepoChangeStatus.PR_CREATED if r.get("success") else RepoChangeStatus.FAILED,
            branch_name=r.get("branch", "main"),
            pr_url=r.get("pr_url", ""),
            pr_number=r.get("pr_number", 0),
            diff_summary=r.get("diff_summary", ""),
            error=r.get("error"),
        ))

    cross = CrossRepoChange(
        id=change_id,
        description=f"Coordinated multi-repo change across {len(repo_changes)} repos",
        repo_changes=repo_changes,
        status="all_prs_created" if all(r.get("success") for r in repo_results) else "partial",
        created_at=datetime.now(timezone.utc).timestamp(),
    )

    # Generate Depends-On blocks for each successful change
    for rc in cross.repo_changes:
        if rc.status == RepoChangeStatus.PR_CREATED:
            rc.diff_summary = (
                (rc.diff_summary + "\n\n" if rc.diff_summary else "")
                + build_depends_on_block(rc, cross.repo_changes, change_id)
            )

    logger.info(
        "Cross-repo coordination %s: %d repos, status=%s",
        change_id, len(repo_changes), cross.status,
    )
    return cross
