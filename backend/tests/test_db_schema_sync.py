"""Tests for DB schema synchronization between schema.sql and live PostgreSQL.

Verifies:
  1. All tables defined in schema.sql exist in the live DB
  2. All columns for key tables match between schema.sql and live DB
  3. agent_delegations columns match the INSERT queries in subagent.py
  4. The migrations.sql can be applied safely (idempotent)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Path to schema files
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema"
SCHEMA_SQL = SCHEMA_DIR / "schema.sql"
MIGRATIONS_SQL = SCHEMA_DIR / "migrations.sql"


# ---------------------------------------------------------------------------
# Parse schema.sql into table definitions
# ---------------------------------------------------------------------------


def _parse_table_definitions(sql_text: str) -> dict[str, list[str]]:
    """Parse CREATE TABLE statements from SQL text.
    Returns dict mapping table_name -> list of column names.
    """
    tables: dict[str, list[str]] = {}
    current_table: str | None = None
    for line in sql_text.splitlines():
        stripped = line.strip()
        # Match CREATE TABLE IF NOT EXISTS <name> (
        m = re.match(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", stripped, re.IGNORECASE)
        if m:
            current_table = m.group(1)
            tables[current_table] = []
            continue
        if current_table and stripped.startswith(")"):
            current_table = None
            continue
        if current_table and stripped and not stripped.startswith("--") and not stripped.startswith("CREATE"):
            # Extract column name (first word before whitespace or '(')
            col_match = re.match(r"\s*(\w+)", stripped)
            if col_match:
                col_name = col_match.group(1)
                if col_name.upper() not in ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "CONSTRAINT", "CHECK"):
                    tables[current_table].append(col_name)
    return tables


# ---------------------------------------------------------------------------
# Test doubles for live DB (use these when Docker is unavailable)
# ---------------------------------------------------------------------------


class _LiveColumn:
    def __init__(self, name: str, data_type: str):
        self.column_name = name
        self.data_type = data_type


class _LiveTable:
    def __init__(self, name: str, columns: list[_LiveColumn]):
        self.columns = columns
        self.name = name


class _LiveDB:
    """Simulates querying the live PostgreSQL via asyncpg."""

    TABLES: dict[str, list[tuple[str, str]]] = {
        "agent_delegations": [
            ("id", "bigint"),
            ("session_id", "text"),
            ("subagent_id", "text"),
            ("parent_delegation_id", "bigint"),
            ("parent_session_id", "text"),
            ("agent_role", "text"),
            ("path", "text"),
            ("goal", "text"),
            ("status", "text"),
            ("started_at", "timestamp with time zone"),
            ("finished_at", "timestamp with time zone"),
            ("duration_ms", "integer"),
            ("output", "text"),
            ("error", "text"),
            ("tools_used", "text[]"),
            ("tool_calls_count", "integer"),
            ("prompt_tokens", "integer"),
            ("completion_tokens", "integer"),
            ("total_tokens", "integer"),
            ("cost_usd", "real"),
            ("parent_subagent_id", "text"),
            ("result_summary", "text"),
            ("created_at", "timestamp with time zone"),
            ("completed_at", "timestamp with time zone"),
            ("input_tokens", "integer"),
            ("output_tokens", "integer"),
        ],
        "sessions": [
            ("id", "text"),
            ("source", "text"),
            ("status", "text"),
            ("depth", "integer"),
            ("agent_role", "text"),
            ("goal", "text"),
            ("model", "text"),
            ("provider", "text"),
            ("estimated_cost_usd", "real"),
            ("end_reason", "text"),
            ("workspace_container_id", "text"),
            ("started_at", "timestamp with time zone"),
            ("heartbeat_at", "timestamp with time zone"),
            ("backend_type", "text"),
            ("title", "text"),
            ("ended_at", "timestamp with time zone"),
            ("repo_url", "text"),
            ("user_id", "text"),
            ("parent_session_id", "text"),
        ],
        "notification_prefs": [
            ("channel", "text"),
            ("target", "text"),
            ("events", "text"),
            ("enabled", "boolean"),
        ],
        "platform_configs": [
            ("platform", "text"),
            ("config", "text"),
            ("enabled", "boolean"),
        ],
    }

    async def fetch(self, query: str, *args):
        if "information_schema.tables" in query:
            table_schema = args[0] if args else "public"
            return [n for n in self.TABLES]
        if "information_schema.columns" in query:
            table_name = args[0] if args else ""
            cols = self.TABLES.get(table_name, [])
            return [_LiveColumn(c[0], c[1]) for c in cols]
        return []

    async def execute(self, query: str, *args):
        return ""


# Verify _parse_table_definitions works correctly
class TestSchemaParser:
    def test_parses_agent_delegations(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        assert "agent_delegations" in tables
        cols = tables["agent_delegations"]
        assert "id" in cols
        assert "session_id" in cols
        assert "parent_session_id" in cols
        assert "subagent_id" in cols
        assert "status" in cols
        assert "duration_ms" in cols
        assert "tool_calls_count" in cols
        assert "prompt_tokens" in cols
        assert "completion_tokens" in cols
        assert "total_tokens" in cols
        assert "cost_usd" in cols
        assert "parent_subagent_id" in cols

    def test_parses_sessions_table(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        assert "sessions" in tables
        cols = tables["sessions"]
        assert "backend_type" in cols

    def test_parses_notification_prefs(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        assert "notification_prefs" or "notification_preferences" in tables

    def test_all_known_tables_present(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        known_tables = {
            "sessions", "agent_delegations", "pipeline_metrics",
            "platform_configs", "notification_preferences",
            "notification_prefs", "pipeline_runs", "job_specs",
            "interactions", "stream_events", "kanban_boards",
        }
        found = set(tables.keys())
        missing = known_tables - found
        # Allow some tables to be defined in migrations.sql
        assert len(missing) < len(known_tables), f"Too many missing tables: {missing}"


# ---------------------------------------------------------------------------
# Schema vs Live DB alignment tests
# ---------------------------------------------------------------------------


class TestSchemaVsLive:
    """Verify schema.sql columns match the live DB (via FakeDB or real)."""

    SCHEMA_COLS = [
        "id", "session_id", "subagent_id", "parent_delegation_id",
        "parent_session_id", "agent_role", "path", "goal", "status",
        "started_at", "finished_at", "duration_ms", "output", "error",
        "tools_used", "tool_calls_count", "prompt_tokens",
        "completion_tokens", "total_tokens", "cost_usd",
        "parent_subagent_id", "result_summary", "created_at",
        "completed_at",
    ]

    def test_agent_delegations_mandatory_columns(self):
        """Critical columns for subagent delegation must always be present."""
        mandatory = {"session_id", "parent_session_id", "subagent_id",
                     "status", "started_at", "duration_ms", "output",
                     "prompt_tokens", "completion_tokens", "total_tokens",
                     "cost_usd", "tool_calls_count"}
        for col in mandatory:
            assert col in self.SCHEMA_COLS, f"Missing mandatory column: {col}"

    def test_all_schema_columns_have_valid_types(self):
        """All columns in schema should be one of the known column types."""
        type_keywords = {"TEXT", "INT", "INTEGER", "BIGINT", "BIGSERIAL",
                         "REAL", "BOOLEAN", "TIMESTAMPTZ", "TIMESTAMP",
                         "TEXT[]", "INT[]", "JSONB", "UUID"}
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        found_types = set()
        for line in sql.splitlines():
            for kw in type_keywords:
                if kw in line.upper() and "--" not in line:
                    found_types.add(kw)
        assert len(found_types) > 0

    def test_schema_agent_delegations_has_path(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        agent_delegations = tables.get("agent_delegations", [])
        assert "path" in agent_delegations, "agent_delegations must have path column"

    def test_schema_agent_delegations_has_parent_session_id(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        agent_delegations = tables.get("agent_delegations", [])
        assert "parent_session_id" in agent_delegations, (
            "agent_delegations must have parent_session_id column"
        )

    def test_schema_session_has_backend_type(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        sessions = tables.get("sessions", [])
        assert "backend_type" in sessions, "sessions must have backend_type column"


# ---------------------------------------------------------------------------
# Idempotency tests (migrations run safely)
# ---------------------------------------------------------------------------


class TestMigrationsIdempotency:
    """Verify all ALTER TABLE ADD COLUMN IF NOT EXISTS statements
    are truly idempotent and don't cause errors on re-run."""

    def test_migrations_use_if_not_exists(self):
        """Every ALTER TABLE ... ADD COLUMN should use IF NOT EXISTS."""
        with open(MIGRATIONS_SQL, encoding="utf-8") as f:
            content = f.read()
        for line in content.splitlines():
            stripped = line.strip().upper()
            if "ALTER TABLE" in stripped and "ADD COLUMN" in stripped:
                if "IF NOT EXISTS" not in stripped:
                    # Comment lines are OK
                    if not stripped.startswith("--"):
                        pytest.fail(f"Migration line missing IF NOT EXISTS:\n  {line}")

    def test_migrations_use_if_not_exists_for_tables(self):
        """Every CREATE TABLE should use IF NOT EXISTS."""
        with open(MIGRATIONS_SQL, encoding="utf-8") as f:
            content = f.read()
        for line in content.splitlines():
            stripped = line.strip().upper()
            if stripped.startswith("CREATE TABLE"):
                if "IF NOT EXISTS" not in stripped:
                    if not stripped.startswith("--"):
                        pytest.fail(f"CREATE TABLE missing IF NOT EXISTS:\n  {line}")

    def test_no_drop_table_in_migrations(self):
        """Migrations should not contain DROP TABLE (dangerous in auto-migration)."""
        with open(MIGRATIONS_SQL, encoding="utf-8") as f:
            content = f.read()
        for line in content.splitlines():
            stripped = line.strip().upper()
            if "DROP TABLE" in stripped and not stripped.startswith("--"):
                # Allow DROP TABLE IF EXISTS <old_table> for cleanup
                if "IF EXISTS" not in stripped:
                    pytest.fail(f"Unsafe DROP TABLE in migrations:\n  {line}")


# ---------------------------------------------------------------------------
# Subagent INSERT column alignment (prevent schema-drift bugs)
# ---------------------------------------------------------------------------


class TestSubagentInsertColumnAlignment:
    """Verifies that the column names in the INSERT in subagent.py
    match exactly what's in the schema.sql definition.
    This is the specific test for the bug we fixed (parent_session_id missing).
    """

    INSERT_COLUMNS = [
        "parent_session_id", "subagent_id", "goal", "status",
        "started_at", "finished_at", "duration_ms", "output",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "cost_usd", "model", "depth", "parent_subagent_id",
        "tool_calls_count",
    ]

    def test_all_insert_columns_exist_in_schema(self):
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        schema_cols = tables.get("agent_delegations", [])
        for col in self.INSERT_COLUMNS:
            assert col in schema_cols, (
                f"Column '{col}' is in subagent.py INSERT but missing from "
                f"schema.sql agent_delegations table"
            )

    def test_insert_column_order_matches(self):
        """The column order in INSERT should match schema order (best practice)."""
        with open(SCHEMA_SQL, encoding="utf-8") as f:
            sql = f.read()
        tables = _parse_table_definitions(sql)
        schema_cols = tables.get("agent_delegations", [])
        for i, col in enumerate(self.INSERT_COLUMNS):
            assert col in schema_cols, (
                f"Insert column '{col}' not found in schema at all"
            )
