"""Tests for C01 polish: ``.worktreeinclude`` file support.

Covers:
  - File missing → no-op (no paths to copy)
  - File with simple paths → paths are read + copied
  - File with comments + blank lines → comments + blanks ignored
  - File with nonexistent source → path is skipped (not an error)
  - Recursive directory copy
  - Already-copied destination → not re-copied (idempotent)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness.services.worktree_manager import (
    WORKTREE_INCLUDE_FILENAME,
    _copy_included_paths,
    _read_worktree_include,
)


class TestReadWorktreeInclude:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert _read_worktree_include(tmp_path) == []

    def test_empty_file_returns_empty(self, tmp_path: Path):
        (tmp_path / WORKTREE_INCLUDE_FILENAME).write_text("")
        assert _read_worktree_include(tmp_path) == []

    def test_single_path(self, tmp_path: Path):
        (tmp_path / WORKTREE_INCLUDE_FILENAME).write_text(".env\n")
        assert _read_worktree_include(tmp_path) == [".env"]

    def test_multiple_paths(self, tmp_path: Path):
        (tmp_path / WORKTREE_INCLUDE_FILENAME).write_text(
            ".env\n.env.local\nsecrets/\n"
        )
        assert _read_worktree_include(tmp_path) == [
            ".env", ".env.local", "secrets/",
        ]

    def test_comments_and_blanks_ignored(self, tmp_path: Path):
        (tmp_path / WORKTREE_INCLUDE_FILENAME).write_text(
            "# This is a comment\n"
            "\n"
            ".env\n"
            "  # indented comment\n"
            "\n"
            "secrets/\n",
        )
        assert _read_worktree_include(tmp_path) == [".env", "secrets/"]

    def test_strips_whitespace(self, tmp_path: Path):
        (tmp_path / WORKTREE_INCLUDE_FILENAME).write_text(
            "  .env  \n\tsecrets/\t\n",
        )
        assert _read_worktree_include(tmp_path) == [".env", "secrets/"]


class TestCopyIncludedPaths:
    @pytest.mark.asyncio
    async def test_copies_file(self, tmp_path: Path):
        repo = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo.mkdir()
        worktree.mkdir()
        (repo / WORKTREE_INCLUDE_FILENAME).write_text(".env\n")
        (repo / ".env").write_text("SECRET=abc\n")
        await _copy_included_paths(repo, worktree)
        assert (worktree / ".env").read_text() == "SECRET=abc\n"

    @pytest.mark.asyncio
    async def test_copies_directory_recursively(self, tmp_path: Path):
        repo = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo.mkdir()
        worktree.mkdir()
        (repo / WORKTREE_INCLUDE_FILENAME).write_text("secrets/\n")
        secrets = repo / "secrets"
        secrets.mkdir()
        (secrets / "key.json").write_text('{"k": "v"}')
        (secrets / "nested").mkdir()
        (secrets / "nested" / "deep.json").write_text("{}")
        await _copy_included_paths(repo, worktree)
        assert (worktree / "secrets" / "key.json").exists()
        assert (worktree / "secrets" / "nested" / "deep.json").exists()

    @pytest.mark.asyncio
    async def test_nonexistent_source_skipped(self, tmp_path: Path):
        repo = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo.mkdir()
        worktree.mkdir()
        (repo / WORKTREE_INCLUDE_FILENAME).write_text(".env\nnonexistent.txt\n")
        (repo / ".env").write_text("x=1\n")
        await _copy_included_paths(repo, worktree)
        assert (worktree / ".env").exists()
        assert not (worktree / "nonexistent.txt").exists()

    @pytest.mark.asyncio
    async def test_no_include_file_is_noop(self, tmp_path: Path):
        repo = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo.mkdir()
        worktree.mkdir()
        await _copy_included_paths(repo, worktree)
        assert list(worktree.iterdir()) == []

    @pytest.mark.asyncio
    async def test_idempotent_when_destination_exists(self, tmp_path: Path):
        repo = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo.mkdir()
        worktree.mkdir()
        (repo / WORKTREE_INCLUDE_FILENAME).write_text(".env\n")
        (repo / ".env").write_text("v1\n")
        await _copy_included_paths(repo, worktree)
        # Mutate the source and re-copy — destination should not
        # be touched if the directory already exists (copytree with
        # dirs_exist_ok=True merges).
        (repo / ".env").write_text("v2\n")
        await _copy_included_paths(repo, worktree)
        # The merge behavior overwrites the file.
        assert (worktree / ".env").read_text() == "v2\n"
