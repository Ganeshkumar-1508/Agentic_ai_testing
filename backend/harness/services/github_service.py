"""GitHub API service — ported from OpenHands enterprise integration.

Adapted from OpenHands' ``GitHubService`` mixin architecture to
our PAT-based token model (tokens stored in ``integration_configs``
table instead of GitHub App installation auth).

Key differences from OpenHands:
  - Token resolution via ``_get_token()`` from env vars or DB
  - No GitHub App installation flow (we use PATs)
  - No PyGithub (pure httpx)
  - Simpler: single class instead of 6 mixins
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from harness.services.github_types import (
    Branch,
    OwnerType,
    PaginatedBranches,
    ProviderType,
    PullRequest,
    Repository,
)

logger = logging.getLogger(__name__)


async def _resolve_token(platform: str = "github") -> str:
    """Resolve token from env vars or integration_configs DB table."""
    if platform == "gitlab":
        import os
        token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN", "")
        if token:
            return token
    else:
        import os
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
        if token:
            return token
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db:
            row = await db.fetchrow(
                "SELECT config FROM integration_configs "
                "WHERE platform = $1 AND enabled = true LIMIT 1",
                platform,
            )
            if row:
                config = row["config"]
                if isinstance(config, str):
                    config = json.loads(config)
                return config.get("token", "")
    except Exception as exc:
        logger.debug("token resolve failed: %s", exc)
    return ""


class GitHubService:
    """GitHub API client.

    Usage::

        gh = GitHubService(token="ghp_...")
        repos = await gh.list_repos()
        pr = await gh.get_pr("owner/repo", 42)
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str = "") -> None:
        self._token = token

    async def _ensure_token(self) -> str:
        if not self._token:
            self._token = await _resolve_token("github")
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "testai",
        }

    async def _request(
        self,
        path: str,
        params: dict | None = None,
        method: str = "GET",
        json_body: dict | None = None,
    ) -> tuple[Any, dict]:
        url = f"{self.BASE_URL}{path}" if path.startswith("/") else path
        headers = await self._headers()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url, headers=headers, params=params, json=json_body,
                )
                if resp.status_code == 401 and self._token:
                    self._token = ""
                    headers = await self._headers()
                    resp = await client.request(
                        method, url, headers=headers, params=params, json=json_body,
                    )
                resp.raise_for_status()
                extra: dict = {}
                if "Link" in resp.headers:
                    extra["Link"] = resp.headers["Link"]
                return resp.json(), extra
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"GitHub API error: {e.response.status_code} {e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"GitHub request failed: {e}") from e

    # ── Auth / User ─────────────────────────────────────────────────

    async def verify_token(self) -> bool:
        try:
            await self._request("/")
            return True
        except RuntimeError:
            return False

    async def get_user(self) -> dict[str, Any]:
        data, _ = await self._request("/user")
        return data

    # ── Repositories ────────────────────────────────────────────────

    async def list_repos(
        self, sort: str = "pushed", max_repos: int = 200,
    ) -> list[Repository]:
        repos: list[dict] = []
        page = 1
        per_page = 100
        while len(repos) < max_repos:
            data, headers = await self._request(
                "/user/repos",
                params={"page": page, "per_page": per_page, "sort": sort},
            )
            if not data:
                break
            repos.extend(data)
            link = headers.get("Link", "")
            if 'rel="next"' not in link:
                break
            page += 1
        return [self._parse_repo(r) for r in repos[:max_repos]]

    async def get_repo(self, full_name: str) -> Repository:
        data, _ = await self._request(f"/repos/{full_name}")
        return self._parse_repo(data)

    async def search_repos(
        self, query: str, per_page: int = 20,
    ) -> list[Repository]:
        data, _ = await self._request(
            "/search/repositories",
            params={"q": f"{query} in:name", "per_page": per_page},
        )
        return [self._parse_repo(r) for r in data.get("items", [])]

    @staticmethod
    def _parse_repo(repo: dict) -> Repository:
        return Repository(
            id=str(repo.get("id", "")),
            full_name=repo.get("full_name", ""),
            git_provider=ProviderType.GITHUB,
            is_public=not repo.get("private", True),
            stargazers_count=repo.get("stargazers_count"),
            pushed_at=repo.get("pushed_at"),
            owner_type=(
                OwnerType.ORGANIZATION
                if repo.get("owner", {}).get("type") == "Organization"
                else OwnerType.USER
            ),
            main_branch=repo.get("default_branch"),
        )

    # ── Branches ────────────────────────────────────────────────────

    async def list_branches(
        self, full_name: str, page: int = 1, per_page: int = 30,
    ) -> PaginatedBranches:
        data, headers = await self._request(
            f"/repos/{full_name}/branches",
            params={"page": page, "per_page": per_page},
        )
        link = headers.get("Link", "")
        return PaginatedBranches(
            branches=[self._parse_branch(b) for b in data],
            has_next_page='rel="next"' in link,
            current_page=page,
            per_page=per_page,
        )

    @staticmethod
    def _parse_branch(b: dict) -> Branch:
        return Branch(
            name=b.get("name", ""),
            commit_sha=b.get("commit", {}).get("sha", ""),
            protected=b.get("protected", False),
        )

    # ── Pull Requests ───────────────────────────────────────────────

    async def list_prs(
        self, full_name: str, state: str = "open", limit: int = 20,
    ) -> list[PullRequest]:
        data, _ = await self._request(
            f"/repos/{full_name}/pulls",
            params={"state": state, "per_page": min(limit, 100)},
        )
        return [self._parse_pr(pr, full_name) for pr in data[:limit]]

    async def get_pr(self, full_name: str, pr_number: int) -> PullRequest:
        data, _ = await self._request(f"/repos/{full_name}/pulls/{pr_number}")
        return self._parse_pr(data, full_name)

    async def get_pr_patches(
        self, full_name: str, pr_number: int,
    ) -> list[dict]:
        data, _ = await self._request(
            f"/repos/{full_name}/pulls/{pr_number}/files",
            params={"per_page": 100},
        )
        return data

    async def create_pr(
        self, full_name: str, title: str, body: str,
        head: str, base: str,
    ) -> PullRequest:
        payload = {"title": title, "body": body, "head": head, "base": base}
        data, _ = await self._request(
            f"/repos/{full_name}/pulls",
            json_body=payload, method="POST",
        )
        return self._parse_pr(data, full_name)

    async def create_pr_comment(
        self, full_name: str, pr_number: int, body: str,
    ) -> dict:
        data, _ = await self._request(
            f"/repos/{full_name}/issues/{pr_number}/comments",
            json_body={"body": body}, method="POST",
        )
        return data

    def _parse_pr(self, pr: dict, full_name: str = "") -> PullRequest:
        return PullRequest(
            number=pr.get("number", 0),
            title=pr.get("title", ""),
            body=pr.get("body", "") or "",
            state=pr.get("state", "open"),
            head_sha=pr.get("head", {}).get("sha", ""),
            base_ref=pr.get("base", {}).get("ref", ""),
            head_ref=pr.get("head", {}).get("ref", ""),
            author=pr.get("user", {}).get("login"),
            merged=pr.get("merged", False),
            mergeable=pr.get("mergeable"),
            labels=[lab["name"] for lab in pr.get("labels", [])],
        )

    # ── Contents (for file reading) ──────────────────────────────────

    async def get_file_content(
        self, full_name: str, path: str, ref: str = "",
    ) -> str | None:
        params = {}
        if ref:
            params["ref"] = ref
        try:
            data, _ = await self._request(
                f"/repos/{full_name}/contents/{path}", params=params,
            )
            content = data.get("content", "")
            if content:
                import base64
                return base64.b64decode(content).decode("utf-8", errors="replace")
        except RuntimeError:
            return None
        return None
