"""GitHub/GitLab integration tools for issues, PRs, diffs, CI, comments, and labels.

All tools use the same token resolution pattern:
  1. GITHUB_TOKEN / GH_TOKEN env var (or GITLAB_TOKEN for GitLab)
  2. integration_configs DB table
  3. Falls back to no-token error

Provider detection is automatic based on the repo URL or platform config.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


async def _get_token(platform: str = "github") -> str:
    """Resolve token from env vars or DB."""
    if platform == "gitlab":
        token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN")
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db:
            row = await db.fetchrow(
                "SELECT config FROM integration_configs WHERE platform = $1 AND enabled = true LIMIT 1",
                platform,
            )
            if row:
                config = row["config"]
                if isinstance(config, str):
                    config = json.loads(config)
                return config.get("token", "")
    except Exception as e:
        logger.warning("Failed to fetch %s token from DB: %s", platform, e)
    return ""


async def _get_provider(token: str, platform: str = ""):
    """Auto-detect provider from token or platform hint."""
    from harness.ci.git_providers import get_provider
    if platform:
        return get_provider(platform)
    if os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN"):
        return get_provider("gitlab")
    return get_provider("github")


class GitHubListIssuesTool(BaseTool):
    """List open GitHub issues for a repository."""

    name = "github_list_issues"
    description = (
        "List open GitHub issues for a repository. Returns issue numbers, titles, "
        "labels, and other metadata. Useful for triaging work and creating kanban tasks."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in format 'owner/repo' (e.g., 'rails/rails')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of issues to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["repo"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        limit = kwargs.get("limit", 20)
        if not repo:
            return ToolResult(success=False, output="repo is required", error="missing_repo")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="GitHub token not configured. Set GITHUB_TOKEN or configure in integration_configs.", error="no_token")

        try:
            provider = await _get_provider(token)
            issues = await provider.list_open_issues(repo, token)
            issues = issues[:limit]
            if not issues:
                return ToolResult(success=True, output=f"No open issues found in {repo}")

            lines = [f"Found {len(issues)} open issues in {repo}:\n"]
            for issue in issues:
                labels = ", ".join(issue.get("labels", [])) or "none"
                lines.append(
                    f"#{issue['number']}: {issue['title']}\n"
                    f"  Labels: {labels}\n"
                    f"  Author: {issue.get('user', 'unknown')}\n"
                    f"  Created: {issue.get('created_at', 'unknown')}\n"
                )
            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            logger.error("Failed to list issues: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to list issues: {e}", error="api_error")


class GitHubListPRsTool(BaseTool):
    """List open GitHub pull requests for a repository."""

    name = "github_list_prs"
    description = (
        "List open GitHub pull requests for a repository. Returns PR numbers, titles, "
        "branches, and other metadata. Useful for tracking active work and reviews."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in format 'owner/repo' (e.g., 'rails/rails')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of PRs to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["repo"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        limit = kwargs.get("limit", 20)
        if not repo:
            return ToolResult(success=False, output="repo is required", error="missing_repo")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="GitHub token not configured. Set GITHUB_TOKEN or configure in integration_configs.", error="no_token")

        try:
            provider = await _get_provider(token)
            prs = await provider.list_open_prs(repo, token)
            prs = prs[:limit]
            if not prs:
                return ToolResult(success=True, output=f"No open PRs found in {repo}")

            lines = [f"Found {len(prs)} open PRs in {repo}:\n"]
            for pr in prs:
                labels = ", ".join(pr.get("labels", [])) or "none"
                draft = " [DRAFT]" if pr.get("draft") else ""
                lines.append(
                    f"#{pr['number']}: {pr['title']}{draft}\n"
                    f"  Branch: {pr.get('source_branch', '?')} -> {pr.get('target_branch', '?')}\n"
                    f"  Labels: {labels}\n"
                    f"  Author: {pr.get('user', 'unknown')}\n"
                    f"  Changes: +{pr.get('additions', 0)}/-{pr.get('deletions', 0)} in {pr.get('changed_files', 0)} files\n"
                    f"  SHA: {pr.get('head_sha', 'unknown')[:8]}\n"
                )
            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            logger.error("Failed to list PRs: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to list PRs: {e}", error="api_error")


class GitHubGetPRDetailTool(BaseTool):
    """Get full details of a GitHub pull request."""

    name = "github_get_pr_detail"
    description = (
        "Get full details of a specific pull request including title, description, "
        "branch info, merge status, labels, reviewers, and change stats."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in format 'owner/repo'"},
                    "pr_number": {"type": "integer", "description": "PR number"},
                },
                "required": ["repo", "pr_number"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        pr_number = kwargs.get("pr_number")
        if not repo or pr_number is None:
            return ToolResult(success=False, output="repo and pr_number are required", error="missing_args")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="Token not configured", error="no_token")

        try:
            provider = await _get_provider(token)
            detail = await provider.get_pr_detail(repo, int(pr_number), token)
            return ToolResult(success=True, output=json.dumps(detail, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to get PR detail: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to get PR detail: {e}", error="api_error")


class GitHubGetPRFilesTool(BaseTool):
    """List files changed in a GitHub pull request."""

    name = "github_get_pr_files"
    description = (
        "List files changed in a specific pull request with additions, deletions, "
        "and the diff patch for each file. Useful for understanding what a PR modifies."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in format 'owner/repo'"},
                    "pr_number": {"type": "integer", "description": "PR number"},
                },
                "required": ["repo", "pr_number"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        pr_number = kwargs.get("pr_number")
        if not repo or pr_number is None:
            return ToolResult(success=False, output="repo and pr_number are required", error="missing_args")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="Token not configured", error="no_token")

        try:
            provider = await _get_provider(token)
            files = await provider.get_pr_files(repo, int(pr_number), token)
            if not files:
                return ToolResult(success=True, output=f"No files found in PR #{pr_number}")

            lines = [f"PR #{pr_number} — {len(files)} files changed:\n"]
            for f in files:
                status_icon = {"added": "+", "deleted": "-", "modified": "~"}.get(f["status"], "?")
                lines.append(
                    f"  {status_icon} {f['filename']} "
                    f"(+{f['additions']}/-{f['deletions']}, {f['changes']} changes)\n"
                )
                if f.get("patch"):
                    lines.append(f"    Patch:\n{f['patch'][:500]}\n")
            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            logger.error("Failed to get PR files: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to get PR files: {e}", error="api_error")


class GitHubGetCIChecksTool(BaseTool):
    """Get CI/CD check status for a commit."""

    name = "github_get_ci_checks"
    description = (
        "Get CI/CD check run status for a specific commit ref (SHA or branch). "
        "Returns status (queued/in_progress/completed) and conclusion (success/failure/neutral) "
        "for each check. Useful for verifying if CI passes before merging."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in format 'owner/repo'"},
                    "ref": {"type": "string", "description": "Git ref — commit SHA, branch name, or tag"},
                },
                "required": ["repo", "ref"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        ref = kwargs.get("ref", "")
        if not repo or not ref:
            return ToolResult(success=False, output="repo and ref are required", error="missing_args")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="Token not configured", error="no_token")

        try:
            provider = await _get_provider(token)
            checks = await provider.get_ci_checks(repo, ref, token)
            if not checks:
                return ToolResult(success=True, output=f"No CI checks found for ref {ref[:12]}")

            lines = [f"CI checks for {ref[:12]} — {len(checks)} found:\n"]
            for c in checks:
                icon = {"success": "✅", "failure": "❌", "queued": "⏳", "in_progress": "🔄", "completed": "✅"}.get(c["conclusion"] or c["status"], "❓")
                lines.append(
                    f"  {icon} {c['name']} — {c['status']}"
                    + (f" ({c['conclusion']})" if c.get("conclusion") else "")
                    + "\n"
                )
                if c.get("output_title"):
                    lines.append(f"    {c['output_title']}\n")
            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            logger.error("Failed to get CI checks: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to get CI checks: {e}", error="api_error")


class GitHubPostCommentTool(BaseTool):
    """Post a comment on a GitHub issue or PR."""

    name = "github_post_comment"
    description = (
        "Post a comment on a GitHub issue or pull request. "
        "Works for both issues and PRs (PRs use the issues API internally)."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in format 'owner/repo'"},
                    "issue_number": {"type": "integer", "description": "Issue or PR number"},
                    "body": {"type": "string", "description": "Comment body (markdown supported)"},
                },
                "required": ["repo", "issue_number", "body"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        issue_number = kwargs.get("issue_number")
        body = kwargs.get("body", "")
        if not repo or issue_number is None or not body:
            return ToolResult(success=False, output="repo, issue_number, and body are required", error="missing_args")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="Token not configured", error="no_token")

        try:
            provider = await _get_provider(token)
            await provider.post_pr_comment(repo, int(issue_number), token, body)
            return ToolResult(success=True, output=f"Comment posted on {repo}#{issue_number}")
        except Exception as e:
            logger.error("Failed to post comment: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to post comment: {e}", error="api_error")


class GitHubAddLabelsTool(BaseTool):
    """Add labels to a GitHub issue or PR."""

    name = "github_add_labels"
    description = (
        "Add one or more labels to a GitHub issue or pull request. "
        "Labels must already exist in the repository."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in format 'owner/repo'"},
                    "issue_number": {"type": "integer", "description": "Issue or PR number"},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "List of label names to add"},
                },
                "required": ["repo", "issue_number", "labels"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        issue_number = kwargs.get("issue_number")
        labels = kwargs.get("labels", [])
        if not repo or issue_number is None or not labels:
            return ToolResult(success=False, output="repo, issue_number, and labels are required", error="missing_args")

        token = await _get_token()
        if not token:
            return ToolResult(success=False, output="Token not configured", error="no_token")

        try:
            provider = await _get_provider(token)
            await provider.add_labels(repo, int(issue_number), token, labels)
            return ToolResult(success=True, output=f"Labels {labels} added to {repo}#{issue_number}")
        except Exception as e:
            logger.error("Failed to add labels: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to add labels: {e}", error="api_error")


# Register tools at module level so discover_tools picks them up
from harness.tools.registry import registry

registry.register(GitHubListIssuesTool(), toolset="read")
registry.register(GitHubListPRsTool(), toolset="read")
registry.register(GitHubGetPRDetailTool(), toolset="read")
registry.register(GitHubGetPRFilesTool(), toolset="read")
registry.register(GitHubGetCIChecksTool(), toolset="read")
registry.register(GitHubPostCommentTool(), toolset="read")
registry.register(GitHubAddLabelsTool(), toolset="read")
