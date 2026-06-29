"""Tests for the ported GitHub service (OpenHands enterprise port)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.services.github_service import GitHubService
from harness.services.github_types import (
    Branch,
    OwnerType,
    PaginatedBranches,
    ProviderType,
    PullRequest,
    Repository,
)


class TestGitHubTypes:
    def test_repository_defaults(self) -> None:
        r = Repository(id="1", full_name="owner/repo", git_provider=ProviderType.GITHUB, is_public=True)
        assert r.stargazers_count is None
        assert r.main_branch is None

    def test_branch(self) -> None:
        b = Branch(name="main", commit_sha="abc123", protected=True)
        assert b.name == "main"

    def test_pull_request(self) -> None:
        pr = PullRequest(number=1, title="Fix", body="desc", state="open", head_sha="a", base_ref="main", head_ref="fix")
        assert pr.number == 1
        assert pr.merged is False


class TestGitHubService:
    @pytest.mark.asyncio
    async def test_list_repos_empty(self) -> None:
        gh = GitHubService(token="test-token")
        with patch.object(gh, "_request", AsyncMock(return_value=([], {}))):
            repos = await gh.list_repos()
            assert repos == []

    @pytest.mark.asyncio
    async def test_list_repos_parses_correctly(self) -> None:
        gh = GitHubService(token="test-token")
        fake_repos = [
            {
                "id": 123,
                "full_name": "owner/repo1",
                "private": False,
                "stargazers_count": 10,
                "pushed_at": "2026-06-01T00:00:00Z",
                "owner": {"type": "Organization"},
                "default_branch": "main",
            },
        ]
        with patch.object(gh, "_request", AsyncMock(return_value=(fake_repos, {}))):
            repos = await gh.list_repos()
            assert len(repos) == 1
            assert repos[0].full_name == "owner/repo1"
            assert repos[0].is_public is True
            assert repos[0].owner_type == OwnerType.ORGANIZATION
            assert repos[0].main_branch == "main"

    @pytest.mark.asyncio
    async def test_get_repo(self) -> None:
        gh = GitHubService(token="test-token")
        fake = {"id": 456, "full_name": "owner/repo", "private": True, "owner": {"type": "User"}}
        with patch.object(gh, "_request", AsyncMock(return_value=(fake, {}))):
            repo = await gh.get_repo("owner/repo")
            assert repo.full_name == "owner/repo"
            assert repo.is_public is False
            assert repo.owner_type == OwnerType.USER

    @pytest.mark.asyncio
    async def test_list_branches(self) -> None:
        gh = GitHubService(token="test-token")
        fake_branches = [
            {"name": "main", "commit": {"sha": "abc"}, "protected": True},
            {"name": "dev", "commit": {"sha": "def"}, "protected": False},
        ]
        with patch.object(gh, "_request", AsyncMock(return_value=(fake_branches, {}))):
            result = await gh.list_branches("owner/repo")
            assert isinstance(result, PaginatedBranches)
            assert len(result.branches) == 2
            assert result.branches[0].name == "main"
            assert result.has_next_page is False

    @pytest.mark.asyncio
    async def test_get_pr(self) -> None:
        gh = GitHubService(token="test-token")
        fake_pr = {
            "number": 42,
            "title": "Fix bug",
            "body": "The fix",
            "state": "open",
            "head": {"sha": "abc123", "ref": "fix-bug"},
            "base": {"ref": "main"},
            "user": {"login": "testuser"},
            "merged": False,
            "mergeable": True,
            "labels": [{"name": "bug"}],
        }
        with patch.object(gh, "_request", AsyncMock(return_value=(fake_pr, {}))):
            pr = await gh.get_pr("owner/repo", 42)
            assert pr.number == 42
            assert pr.title == "Fix bug"
            assert pr.author == "testuser"
            assert pr.labels == ["bug"]

    @pytest.mark.asyncio
    async def test_verify_token_valid(self) -> None:
        gh = GitHubService(token="valid-token")
        with patch.object(gh, "_request", AsyncMock(return_value=({"login": "user"}, {}))):
            assert await gh.verify_token() is True

    @pytest.mark.asyncio
    async def test_verify_token_invalid(self) -> None:
        gh = GitHubService(token="bad-token")
        with patch.object(gh, "_request", AsyncMock(side_effect=RuntimeError("401"))):
            assert await gh.verify_token() is False

    @pytest.mark.asyncio
    async def test_get_user(self) -> None:
        gh = GitHubService(token="test-token")
        fake_user = {"login": "testuser", "id": 123, "name": "Test User"}
        with patch.object(gh, "_request", AsyncMock(return_value=(fake_user, {}))):
            user = await gh.get_user()
            assert user["login"] == "testuser"

    @pytest.mark.asyncio
    async def test_search_repos(self) -> None:
        gh = GitHubService(token="test-token")
        fake = {"items": [{"id": 1, "full_name": "owner/repo", "private": False, "owner": {"type": "User"}}]}
        with patch.object(gh, "_request", AsyncMock(return_value=(fake, {}))):
            repos = await gh.search_repos("test")
            assert len(repos) == 1

    @pytest.mark.asyncio
    async def test_get_pr_patches(self) -> None:
        gh = GitHubService(token="test-token")
        fake_files = [{"filename": "src/main.py", "status": "modified", "additions": 5, "deletions": 2}]
        with patch.object(gh, "_request", AsyncMock(return_value=(fake_files, {}))):
            patches = await gh.get_pr_patches("owner/repo", 42)
            assert len(patches) == 1
            assert patches[0]["filename"] == "src/main.py"

    @pytest.mark.asyncio
    async def test_get_file_content(self) -> None:
        import base64
        gh = GitHubService(token="test-token")
        content = base64.b64encode(b"hello world").decode()
        fake = {"content": content, "encoding": "base64"}
        with patch.object(gh, "_request", AsyncMock(return_value=(fake, {}))):
            result = await gh.get_file_content("owner/repo", "README.md")
            assert result == "hello world"

    @pytest.mark.asyncio
    async def test_get_file_content_not_found(self) -> None:
        gh = GitHubService(token="test-token")
        with patch.object(gh, "_request", AsyncMock(side_effect=RuntimeError("404"))):
            result = await gh.get_file_content("owner/repo", "nonexistent.py")
            assert result is None


