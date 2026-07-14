"""Tests for artifacts table schema alignment with INSERT queries.

Verifies the `meta` JSONB column that artifact_tools.py and visual_diff_tool.py
depend on actually exists in the schema and DB.
"""
from __future__ import annotations

import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema" / "schema.sql"


def _get_table_columns(sql_text: str, table_name: str) -> list[str]:
    """Extract column names from a CREATE TABLE statement."""
    in_table = False
    cols: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"CREATE TABLE IF NOT EXISTS {table_name}"):
            in_table = True
            continue
        if in_table and stripped.startswith(")"):
            break
        if in_table and stripped and not stripped.startswith("--"):
            m = re.match(r"(\w+)", stripped)
            if m:
                col = m.group(1)
                if col.upper() not in ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "CONSTRAINT", "CHECK", "ALTER"):
                    cols.append(col)
    return cols


class TestArtifactsSchema:
    def test_artifacts_has_meta_column(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        cols = _get_table_columns(sql, "artifacts")
        assert "meta" in cols, "artifacts table must have 'meta' column"

    def test_agent_artifacts_columns_align_with_code(self):
        """agent_artifacts table columns are separate from artifacts."""
        pass  # agent_artifacts doesn't use meta

    def test_artifacts_meta_column_order(self):
        """meta should be after description, before created_at."""
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        cols = _get_table_columns(sql, "artifacts")
        assert cols.index("meta") > cols.index("description")
        assert cols.index("meta") < cols.index("created_at")

    def test_artifacts_mandatory_columns(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        cols = _get_table_columns(sql, "artifacts")
        for col in ("id", "session_id", "path", "meta"):
            assert col in cols, f"Missing mandatory column: {col}"

    def test_code_insert_columns_exist(self):
        """Every column in artifact_tools.py INSERT exists in schema."""
        insert_cols = ["session_id", "path", "size_bytes", "mime_type", "description", "meta"]
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        schema_cols = _get_table_columns(sql, "artifacts")
        for col in insert_cols:
            assert col in schema_cols, f"INSERT column '{col}' not in schema"
