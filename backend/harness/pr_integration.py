"""PR Integration — auto-post test results, coverage, and quality data to GitHub PRs.

Triggers on GitHub webhook events (pull_request.opened, pull_request.synchronize).
Runs tests, analyzes results, posts a summary comment on the PR.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_pr_comment(
    test_summary: dict | None = None,
    coverage: dict | None = None,
    quality_score: dict | None = None,
    flaky: dict | None = None,
    rca: dict | None = None,
) -> str:
    """Build a formatted PR comment with test results, coverage, and quality data."""
    lines = ["## TestAI Quality Report\n"]

    # Overall quality score
    if quality_score:
        score = quality_score.get("score", 0)
        verdict = quality_score.get("verdict", "unknown")
        emoji = {"go": "✅", "caution": "⚠️", "no-go": "❌"}.get(verdict, "❓")
        lines.append(f"### {emoji} Quality Score: **{score}/100** ({verdict})\n")

    # Test results
    if test_summary:
        total = test_summary.get("total", 0)
        passed = test_summary.get("passed", 0)
        failed = test_summary.get("failed", 0)
        pass_rate = test_summary.get("pass_rate", 0)
        lines.append(f"### Tests: {passed}/{total} passed ({pass_rate}%)\n")
        if failed > 0:
            lines.append(f"<details><summary>❌ {failed} failed test(s)</summary>\n\n")
            lines.append(f"| Test | Status |\n|---|---|\n")
            for f in test_summary.get("failures", []):
                lines.append(f"| {f.get('test_name', '?')} | ❌ |\n")
            lines.append("</details>\n")

    # Coverage
    if coverage and coverage.get("coverage"):
        cov = coverage["coverage"]
        line_cov = cov.get("line_coverage", 0)
        lines.append(f"\n### Coverage: **{line_cov}%**\n")
        gaps = coverage.get("gaps", [])
        if gaps:
            lines.append(f"<details><summary>📉 {len(gaps)} coverage gap(s)</summary>\n\n")
            for g in gaps[:10]:
                lines.append(f"- `{g['path']}`: {g['percent']}%\n")
            lines.append("</details>\n")

    # Flaky tests
    if flaky:
        q = flaky.get("quarantined", 0)
        if q > 0:
            lines.append(f"\n### 🔄 {q} flaky test(s) quarantined\n")

    # RCA summary
    if rca:
        defects = rca.get("defect_count", 0)
        flakes = rca.get("flake_count", 0)
        if defects > 0 or flakes > 0:
            lines.append(f"\n### Root Cause Analysis: {defects} defects, {flakes} flakes\n")

    lines.append("\n---\n*Reported by TestAI*")
    return "\n".join(lines)


async def post_pr_comment(
    repo_url: str,
    pr_number: int,
    comment: str,
    github_token: str,
) -> dict[str, Any]:
    """Post a comment on a GitHub PR using the GitHub API."""
    import httpx
    from urllib.parse import urlparse

    # Extract owner/repo from URL
    parsed = urlparse(repo_url)
    path_parts = parsed.path.strip("/").replace(".git", "").split("/")
    if len(path_parts) < 2:
        return {"error": f"Invalid repo URL: {repo_url}"}
    owner, repo = path_parts[0], path_parts[1]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"body": comment},
            )
            if resp.status_code in (200, 201):
                return {"status": "posted", "url": resp.json().get("html_url", "")}
            return {"error": f"GitHub API returned {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


async def update_pr_commit_status(
    repo_url: str,
    commit_sha: str,
    state: str,
    description: str,
    github_token: str,
    target_url: str = "",
) -> dict[str, Any]:
    """Update the commit status on a GitHub PR."""
    import httpx
    from urllib.parse import urlparse

    parsed = urlparse(repo_url)
    path_parts = parsed.path.strip("/").replace(".git", "").split("/")
    if len(path_parts) < 2:
        return {"error": f"Invalid repo URL: {repo_url}"}
    owner, repo = path_parts[0], path_parts[1]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/statuses/{commit_sha}"

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "state": state,
                    "description": description,
                    "context": "TestAI Quality Check",
                    "target_url": target_url,
                },
            )
            return {"status": "updated" if resp.status_code in (200, 201) else "failed"}
    except Exception as e:
        return {"error": str(e)}
