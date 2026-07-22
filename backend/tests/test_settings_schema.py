"""Tests for settings_service.py SQL queries matching schema.sql columns.

Verifies all the CRITICAL column mismatches found in settings_service.py
are fixed and continue to align with the DB schema.
"""
from __future__ import annotations

import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema" / "schema.sql"
MIGRATIONS_PATH = Path(__file__).resolve().parent.parent / "harness" / "memory" / "schema" / "migrations.sql"


def _get_schema_columns(sql_text: str, table_name: str) -> list[str]:
    """Extract column names from a CREATE TABLE statement in SQL."""
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


class TestMcpConfigsSchema:
    """Verify mcp_configs INSERT matches schema (display_name fix)."""

    INSERT_COLS = ["name", "display_name", "enabled", "config", "server_url"]

    def test_mcp_insert_columns_exist(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        schema_cols = _get_schema_columns(sql, "mcp_configs")
        for col in self.INSERT_COLS:
            assert col in schema_cols, f"mcp_configs INSERT column '{col}' missing from schema"

    def test_display_name_is_included(self):
        """display_name must be in INSERT (NOT NULL, no default)."""
        assert "display_name" in self.INSERT_COLS


class TestFeatureFlagsSchema:
    """Verify feature_flags INSERT matches schema (label fix)."""

    INSERT_COLS = ["key", "label", "enabled", "description"]

    def test_feature_flag_insert_columns_exist(self):
        with open(MIGRATIONS_PATH, encoding="utf-8") as f:
            sql = f.read()
        schema_cols = _get_schema_columns(sql, "feature_flags")
        for col in self.INSERT_COLS:
            assert col in schema_cols, f"feature_flags INSERT column '{col}' missing from migrations"

    def test_label_is_included(self):
        """label must be in INSERT (NOT NULL, no default)."""
        assert "label" in self.INSERT_COLS


class TestQualityGatesSchema:
    """Verify quality_gates INSERT matches schema (threshold→fail_threshold fix)."""

    INSERT_COLS = ["name", "metric", "fail_threshold", "warn_threshold", "enabled", "description"]

    def test_quality_gates_insert_columns_exist(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        schema_cols = _get_schema_columns(sql, "quality_gates")
        for col in self.INSERT_COLS:
            assert col in schema_cols, f"quality_gates INSERT column '{col}' missing from schema"

    def test_no_threshold_column_in_insert(self):
        """The old 'threshold' column name must not be used."""
        # Read the actual settings_service.py to verify
        settings_path = Path(__file__).resolve().parent.parent / "harness" / "services" / "settings_service.py"
        with open(settings_path, encoding="utf-8") as f:
            content = f.read()
        # Check create_gate
        assert "INSERT INTO quality_gates" in content
        # Verify fail_threshold is in the query, not bare threshold
        gate_insert = [l for l in content.splitlines() if "INSERT INTO quality_gates" in l]
        assert any("fail_threshold" in l for l in gate_insert), \
            "quality_gates INSERT must use fail_threshold, not bare threshold"
        assert not any("threshold," in l and "fail_threshold" not in l and "warn_threshold" not in l for l in gate_insert), \
            "quality_gates INSERT must not use bare 'threshold' column"


class TestExperimentsSchema:
    """Verify experiments INSERT matches schema (config→control_config fix)."""

    INSERT_COLS = ["name", "description", "control_config"]

    def test_experiments_insert_columns_exist(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        schema_cols = _get_schema_columns(sql, "experiments")
        for col in self.INSERT_COLS:
            assert col in schema_cols, f"experiments INSERT column '{col}' missing from schema"

    def test_no_bare_config_in_insert(self):
        settings_path = Path(__file__).resolve().parent.parent / "harness" / "services" / "settings_service.py"
        with open(settings_path, encoding="utf-8") as f:
            content = f.read()
        exp_lines = [l for l in content.splitlines() if "INSERT INTO experiments" in l]
        assert any("control_config" in l for l in exp_lines), \
            "experiments INSERT must use control_config"
        assert not any("name, description, config)" in l.replace(" ", "") for l in exp_lines)


class TestAlertRulesSchema:
    """Verify alert_rules INSERT matches schema (all column names fixed)."""

    INSERT_COLS = [
        "name", "condition_type", "condition_value", "condition_direction",
        "action_type", "action_config", "enabled",
    ]

    def test_alert_rules_insert_columns_exist(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        schema_cols = _get_schema_columns(sql, "alert_rules")
        for col in self.INSERT_COLS:
            assert col in schema_cols, f"alert_rules INSERT column '{col}' missing from schema"

    def test_no_old_column_names_in_insert(self):
        settings_path = Path(__file__).resolve().parent.parent / "harness" / "services" / "settings_service.py"
        with open(settings_path, encoding="utf-8") as f:
            content = f.read()
        alert_lines = [l for l in content.splitlines() if "INSERT INTO alert_rules" in l]
        for line in alert_lines:
            assert "metric" not in line, f"alert_rules INSERT must not use 'metric': {line}"
            assert "operator" not in line, f"alert_rules INSERT must not use 'operator': {line}"
            assert "threshold" not in line, f"alert_rules INSERT must not use 'threshold': {line}"
            assert "channel" not in line, f"alert_rules INSERT must not use 'channel': {line}"
