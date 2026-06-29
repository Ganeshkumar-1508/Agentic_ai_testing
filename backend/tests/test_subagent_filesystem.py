"""Tests for SubagentFilesystem (C6)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.services.subagent_filesystem import (
    MergeResult,
    SharedFilesystem,
    WorktreeFilesystem,
    filesystem_for_toolset,
    requires_isolation,
    subagent_worktree_branch,
    subagent_worktree_slug,
)


class TestNaming:
    def test_subagent_worktree_slug(self) -> None:
        assert subagent_worktree_slug("sa-abc") == "agent-sa-abc"

    def test_subagent_worktree_branch(self) -> None:
        branch = subagent_worktree_branch("sa-abc")
        assert branch == "testai/sa-abc"
        assert "/" in branch


class TestRequiresIsolation:
    def test_none_returns_false(self) -> None:
        assert requires_isolation(None) is False

    def test_empty_returns_false(self) -> None:
        assert requires_isolation([]) is False

    def test_read_only_tools_no_isolation(self) -> None:
        assert requires_isolation(["read", "intelligence"]) is False

    def test_write_tools_requires_isolation(self) -> None:
        assert requires_isolation(["read", "write", "intelligence"]) is True

    def test_edit_tool_requires_isolation(self) -> None:
        assert requires_isolation(["read", "edit"]) is True

    def test_apply_patch_requires_isolation(self) -> None:
        assert requires_isolation(["read", "apply_patch"]) is True

    def test_bash_requires_isolation(self) -> None:
        assert requires_isolation(["bash"]) is True


class TestFilesystemFactory:
    def test_read_only_returns_shared(self) -> None:
        fs = filesystem_for_toolset(["read", "intelligence"])
        assert isinstance(fs, SharedFilesystem)

    def test_write_returns_worktree(self) -> None:
        fs = filesystem_for_toolset(["read", "write"])
        assert isinstance(fs, WorktreeFilesystem)

    def test_default_is_shared(self) -> None:
        fs = filesystem_for_toolset()
        assert isinstance(fs, SharedFilesystem)


class TestSharedFilesystem:
    @pytest.mark.asyncio
    async def test_setup_returns_repo_path(self) -> None:
        fs = SharedFilesystem()
        path = await fs.setup("sa-abc", Path("/workspace/repo"), "main")
        assert path == Path("/workspace/repo")

    @pytest.mark.asyncio
    async def test_merge_back_always_succeeds(self) -> None:
        fs = SharedFilesystem()
        result = await fs.merge_back("sa-abc", Path("/workspace/repo"))
        assert result.success is True

    @pytest.mark.asyncio
    async def test_cleanup_does_nothing(self) -> None:
        fs = SharedFilesystem()
        await fs.cleanup("sa-abc", Path("/workspace/repo"))  # should not raise


class TestWorktreeFilesystem:
    @pytest.mark.asyncio
    async def test_setup_creates_worktree(self) -> None:
        fs = WorktreeFilesystem()
        fake_info = MagicMock()
        fake_info.path = Path("/workspace/.testai-worktrees/agent-sa-abc")

        with patch(
            "harness.services.worktree_manager.WorktreeManager.create_worktree",
            AsyncMock(return_value=fake_info),
        ):
            path = await fs.setup("sa-abc", Path("/workspace/repo"), "testai/session-xyz")
            assert path == fake_info.path

    @pytest.mark.asyncio
    async def test_merge_back_calls_git_merge(self) -> None:
        fs = WorktreeFilesystem()
        mock_mgr = MagicMock()
        mock_mgr._git_runner = AsyncMock(side_effect=[
            (0, "3", ""),  # _count_commits: 3 commits
            (0, "up-to-date", ""),  # git merge --ff-only
        ])
        fs._manager = mock_mgr

        result = await fs.merge_back("sa-abc", Path("/workspace/repo"))
        assert result.success is True
        assert result.n_commits == 3

    @pytest.mark.asyncio
    async def test_merge_back_conflict(self) -> None:
        fs = WorktreeFilesystem()
        mock_mgr = MagicMock()
        mock_mgr._git_runner = AsyncMock(side_effect=[
            (0, "3", ""),  # _count_commits
            (1, "", "conflict in file.txt"),  # merge
            (0, "file.txt\nother.py", ""),  # _detect_conflicts
        ])
        fs._manager = mock_mgr

        result = await fs.merge_back("sa-abc", Path("/workspace/repo"))
        assert result.success is False
        assert result.conflict_files == ["file.txt", "other.py"]

    @pytest.mark.asyncio
    async def test_cleanup_removes_worktree(self) -> None:
        fs = WorktreeFilesystem()
        mock_mgr = MagicMock()
        mock_mgr.remove_worktree = AsyncMock(return_value=True)
        fs._manager = mock_mgr

        await fs.cleanup("sa-abc", Path("/workspace/repo"))
        mock_mgr.remove_worktree.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_swallows_exception(self) -> None:
        fs = WorktreeFilesystem()
        mock_mgr = MagicMock()
        mock_mgr.remove_worktree = AsyncMock(side_effect=RuntimeError("boom"))
        fs._manager = mock_mgr

        await fs.cleanup("sa-abc", Path("/workspace/repo"))
        mock_mgr.remove_worktree.assert_awaited_once()
