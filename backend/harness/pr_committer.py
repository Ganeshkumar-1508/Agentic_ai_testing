"""Auto-commit generated tests to PR branches.

Three modes:
  - auto_commit=True: commit directly to the PR branch (GREPTILE-style)
  - auto_commit=False (default): create approval request, commit only after human approves
  - Phase 1 (Early.ai-style): generate behavior-freeze tests on base branch before change
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def commit_test_files(
    repo_url: str,
    branch: str,
    test_files: list[dict[str, str]],
    token: str | None = None,
    message: str = "testai: add generated tests",
    provider: str = "github",
) -> dict[str, Any]:
    """Clone repo, write test files, commit, and push.

    Args:
        repo_url: Remote repository URL.
        branch: Target branch to commit to.
        test_files: List of {path, content} dicts.
        token: Git access token. Falls back to env if None.
        message: Commit message.
        provider: 'github', 'gitlab', or 'bitbucket'.

    Returns:
        {success, commit_sha, branch, error}
    """
    token = token or os.environ.get("GIT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        return {"success": False, "error": "No git token available"}

    authed_url = _inject_token(repo_url, token, provider)
    tmp_dir = None

    try:
        tmp_dir = tempfile.mkdtemp(prefix="testai-commit-")
        repo_path = Path(tmp_dir) / "repo"

        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, authed_url, str(repo_path)],
            capture_output=True, text=True, timeout=120,
        )
        if not repo_path.exists():
            return {"success": False, "error": "Clone failed"}

        for tf in test_files:
            file_path = repo_path / tf["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(tf["content"], encoding="utf-8")

        subprocess.run(["git", "add", "-A"], cwd=repo_path, capture_output=True, timeout=30)
        result = subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty"],
            cwd=repo_path, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 and "nothing to commit" not in result.stderr:
            return {"success": False, "error": result.stderr.strip()}

        push = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=repo_path, capture_output=True, text=True, timeout=60,
        )
        if push.returncode != 0:
            return {"success": False, "error": push.stderr.strip()}

        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        return {"success": True, "commit_sha": sha.stdout.strip(), "branch": branch}

    except Exception as e:
        logger.warning("Commit to PR failed: %s", e)
        return {"success": False, "error": str(e)}
    finally:
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _inject_token(url: str, token: str, provider: str) -> str:
    """Insert token into git URL for authentication."""
    if provider == "github":
        return url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")
    if provider == "gitlab":
        return url.replace("https://gitlab.com/", f"https://oauth2:{token}@gitlab.com/")
    if provider == "bitbucket":
        return url.replace("https://bitbucket.org/", f"https://x-token-auth:{token}@bitbucket.org/")
    return url
