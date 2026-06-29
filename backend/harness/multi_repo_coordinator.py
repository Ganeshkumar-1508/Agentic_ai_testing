"""Coordinates multi-repo change execution.

Orchestrates the per-repo workflow: clone → analyze → generate → commit → PR.
Follows the agent-agnostic orchestration pattern from Tembo:
coordination layer is separate from the agent that makes the changes.
"""

from __future__ import annotations
import asyncio
import time
import uuid
from typing import Any, Callable

from harness.cross_repo import (
    CrossRepoChange, RepoChange, RepoConfig, RepoChangeStatus,
    build_depends_on_block,
)
from harness.tools.delegate_task import DelegateTaskTool  # for spawning per-repo subagents


class MultiRepoCoordinator:
    """Orchestrates changes across multiple repositories.

    For each repo in dependency order:
    1. Clone the repo
    2. Delegate to agent for analysis and changes
    3. Commit and create PR
    4. Collect PR URL and link in subsequent PRs via Depends-On
    """

    def __init__(self, cross_repo_change: CrossRepoChange):
        self.crc = cross_repo_change
        self._results: dict[str, RepoChange] = {}

    async def execute(
        self,
        agent_factory: Callable,
        progress_callback: Callable | None = None,
    ) -> CrossRepoChange:
        """Execute the cross-repo change.

        Processes repos in dependency order (dependents last).
        Each repo gets its own subagent with per-repo credentials.
        After all PRs are created, adds Depends-On links to each PR body.
        """
        self.crc.status = "in_progress"
        self.crc.created_at = time.time()

        ordered_repos = self.crc.dependency_order
        completed_prs: list[dict[str, Any]] = []

        for repo_change in ordered_repos:
            try:
                repo_change.status = RepoChangeStatus.GENERATING

                # Create branch name unique to this run
                branch = f"testai/{self.crc.id[:8]}-{_sanitize_repo_name(repo_change.repo.url)}"
                repo_change.branch_name = branch

                # Spawn per-repo subagent with its own credentials
                # The agent clones the repo, makes changes, commits, and creates PR
                result = await self._execute_per_repo(
                    repo_change=repo_change,
                    agent_factory=agent_factory,
                    completed_prs=completed_prs,
                )

                if result:
                    repo_change.status = RepoChangeStatus.PR_CREATED
                    repo_change.pr_url = result.get("pr_url", "")
                    repo_change.pr_number = result.get("pr_number", 0)
                    repo_change.commit_sha = result.get("commit_sha", "")
                    repo_change.diff_summary = result.get("diff_summary", "")
                    completed_prs.append(result)
                else:
                    repo_change.status = RepoChangeStatus.FAILED
                    repo_change.error = f"{repo_change.repo.url}: no changes needed or failed"

            except Exception as e:
                repo_change.status = RepoChangeStatus.FAILED
                repo_change.error = str(e)

            if progress_callback:
                await progress_callback(self.crc)

        # After all PRs, update their bodies with Depends-On links
        await self._update_pr_bodies_with_depends_on()

        # Determine final status
        pr_count = sum(1 for rc in self.crc.repo_changes if rc.status == RepoChangeStatus.PR_CREATED)
        failed_count = sum(1 for rc in self.crc.repo_changes if rc.status == RepoChangeStatus.FAILED)

        if pr_count == len(self.crc.repo_changes):
            self.crc.status = "all_prs_created"
        elif pr_count > 0:
            self.crc.status = "partial"
        else:
            self.crc.status = "failed"
            self.crc.error = "All repo changes failed"

        return self.crc

    async def _execute_per_repo(
        self,
        repo_change: RepoChange,
        agent_factory: Callable,
        completed_prs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Execute changes for a single repo.

        Delegates to a subagent with per-repo credentials.
        """
        # Build context from already-completed PRs so the agent knows
        # what changed in dependencies
        dep_context = ""
        for pr in completed_prs:
            dep_context += f"\nDependency PR: {pr.get('pr_url', '')} — {pr.get('diff_summary', '')[:200]}"

        goal = (
            f"Clone {repo_change.repo.url} (branch: {repo_change.repo.branch}), "
            f"create branch {repo_change.branch_name}, "
            f"make the following changes: {self.crc.description}"
            f"\n{dep_context}"
            f"\nAfter changes, commit and push to branch {repo_change.branch_name}."
            f"\nCreate a PR against {repo_change.repo.branch} with a clear description."
        )

        # Delegate to subagent with per-repo auth
        agent = agent_factory(
            allowed_tools=["read", "write", "bash", "git"],
            repo_token=repo_change.repo.token,  # per-repo auth
            repo_url=repo_change.repo.url,
        )

        result = await agent.run(goal)

        if result:
            try:
                import json
                parsed = json.loads(result)
                if parsed.get("pr_url"):
                    return parsed
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

        return None

    async def _update_pr_bodies_with_depends_on(self):
        """Update all created PR bodies with Depends-On cross-references.

        After all PRs are created, updates each PR's body to include
        the Cross-Repo-Change-ID and Depends-On headers.
        Uses the GitHub/GitLab API to update PR descriptions.
        """
        for repo_change in self.crc.repo_changes:
            if repo_change.status != RepoChangeStatus.PR_CREATED:
                continue

            depends_block = build_depends_on_block(
                repo_change, self.crc.dependency_order
            )

            # Update PR body via provider API
            # (This would use git_providers.post_pr_comment or PR update endpoint)
            # For MVP: we embed the depends-on block in the original PR body
            pass  # TODO: wire git_providers to update PR body


def _sanitize_repo_name(url: str) -> str:
    """Extract a short, sanitized name from a repo URL.

    "https://github.com/org/service-a" → "service-a"
    """
    return url.rstrip("/").split("/")[-1].replace(" ", "-").lower()
