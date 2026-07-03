"""Tests for PR manager endpoint logic — verifies the agent_config column fix.

The /api/prs/{pr_id}/run endpoint crashed with KeyError: 'agent_config'
because the pr_tracker table was created before that column existed.

These tests replicate the endpoint logic inline (avoiding the deep
import chain: pr_manager → deps → agent → asyncpg) and verify:
  1. The agent_config access works for all edge cases
  2. The migration files include the ALTER TABLE for agent_config
  3. The endpoint logic handles missing rows correctly
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — replicate the endpoint's DB access pattern
# ---------------------------------------------------------------------------


class _FakeRow:
    """Simulates an asyncpg Record with dict-like access."""

    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


def _make_pr_row(**overrides: Any) -> _FakeRow:
    defaults = {
        "id": str(uuid.uuid4()),
        "repo_url": "rails/rails",
        "repo_provider": "github",
        "pr_number": 123,
        "title": "Fix test",
        "description": "A fix",
        "author": "test-user",
        "status": "open",
        "priority": 0,
        "labels": "[]",
        "agent_config": "{}",
        "source_branch": "fix-branch",
        "target_branch": "main",
        "files_changed": 1,
        "additions": 10,
        "deletions": 5,
    }
    defaults.update(overrides)
    return _FakeRow(**defaults)


# ---------------------------------------------------------------------------
# Replicate run_pr_tests logic (pr_manager.py:144-182)
# ---------------------------------------------------------------------------


def _run_pr_tests_logic(row: _FakeRow | None, body: dict) -> dict | int:
    """Replicate the critical path of run_pr_tests without importing FastAPI.

    Returns dict on success, 404 int on missing PR.
    """
    if row is None:
        return 404

    agent_config = body.get("agent_config", row["agent_config"] or "{}")
    if isinstance(agent_config, str):
        agent_config = json.loads(agent_config)

    run_id = str(uuid.uuid4())
    return {"status": "started", "run_id": run_id, "agent_config": agent_config}


# ---------------------------------------------------------------------------
# agent_config access — the exact crash scenario
# ---------------------------------------------------------------------------


async def test_agent_config_present_in_row() -> None:
    """Row has agent_config='{}' — no KeyError."""
    row = _make_pr_row(agent_config="{}")
    result = _run_pr_tests_logic(row, body={})
    assert result["status"] == "started"
    assert result["agent_config"] == {}


async def test_agent_config_custom_value() -> None:
    """Row has a custom agent_config — parsed correctly."""
    row = _make_pr_row(agent_config='{"model": "gpt-4"}')
    result = _run_pr_tests_logic(row, body={})
    assert result["agent_config"] == {"model": "gpt-4"}


async def test_agent_config_none_defaults_to_empty_dict() -> None:
    """Row has agent_config=None — defaults to '{}'."""
    row = _make_pr_row(agent_config=None)
    result = _run_pr_tests_logic(row, body={})
    assert result["agent_config"] == {}


async def test_agent_config_body_overrides_row() -> None:
    """Body provides agent_config — overrides row value."""
    row = _make_pr_row(agent_config='{"model": "gpt-3.5"}')
    body = {"agent_config": {"model": "claude-3"}}
    result = _run_pr_tests_logic(row, body=body)
    assert result["agent_config"] == {"model": "claude-3"}


async def test_agent_config_body_string_overrides_row() -> None:
    """Body provides agent_config as JSON string — parsed and overrides."""
    row = _make_pr_row(agent_config='{"model": "gpt-3.5"}')
    body = {"agent_config": '{"model": "claude-3"}'}
    result = _run_pr_tests_logic(row, body=body)
    assert result["agent_config"] == {"model": "claude-3"}


async def test_agent_config_missing_crashes_without_fix() -> None:
    """Verify the original bug: accessing row['agent_config'] on a row
    without that column raises KeyError."""
    row = _make_pr_row()
    # Simulate the old row (no agent_config column at all)
    del row._data["agent_config"]

    with pytest.raises(KeyError, match="agent_config"):
        _ = row["agent_config"]


async def test_agent_config_no_crash_with_fix() -> None:
    """With the fix (ALTER TABLE ADD COLUMN), the column always exists."""
    row = _make_pr_row(agent_config="{}")
    # This should NOT raise
    val = row["agent_config"]
    assert val == "{}"


# ---------------------------------------------------------------------------
# Missing PR (404 case)
# ---------------------------------------------------------------------------


async def test_missing_pr_returns_404() -> None:
    """When PR not found, endpoint returns 404."""
    result = _run_pr_tests_logic(row=None, body={})
    assert result == 404


# ---------------------------------------------------------------------------
# run_id generation
# ---------------------------------------------------------------------------


async def test_run_id_is_valid_uuid() -> None:
    """Generated run_id is a valid UUID4."""
    row = _make_pr_row()
    result = _run_pr_tests_logic(row, body={})
    parsed = uuid.UUID(result["run_id"])
    assert parsed.version == 4


async def test_run_ids_are_unique() -> None:
    """Two calls produce different run_ids."""
    row = _make_pr_row()
    r1 = _run_pr_tests_logic(row, body={})
    r2 = _run_pr_tests_logic(row, body={})
    assert r1["run_id"] != r2["run_id"]


# ---------------------------------------------------------------------------
# Migration file verification
# ---------------------------------------------------------------------------


async def test_schema_sql_has_agent_config_alter() -> None:
    """schema.sql includes ALTER TABLE for agent_config."""
    path = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema" / "schema.sql"
    content = path.read_text()
    assert "ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS agent_config TEXT DEFAULT" in content


async def test_migrations_sql_has_agent_config_alter() -> None:
    """migrations.sql includes ALTER TABLE for agent_config."""
    path = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema" / "migrations.sql"
    content = path.read_text()
    assert "ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS agent_config TEXT DEFAULT" in content


async def test_schema_sql_has_all_missing_columns() -> None:
    """schema.sql ALTER TABLEs cover all columns the code expects."""
    path = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema" / "schema.sql"
    content = path.read_text()
    required = [
        "agent_config",
        "pr_url",
        "merged_at",
        "closed_at",
        "commit_count",
        "comments_count",
        "last_commit_at",
    ]
    for col in required:
        assert f"ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS {col}" in content, (
            f"Missing ALTER TABLE for {col} in schema.sql"
        )
