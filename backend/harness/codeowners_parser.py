"""CODEOWNERS file parser — maps test file paths to owning teams.

Reads a .github/CODEOWNERS file and builds a pattern → team mapping.
Uses the rightmost-matching-pattern-wins semantics of GitHub CODEOWNERS.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Default patterns that match everything
FALLBACK_OWNER = "@core"


def parse_codeowners(content: str) -> list[tuple[str, str]]:
    """Parse a CODEOWNERS file into a list of (pattern, owner) tuples.

    Each entry: a glob pattern and one or more @usernames/@team handles.
    Comments (starting with #) and blank lines are ignored.
    Returns entries in file order — later entries override earlier ones.
    """
    entries: list[tuple[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        # Take the first owner/handle (multiple owners space-separated)
        owner = parts[1].lstrip("@")
        if owner:
            entries.append((pattern, owner))
    return entries


def match_owner(test_path: str, entries: list[tuple[str, str]]) -> str:
    """Find the owning team for a test path using rightmost-match semantics.

    Iterates entries in reverse (later patterns win) and returns the
    first match. Falls back to FALLBACK_OWNER if no pattern matches.
    """
    for pattern, owner in reversed(entries):
        # Normalize: patterns like `tests/` should match `tests/**`
        pat = pattern.rstrip("/") + "/**" if pattern.endswith("/") else pattern
        if fnmatch.fnmatch(test_path, pat):
            return owner
    return FALLBACK_OWNER


def extract_repo_name(repo_url: str) -> str:
    """Extract owner/repo from a GitHub URL."""
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", repo_url)
    return m.group(1) if m else repo_url


async def fetch_codeowners_via_api(repo_url: str, token: str = "") -> str | None:
    """Fetch CODEOWNERS from GitHub API. Returns raw content or None."""
    import httpx

    repo = extract_repo_name(repo_url)
    if not repo:
        return None

    candidates = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]
    headers = {"Accept": "application/vnd.github.raw+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=10) as client:
        for path in candidates:
            try:
                r = await client.get(
                    f"https://api.github.com/repos/{repo}/contents/{path}",
                    headers=headers,
                )
                if r.status_code == 200:
                    return r.text
            except Exception:
                continue
    return None


async def read_codeowners_from_workspace(workspace_path: str) -> str | None:
    """Read CODEOWNERS from a cloned repo workspace."""
    import os

    candidates = [
        os.path.join(workspace_path, ".github", "CODEOWNERS"),
        os.path.join(workspace_path, "CODEOWNERS"),
        os.path.join(workspace_path, "docs", "CODEOWNERS"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    return f.read()
            except Exception as e:
                logger.warning("Failed to read CODEOWNERS at %s: %s", path, e)
    return None


async def sync_test_owners(db: Any, repo_url: str, codeowners_content: str) -> int:
    """Parse CODEOWNERS and populate test_owners table.

    Returns number of entries inserted.
    We store the raw entries (pattern → team) rather than per-test mappings
    since tests aren't known in advance. The matching happens at query time.
    """
    entries = parse_codeowners(codeowners_content)
    if not entries:
        return 0

    # Clear existing entries for this repo and re-insert
    await db.execute(
        "DELETE FROM test_owners WHERE repo_url = $1", repo_url,
    )
    count = 0
    for pattern, owner in entries:
        await db.execute(
            "INSERT INTO test_owners (test_name, repo_url, team_name, pattern) "
            "VALUES ($1, $2, $3, $4)",
            f"pattern:{pattern}", repo_url, owner, pattern,
        )
        count += 1
    return count


async def get_owner_for_test(db: Any, test_name: str, repo_url: str) -> str:
    """Find the owning team for a test by matching against stored patterns."""
    rows = await db.fetch(
        "SELECT team_name, pattern FROM test_owners WHERE repo_url = $1 ORDER BY updated_at ASC",
        repo_url,
    )
    entries = [(r["pattern"], r["team_name"]) for r in rows]
    if not entries:
        return "core"
    return match_owner(test_name, entries)
