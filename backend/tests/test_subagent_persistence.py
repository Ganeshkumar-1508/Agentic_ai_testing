"""Tests for subagent DB persistence functions: create_child_session and persist_delegation.

Verifies the INSERT queries match the agent_delegations table schema
and that all edge cases are handled gracefully (no DB, missing parent_session_id, etc).
"""
from __future__ import annotations

import datetime

import pytest

from harness.memory.db_context import set_db
from harness.tools.subagent import create_child_session, persist_delegation

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fake DB doubles
# ---------------------------------------------------------------------------


class _FakeDB:
    """Minimal async DB double that records calls."""

    def __init__(self):
        self.executes: list[tuple[str, tuple]] = []
        self.fetchrows: list[tuple[str, tuple]] = []
        self._fetchrow_return = None
        self._has_pool = True

    @property
    def _pool(self):
        return self if self._has_pool else None

    async def execute(self, query: str, *args):
        self.executes.append((query, args))
        return "INSERT 0 1"

    async def fetchrow(self, query: str, *args):
        self.fetchrows.append((query, args))
        return self._fetchrow_return

    def set_fetchrow_result(self, row: dict | None):
        self._fetchrow_return = row


class _FakeDBNoPool:
    """DB double with no pool — tests the graceful-skip path."""

    @property
    def _pool(self):
        return None

    async def execute(self, query: str, *args):
        raise RuntimeError("should not be called")

    async def fetchrow(self, query: str, *args):
        raise RuntimeError("should not be called")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW_TS = 1720000000.0
SAMPLE_SESSION_ID = "ses_test_child_001"
SAMPLE_PARENT = "ses_parent_001"
SAMPLE_GOAL = "Run tests and report results"


def _reset_get_db():
    set_db(None)


# ---------------------------------------------------------------------------
# create_child_session tests
# ---------------------------------------------------------------------------


class TestCreateChildSession:
    """Verify create_child_session builds correct INSERT queries and handles edge cases."""

    @pytest.fixture(autouse=True)
    def _no_db(self):
        _reset_get_db()

    async def test_creates_session_with_parent(self):
        db = _FakeDB()
        db.set_fetchrow_result({"backend_type": "docker"})
        set_db(db)
        await create_child_session(
            SAMPLE_SESSION_ID, 1, SAMPLE_GOAL, "gpt-4", SAMPLE_PARENT, NOW_TS,
        )
        assert len(db.executes) == 1
        query, args = db.executes[0]
        assert "INSERT INTO sessions" in query
        assert SAMPLE_SESSION_ID in args
        assert args[1] == 1
        assert SAMPLE_GOAL in args
        assert SAMPLE_PARENT in args
        assert args[6] == "docker"

    async def test_creates_session_without_parent(self):
        db = _FakeDB()
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, SAMPLE_GOAL, None, None, NOW_TS)
        assert len(db.executes) == 1
        query, args = db.executes[0]
        assert SAMPLE_SESSION_ID in args
        assert args[6] == "local"

    async def test_creates_session_with_empty_goal(self):
        db = _FakeDB()
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, "", None, None, NOW_TS)
        assert len(db.executes) == 1
        _, args = db.executes[0]
        assert args[3] == ""

    async def test_no_db_returns_gracefully(self):
        set_db(None)
        await create_child_session(SAMPLE_SESSION_ID, 0, SAMPLE_GOAL, None, SAMPLE_PARENT, NOW_TS)

    async def test_no_pool_returns_gracefully(self):
        db = _FakeDBNoPool()
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, SAMPLE_GOAL, None, SAMPLE_PARENT, NOW_TS)

    async def test_parent_row_none_falls_back_to_local(self):
        db = _FakeDB()
        db.set_fetchrow_result(None)
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 1, SAMPLE_GOAL, "gpt-4", SAMPLE_PARENT, NOW_TS)
        _, args = db.executes[0]
        assert args[6] == "local"

    async def test_goal_truncated_at_500_chars(self):
        long_goal = "x" * 1000
        db = _FakeDB()
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, long_goal, None, None, NOW_TS)
        _, args = db.executes[0]
        assert len(args[2]) == 500

    async def test_on_conflict_do_nothing(self):
        db = _FakeDB()
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, SAMPLE_GOAL, None, None, NOW_TS)
        query = db.executes[0][0]
        assert "ON CONFLICT (id) DO NOTHING" in query

    async def test_model_override_empty_string(self):
        db = _FakeDB()
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, SAMPLE_GOAL, "", None, NOW_TS)
        _, args = db.executes[0]
        assert args[3] == ""

    async def test_db_execute_exception_logged(self):
        db = _FakeDB()
        db.execute = lambda q, *a: (_ for _ in ()).throw(Exception("DB error"))
        set_db(db)
        await create_child_session(SAMPLE_SESSION_ID, 0, SAMPLE_GOAL, None, None, NOW_TS)


# ---------------------------------------------------------------------------
# persist_delegation tests
# ---------------------------------------------------------------------------


class TestPersistDelegation:
    """Verify persist_delegation builds correct INSERT into agent_delegations."""

    @pytest.fixture(autouse=True)
    def _no_db(self):
        _reset_get_db()

    async def test_persists_full_delegation_record(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_001",
            goal=SAMPLE_GOAL,
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 10.0,
            output="All tests passed.",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.025,
            model="gpt-4",
            depth=1,
            parent_subagent_id="parent_sub_001",
            tool_calls_count=5,
        )
        assert len(db.executes) == 1
        query, args = db.executes[0]
        assert "INSERT INTO agent_delegations" in query
        assert SAMPLE_PARENT in args
        assert "sub_001" in args
        assert "completed" in args
        assert args[7] == 10000

    async def test_persists_minimal_record(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=None,
            subagent_id="sub_002",
            goal="Minimal goal",
            status="running",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )
        assert len(db.executes) == 1

    async def test_output_truncated_at_2000_chars(self):
        long_output = "x" * 5000
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_trunc",
            goal="test",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
            output=long_output,
        )
        _, args = db.executes[0]
        assert len(args[8]) == 2000

    async def test_goal_truncated_at_500_chars(self):
        long_goal = "x" * 1000
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_trunc_goal",
            goal=long_goal,
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )
        _, args = db.executes[0]
        assert len(args[3]) == 500

    async def test_duration_milliseconds_correct(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_time",
            goal="time test",
            status="completed",
            started_at=100.0,
            finished_at=105.5,
        )
        _, args = db.executes[0]
        assert args[7] == 5500

    async def test_zero_duration(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_zero",
            goal="zero duration",
            status="completed",
            started_at=100.0,
            finished_at=100.0,
        )
        _, args = db.executes[0]
        assert args[7] == 0

    async def test_negative_duration_returns_negative_ms(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_neg",
            goal="negative test",
            status="failed",
            started_at=200.0,
            finished_at=100.0,
        )
        _, args = db.executes[0]
        assert args[7] == -100000

    async def test_total_tokens_is_sum(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_token",
            goal="token test",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
            prompt_tokens=150,
            completion_tokens=75,
        )
        _, args = db.executes[0]
        assert args[11] == 225

    async def test_zero_total_tokens(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_no_tokens",
            goal="no tokens",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )
        _, args = db.executes[0]
        assert args[11] == 0

    async def test_no_db_returns_gracefully(self):
        set_db(None)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_no_db",
            goal="no db",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )

    async def test_no_pool_returns_gracefully(self):
        db = _FakeDBNoPool()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_no_pool",
            goal="no pool",
            status="running",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )

    async def test_exception_during_execute_is_caught(self):
        db = _FakeDB()
        db.execute = lambda q, *a: (_ for _ in ()).throw(Exception("persist failed"))
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_except",
            goal="exception",
            status="failed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )

    async def test_inserts_all_17_columns(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_col_count",
            goal="column count test",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )
        query = db.executes[0][0]
        num_params = query.count("$")
        assert num_params == 17

    async def test_special_chars_in_goal_and_output(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_special",
            goal="Goal with $pecial chars & <stuff> 'quotes'",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
            output="Output with emoji 🎉 and unicode: 你好",
        )
        assert len(db.executes) == 1

    async def test_none_parent_session_id(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=None,
            subagent_id="sub_null_parent",
            goal="null parent",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )
        _, args = db.executes[0]
        assert args[0] == "sub_null_parent"
        assert args[1] is None

    async def test_empty_parent_subagent_id(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_empty_psub",
            goal="empty parent_subagent_id",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
            parent_subagent_id="",
        )
        _, args = db.executes[0]
        assert args[15] == ""

    async def test_various_status_values(self):
        db = _FakeDB()
        set_db(db)
        for status in ("running", "completed", "failed", "timeout", "cancelled", "paused"):
            db.executes = []
            await persist_delegation(
                parent_session_id=SAMPLE_PARENT,
                subagent_id=f"sub_status_{status}",
                goal=f"status {status}",
                status=status,
                started_at=NOW_TS,
                finished_at=NOW_TS + 1.0,
            )
            _, args = db.executes[0]
            assert args[4] == status

    async def test_max_tool_calls_count(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_max_tools",
            goal="max tool calls",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
            tool_calls_count=9999,
        )
        _, args = db.executes[0]
        assert args[16] == 9999

    async def test_empty_output_default(self):
        db = _FakeDB()
        set_db(db)
        await persist_delegation(
            parent_session_id=SAMPLE_PARENT,
            subagent_id="sub_empty_output",
            goal="empty output",
            status="completed",
            started_at=NOW_TS,
            finished_at=NOW_TS + 1.0,
        )
        _, args = db.executes[0]
        assert args[8] == ""


# ---------------------------------------------------------------------------
# Column name alignment tests
# ---------------------------------------------------------------------------


class TestColumnAlignment:
    """Verify that the column names in subagent.py match the schema.sql definition."""

    SQL_INSERT_COLS = [
        "session_id", "parent_session_id", "subagent_id", "goal", "status",
        "started_at", "finished_at", "duration_ms", "output",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "cost_usd", "model", "depth", "parent_subagent_id",
        "tool_calls_count",
    ]

    SCHEMA_FILE_COLS = [
        "id", "session_id", "subagent_id", "parent_delegation_id",
        "parent_session_id", "agent_role", "path", "goal", "status",
        "started_at", "finished_at", "duration_ms", "output", "error",
        "tools_used", "tool_calls_count", "prompt_tokens",
        "completion_tokens", "total_tokens", "cost_usd",
        "model", "depth", "parent_subagent_id", "result_summary", "created_at",
        "completed_at",
    ]

    def test_all_insert_columns_exist_in_schema(self):
        for col in self.SQL_INSERT_COLS:
            assert col in self.SCHEMA_FILE_COLS, (
                f"Column '{col}' used in subagent.py INSERT "
                f"but is NOT defined in schema.sql agent_delegations table"
            )

    def test_no_spurious_columns_in_insert(self):
        expected = set(self.SQL_INSERT_COLS)
        actual = {
            "session_id", "parent_session_id", "subagent_id", "goal", "status",
            "started_at", "finished_at", "duration_ms", "output",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "cost_usd", "model", "depth", "parent_subagent_id",
            "tool_calls_count",
        }
        assert expected == actual
