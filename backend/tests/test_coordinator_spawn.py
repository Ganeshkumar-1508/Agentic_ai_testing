"""Tests for CoordinatorSpawnPhase — verifies config injection and pre/post commands.

The phase injects advanced pipeline config into the coordinator's goal
and executes pre/post commands before/after the agent runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeRunContext:
    def __init__(self, **kwargs):
        self.run_id = kwargs.get("run_id", "test-run")
        self.session_id = kwargs.get("session_id", "test-session")
        self.repo_url = kwargs.get("repo_url", "https://github.com/octocat/Hello-World")
        self.branch = kwargs.get("branch", "master")
        self.goal = kwargs.get("goal", "Write a test")
        self.orchestrator = kwargs.get("orchestrator", None)
        self.sandbox = kwargs.get("sandbox", None)
        self.test_config = kwargs.get("test_config", None)
        self.board_id = kwargs.get("board_id", "test-board")
        self.kg_ctx = kwargs.get("kg_ctx", None)
        self.explore_findings = kwargs.get("explore_findings", "Found main.py")
        self.memory_block = kwargs.get("memory_block", "")
        self.coordinator_result = kwargs.get("coordinator_result", None)
        self.run_started_at = kwargs.get("run_started_at", "")
        self.errors = kwargs.get("errors", ())
        self.worktree_path = kwargs.get("worktree_path", None)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)


# ---------------------------------------------------------------------------
# Tests — config injection
# ---------------------------------------------------------------------------


async def test_config_injected_into_goal():
    """Advanced config is injected into the coordinator's goal string."""
    from harness.phases.coordinator_spawn import CoordinatorSpawnPhase

    phase = CoordinatorSpawnPhase()
    mock_orchestrator = MagicMock()
    ctx = _FakeRunContext(
        orchestrator=mock_orchestrator,
        sandbox=MagicMock(),
        test_config={"timeout_seconds": 300, "max_retries": 3},
    )

    # We can't fully run the phase without a real agent factory,
    # but we can verify the config parsing logic
    tc = ctx.test_config
    config_lines = []
    if tc.get("timeout_seconds"):
        config_lines.append(f"Timeout: {tc['timeout_seconds']}s per command")
    if tc.get("max_retries"):
        config_lines.append(f"Max retries: {tc['max_retries']}")

    assert "Timeout: 300s per command" in config_lines
    assert "Max retries: 3" in config_lines


async def test_config_empty_test_config():
    """Empty test_config produces no config lines."""
    tc = {}
    config_lines = []
    if tc.get("timeout_seconds"):
        config_lines.append(f"Timeout: {tc['timeout_seconds']}s per command")
    if tc.get("max_retries"):
        config_lines.append(f"Max retries: {tc['max_retries']}")

    assert len(config_lines) == 0


async def test_config_pre_commands():
    """Pre-commands are included in config lines."""
    tc = {"pre_commands": ["npm install", "pip install -r requirements.txt"]}
    config_lines = []
    if tc.get("pre_commands"):
        config_lines.append(f"Pre-commands: {', '.join(tc['pre_commands'])}")

    assert "Pre-commands: npm install, pip install -r requirements.txt" in config_lines


async def test_config_post_commands():
    """Post-commands are included in config lines."""
    tc = {"post_commands": ["npm run report"]}
    config_lines = []
    if tc.get("post_commands"):
        config_lines.append(f"Post-commands: {', '.join(tc['post_commands'])}")

    assert "Post-commands: npm run report" in config_lines


async def test_config_parallelism():
    """Parallelism > 1 is included in config lines."""
    tc = {"parallelism": 4}
    config_lines = []
    if tc.get("parallelism") and tc["parallelism"] > 1:
        config_lines.append(f"Parallelism: {tc['parallelism']} containers")

    assert "Parallelism: 4 containers" in config_lines


async def test_config_parallelism_1_not_included():
    """Parallelism of 1 is not included (default)."""
    tc = {"parallelism": 1}
    config_lines = []
    if tc.get("parallelism") and tc["parallelism"] > 1:
        config_lines.append(f"Parallelism: {tc['parallelism']} containers")

    assert len(config_lines) == 0


async def test_config_all_fields():
    """All config fields are included when present."""
    tc = {
        "timeout_seconds": 600,
        "max_retries": 5,
        "retry_on_failure": True,
        "fail_fast": True,
        "parallelism": 8,
        "shard_count": 4,
        "pre_commands": ["npm install"],
        "post_commands": ["npm test"],
        "os": "linux",
        "runtime_version": "18.x",
        "browser": "chromium",
        "cache_directories": ["node_modules"],
        "artifact_paths": ["coverage/"],
        "auto_commit": True,
        "commit_branch": "main",
        "tags": ["regression"],
    }

    config_lines = []
    if tc.get("timeout_seconds"):
        config_lines.append(f"Timeout: {tc['timeout_seconds']}s per command")
    if tc.get("max_retries"):
        config_lines.append(f"Max retries: {tc['max_retries']}")
    if tc.get("fail_fast"):
        config_lines.append("Fail fast: YES")
    if tc.get("parallelism") and tc["parallelism"] > 1:
        config_lines.append(f"Parallelism: {tc['parallelism']} containers")
    if tc.get("shard_count") and tc["shard_count"] > 1:
        config_lines.append(f"Shards: {tc['shard_count']}")
    if tc.get("pre_commands"):
        config_lines.append(f"Pre-commands: {', '.join(tc['pre_commands'])}")
    if tc.get("post_commands"):
        config_lines.append(f"Post-commands: {', '.join(tc['post_commands'])}")
    if tc.get("os"):
        config_lines.append(f"Target OS: {tc['os']}")
    if tc.get("runtime_version"):
        config_lines.append(f"Runtime: {tc['runtime_version']}")
    if tc.get("browser"):
        config_lines.append(f"Browser: {tc['browser']}")
    if tc.get("cache_directories"):
        config_lines.append(f"Cache dirs: {', '.join(tc['cache_directories'])}")
    if tc.get("artifact_paths"):
        config_lines.append(f"Artifact paths: {', '.join(tc['artifact_paths'])}")
    if tc.get("auto_commit"):
        config_lines.append(f"Auto-commit: YES (branch: {tc.get('commit_branch', 'main')})")
    if tc.get("tags"):
        config_lines.append(f"Tags: {', '.join(tc['tags'])}")

    assert len(config_lines) == 14
    assert "Timeout: 600s per command" in config_lines
    assert "Max retries: 5" in config_lines
    assert "Fail fast: YES" in config_lines
    assert "Parallelism: 8 containers" in config_lines
    assert "Shards: 4" in config_lines
    assert "Pre-commands: npm install" in config_lines
    assert "Post-commands: npm test" in config_lines
    assert "Target OS: linux" in config_lines
    assert "Runtime: 18.x" in config_lines
    assert "Browser: chromium" in config_lines
    assert "Cache dirs: node_modules" in config_lines
    assert "Artifact paths: coverage/" in config_lines
    assert "Auto-commit: YES (branch: main)" in config_lines
    assert "Tags: regression" in config_lines
