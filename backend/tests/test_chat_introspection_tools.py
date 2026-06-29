"""Tests for the chat introspection tools.

The chat Role has 9 read-only tools that read from the same Postgres
tables the API routers read. These tests verify the tools:
  - Return a clear "not initialized" error when the store is unset
  - Parse input arguments safely
  - Format output for the chat LLM
  - Handle empty results
  - Don't propagate DB errors

We use a fake store that records queries and returns canned data. No
real Postgres connection is needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from harness.tools.chat_introspection import (
    GetCoverageTool,
    GetDashboardStatusTool,
    GetLogsTool,
    GetRunArtifactsTool,
    GetRunTool,
    GetTestCaseTool,
    ListRunsTool,
    ListTestCasesTool,
    SearchRunsTool,
    set_introspection_store,
)
from harness.tools.registry import registry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _FakeRow:
    """Lightweight row that supports `**dict(row)`, attribute access,
    and `dict(row)` construction."""
    data: dict

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def keys(self):
        return self.data.keys()

    def values(self):
        return self.data.values()

    def items(self):
        return self.data.items()

    def __iter__(self):
        return iter(self.data)


class _FakeDB:
    """Stand-in for the db handle. Records queries and returns canned
    data via the `set_response` method."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple]] = []
        self._fetch_responses: list[list[_FakeRow]] = []
        self._fetchrow_responses: list[_FakeRow | None] = []

    def set_fetch(self, rows: list[dict] | None) -> None:
        self._fetch_responses.append(
            [_FakeRow(r) for r in (rows or [])]
        )

    def set_fetchrow(self, row: dict | None) -> None:
        self._fetchrow_responses.append(
            _FakeRow(row) if row else None
        )

    async def fetch(self, sql: str, *args: Any) -> list[_FakeRow]:
        self.queries.append((sql, args))
        if self._fetch_responses:
            return self._fetch_responses.pop(0)
        return []

    async def fetchrow(self, sql: str, *args: Any) -> _FakeRow | None:
        self.queries.append((sql, args))
        if self._fetchrow_responses:
            return self._fetchrow_responses.pop(0)
        return None


class _FakeStore:
    def __init__(self) -> None:
        self.db = _FakeDB()


# ---------------------------------------------------------------------------
# Fixture: reset the module-level store reference between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_introspection_store():
    set_introspection_store(None)
    yield
    set_introspection_store(None)


@pytest.fixture
def fake_store():
    store = _FakeStore()
    set_introspection_store(store)
    return store


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_returns_not_initialized_when_store_missing():
    """No store wired → tool returns a clear error, doesn't crash."""
    tool = ListRunsTool()
    result = await tool.run(limit=10)
    assert result.success is False
    assert "not initialized" in result.output


@pytest.mark.asyncio
async def test_list_runs_returns_empty_when_no_rows(fake_store):
    fake_store.db.set_fetch([])
    result = await ListRunsTool().run(limit=10)
    assert result.success is True
    assert "No runs found" in result.output


@pytest.mark.asyncio
async def test_list_runs_formats_results(fake_store):
    fake_store.db.set_fetch([{
        "id": "abc12345-deadbeef-cafe0000-000000000000",
        "status": "completed",
        "inputs": json_dumps({
            "requirements": "Test the checkout flow",
            "source": "chat-submission",
            "task_type": "chat-job-tier1",
        }),
        "test_count": 12, "passed_count": 10, "failed_count": 2,
        "duration": 5000, "cost_usd": 0.05,
        "created_at": datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 6, 13, 8, 5, tzinfo=timezone.utc),
    }])
    result = await ListRunsTool().run(limit=10)
    assert result.success is True
    assert "abc12345" in result.output
    assert "completed" in result.output
    assert "Test the checkout flow" in result.output
    assert "10/2" in result.output or "10 pass" in result.output


def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# get_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_requires_run_id(fake_store):
    tool = GetRunTool()
    result = await tool.run()
    assert result.success is False
    assert "required" in result.output


@pytest.mark.asyncio
async def test_get_run_returns_not_found(fake_store):
    fake_store.db.set_fetchrow(None)
    result = await GetRunTool().run(run_id="nonexistent")
    assert result.success is False
    assert "No run found" in result.output


@pytest.mark.asyncio
async def test_get_run_formats_detail(fake_store):
    fake_store.db.set_fetchrow({
        "id": "xyz99999-aaaaaaaa-bbbbbbbb-cccccccccccc",
        "status": "failed",
        "inputs": json_dumps({
            "requirements": "Fix the expired card test",
            "source": "github",
            "task_type": "auto",
            "repo_url": "github.com/foo/bar",
            "branch": "main",
        }),
        "test_count": 5, "passed_count": 4, "failed_count": 1,
        "duration": 12000, "cost_usd": 0.10,
        "created_at": datetime(2026, 6, 13, 7, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 6, 13, 7, 12, tzinfo=timezone.utc),
    })
    result = await GetRunTool().run(run_id="xyz99999")
    assert result.success is True
    assert "xyz99999" in result.output
    assert "failed" in result.output
    assert "github.com/foo/bar" in result.output
    assert "main" in result.output
    assert "Fix the expired card test" in result.output


# ---------------------------------------------------------------------------
# get_logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_returns_empty_when_no_events(fake_store):
    fake_store.db.set_fetch([])
    result = await GetLogsTool().run(run_id="run-1")
    assert result.success is True
    assert "No events" in result.output


@pytest.mark.asyncio
async def test_get_logs_formats_events(fake_store):
    fake_store.db.set_fetch([
        {"id": 1, "event_type": "ToolExecutionStarted", "payload": json_dumps({"tool_name": "bash"}), "created_at": datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc)},
        {"id": 2, "event_type": "ToolExecutionCompleted", "payload": json_dumps({"tool_name": "bash", "output_preview": "ok", "success": True}), "created_at": datetime(2026, 6, 13, 8, 0, 1, tzinfo=timezone.utc)},
    ])
    result = await GetLogsTool().run(run_id="abc12345")
    assert result.success is True
    assert "ToolExecutionStarted" in result.output
    assert "ToolExecutionCompleted" in result.output
    assert "2 event(s)" in result.output


# ---------------------------------------------------------------------------
# list_testcases + get_testcase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_testcases_filters(fake_store):
    fake_store.db.set_fetch([
        {"id": "tc-aaaaaaaa", "name": "test_checkout_expired_card",
         "test_type": "e2e", "status": "failing", "priority": "high",
         "updated_at": datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc)},
    ])
    result = await ListTestCasesTool().run(status="failing", test_type="e2e")
    assert result.success is True
    assert "test_checkout_expired_card" in result.output
    # Verify the SQL contained the filter clauses.
    sql, _ = fake_store.db.queries[0]
    assert "status =" in sql
    assert "test_type =" in sql


@pytest.mark.asyncio
async def test_get_testcase_formats_code(fake_store):
    fake_store.db.set_fetchrow({
        "id": "tc-bbbbbbbb", "name": "test_checkout",
        "description": "Tests the basic checkout flow",
        "test_type": "e2e", "status": "failing", "priority": "high",
        "code": "def test_checkout():\n    assert True",
        "code_language": "python",
        "error_message": "TimeoutError: page took too long",
        "updated_at": datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc),
    })
    result = await GetTestCaseTool().run(testcase_id="tc-bbbbbbbb")
    assert result.success is True
    assert "test_checkout" in result.output
    assert "TimeoutError" in result.output
    assert "def test_checkout" in result.output
    assert "python" in result.output


# ---------------------------------------------------------------------------
# get_run_artifacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_artifacts_lists_files(fake_store):
    fake_store.db.set_fetch([
        {"id": 1, "path": "tests/test_checkout.py", "size_bytes": 1024,
         "mime_type": "text/python", "description": "E2E test for checkout"},
        {"id": 2, "path": "coverage.xml", "size_bytes": 8192,
         "mime_type": "text/xml", "description": ""},
    ])
    result = await GetRunArtifactsTool().run(session_id="sess-1")
    assert result.success is True
    assert "tests/test_checkout.py" in result.output
    assert "coverage.xml" in result.output
    assert "1024" in result.output


# ---------------------------------------------------------------------------
# search_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_runs_requires_some_filter(fake_store):
    result = await SearchRunsTool().run()
    assert result.success is False
    assert "required" in result.output.lower()


@pytest.mark.asyncio
async def test_search_runs_by_repo_url(fake_store):
    fake_store.db.set_fetch([])
    result = await SearchRunsTool().run(repo_url="github.com/foo/bar")
    assert result.success is True
    sql, params = fake_store.db.queries[0]
    assert "repo_url" in sql
    assert any("github.com/foo/bar" in str(p) for p in params)


# ---------------------------------------------------------------------------
# get_dashboard_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dashboard_status_summarises(fake_store):
    fake_store.db.set_fetch([
        {"status": "completed", "n": 12},
        {"status": "failed", "n": 3},
        {"status": "running", "n": 1},
    ])
    # Order of fetchrow responses: cost (1st), tokens (2nd), tc count (3rd)
    fake_store.db.set_fetchrow({"total": 0.75})         # cost_usd
    fake_store.db.set_fetchrow({"total": 150000})        # tokens
    fake_store.db.set_fetchrow({"n": 47})               # test_cases
    result = await GetDashboardStatusTool().run()
    assert result.success is True
    assert "12" in result.output  # completed count
    assert "failed: 3" in result.output
    assert "150,000" in result.output or "150000" in result.output
    assert "$0.7500" in result.output
    assert "47" in result.output  # test case count


# ---------------------------------------------------------------------------
# get_coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_coverage_returns_latest_when_no_run_id(fake_store):
    fake_store.db.set_fetch([
        {"language": "python", "framework": "pytest",
         "line_coverage": 87.5, "branch_coverage": 80.0,
         "total_lines": 1000, "covered_lines": 875,
         "created_at": datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc),
         "run_id": "run-1"},
    ])
    result = await GetCoverageTool().run()
    assert result.success is True
    assert "python" in result.output
    assert "87.5" in result.output
    assert "875/1000" in result.output


@pytest.mark.asyncio
async def test_get_coverage_filters_by_run_id(fake_store):
    fake_store.db.set_fetch([])
    result = await GetCoverageTool().run(run_id="specific-run")
    assert result.success is True
    assert "No coverage reports" in result.output
    sql, params = fake_store.db.queries[0]
    assert "run_id" in sql


# ---------------------------------------------------------------------------
# Registration: every chat tool is in the registry and the "chat" toolset
# ---------------------------------------------------------------------------


def test_all_nine_chat_tools_registered():
    expected = {
        "list_runs", "get_run", "get_logs", "list_testcases", "get_testcase",
        "get_run_artifacts", "search_runs", "get_dashboard_status", "get_coverage",
    }
    actual = {
        name for name in expected
        if registry.get_spec(name) is not None
    }
    assert actual == expected, f"missing: {expected - actual}"


def test_chat_toolset_resolves_to_all_nine_plus_handoff():
    """The chat toolset in TOOLSETS includes all 9 introspection tools
    PLUS submit_job (the handoff) PLUS skills_list, skill_view, question."""
    from harness.tools.toolsets import resolve_toolsets, TOOLSETS
    tools = set(resolve_toolsets(["chat"]))
    expected_introspection = {
        "list_runs", "get_run", "get_logs", "list_testcases", "get_testcase",
        "get_run_artifacts", "search_runs", "get_dashboard_status", "get_coverage",
    }
    missing = expected_introspection - tools
    assert not missing, f"chat toolset missing: {missing}"
    # submit_job is in the chat toolset (the handoff).
    assert "submit_job" in tools
    # skills_list, skill_view, question are in the chat toolset.
    assert {"skills_list", "skill_view", "question"}.issubset(tools)
    # bash/write_file/etc. are NOT in the chat toolset.
    assert "bash" not in tools
    assert "write_file" not in tools
    assert "set_mode" not in tools
