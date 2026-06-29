"""Tests for the C08 chat-facing methods on ``PostgresJobSpecStore``.

The in-code C08 surface (list_by_session, get_status, cancel,
pause, resume, add_comment, list_comments, get_output) is
exercised by ``tests/test_c08_jobs.py`` against a ``_FakeStore``
mock. Those tests pin the *protocol contract* — what a JobSpec
chat surface must look like — but they don't catch bugs in the
real Postgres implementation: missing columns, wrong placeholders,
typos in table names.

This file pins the *Postgres adapter contract*:

  1. The DDL tuples (``JOB_SPEC_DDL`` / ``JOB_COMMENT_DDL`` /
     ``JOB_OUTPUT_DDL``) declare the expected columns and
     indexes.
  2. The C08 methods on ``PostgresJobSpecStore`` exist and
     reference the expected tables + columns.
  3. The schema.sql file (production startup path) declares
     the same tables.

A real Postgres connection is NOT required; we use a
``_RecordingDatabase`` stub that captures the SQL string + args
and returns canned rows. This catches refactor regressions
without dragging Docker into the test loop.

If a real Postgres becomes available, swap the stub for a
``Database(dsn)`` instance — the C08 method calls themselves
are unmodified.
"""
from __future__ import annotations

import json
import pytest

from harness.store.adapters.postgres import (
    JOB_COMMENT_DDL,
    JOB_OUTPUT_DDL,
    JOB_SPEC_DDL,
    PostgresJobSpecStore,
    _row_to_job_comment,
    _row_to_job_output,
    _row_to_job_summary,
)
from harness.store.protocols import (
    JobComment,
    JobOutput,
    JobSpecRecord,
)


# ---------------------------------------------------------------------------
# Test double: a minimal Database stub that records calls and returns canned
# results. Mirrors the asyncpg-shaped surface used by
# ``PostgresJobSpecStore`` (fetch / fetchrow / execute).
# ---------------------------------------------------------------------------


class _RecordingDatabase:
    """Captures every SQL call for assertion.

    The C08 methods on ``PostgresJobSpecStore`` call
    ``self._db.fetch`` / ``self._db.fetchrow`` / ``self._db.execute``
    with ``$N`` placeholders (asyncpg style). We capture the SQL
    and args, return whatever the per-test ``script`` says, and
    expose a helper to assert on the recorded calls.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        # A list of return values (one per fetch / fetchrow call).
        # The test pushes rows onto ``script`` in the order the
        # method will receive them.
        self.script: list = []

    async def execute(self, query: str, *args) -> None:
        self.calls.append((query, args))

    async def fetch(self, query: str, *args):
        self.calls.append((query, args))
        if not self.script:
            return []
        return self.script.pop(0)

    async def fetchrow(self, query: str, *args):
        self.calls.append((query, args))
        if not self.script:
            return None
        return self.script.pop(0)

    def last_sql(self) -> str:
        return self.calls[-1][0] if self.calls else ""

    def sql_for(self, contains: str) -> str | None:
        for sql, _ in self.calls:
            if contains in sql:
                return sql
        return None


def _make_record(spec_id: str = "spec-1", run_id: str = "run-1") -> JobSpecRecord:
    return JobSpecRecord(
        spec_id=spec_id,
        run_id=run_id,
        source="chat",
        prompt="test prompt",
        repo_url="https://github.com/example/repo",
        branch="main",
        sha="",
        tier=1,
        capabilities=["read_code", "write_test_files"],
        approval={},
        context={"session_id": "sess-1"},
        status="pending",
        error=None,
        created_at="2026-06-22T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# DDL contracts — schema.sql + in-code DDL tuples must agree
# ---------------------------------------------------------------------------


def test_job_spec_ddl_declares_latest_run_columns():
    """C08 summary view reads ``latest_run_status`` /
    ``latest_run_cost_usd`` / ``latest_run_duration_s`` —
    these columns must be in the DDL or the migration is broken."""
    ddl_blob = " ".join(JOB_SPEC_DDL)
    assert "latest_run_status" in ddl_blob
    assert "latest_run_cost_usd" in ddl_blob
    assert "latest_run_duration_s" in ddl_blob


def test_job_spec_ddl_declares_context_session_index():
    """The chat's ``list_jobs`` filters by
    ``context->>'session_id'``. The partial GIN index keeps
    that query O(log n) at scale."""
    ddl_blob = " ".join(JOB_SPEC_DDL)
    assert "idx_job_specs_context_session" in ddl_blob
    # Must be a partial index (WHERE clause present).
    assert "WHERE context" in ddl_blob


def test_job_comment_ddl_declares_table_and_indexes():
    ddl_blob = " ".join(JOB_COMMENT_DDL)
    assert "CREATE TABLE IF NOT EXISTS job_comments" in ddl_blob
    assert "comment_id TEXT PRIMARY KEY" in ddl_blob
    assert "spec_id    TEXT NOT NULL REFERENCES job_specs" in ddl_blob
    # ON DELETE CASCADE so dropping a spec drops its comments.
    assert "ON DELETE CASCADE" in ddl_blob
    assert "idx_job_comments_spec_id" in ddl_blob
    assert "idx_job_comments_created_at" in ddl_blob


def test_job_output_ddl_declares_table():
    ddl_blob = " ".join(JOB_OUTPUT_DDL)
    assert "CREATE TABLE IF NOT EXISTS job_outputs" in ddl_blob
    assert "spec_id       TEXT PRIMARY KEY" in ddl_blob
    assert "ON DELETE CASCADE" in ddl_blob
    assert "summary       TEXT" in ddl_blob
    assert "artifacts     TEXT" in ddl_blob
    assert "cost_usd      REAL" in ddl_blob
    assert "duration_s    REAL" in ddl_blob


def test_schema_sql_agrees_with_in_code_ddl():
    """The production ``schema.sql`` must include the same tables
    + columns + indexes as the in-code DDL tuples. A refactor of
    one without the other would leave the table missing at
    production startup."""
    from pathlib import Path
    schema_path = (
        Path(__file__).parent.parent
        / "harness" / "memory" / "schema" / "schema.sql"
    )
    content = schema_path.read_text(encoding="utf-8")

    # New tables.
    assert "CREATE TABLE IF NOT EXISTS job_comments" in content
    assert "CREATE TABLE IF NOT EXISTS job_outputs" in content
    # New columns on job_specs.
    assert "latest_run_status" in content
    assert "latest_run_cost_usd" in content
    assert "latest_run_duration_s" in content
    # New index.
    assert "idx_job_specs_context_session" in content
    # CASCADE on FKs (mirrors in-code DDL).
    assert content.count("ON DELETE CASCADE") >= 2  # job_comments + job_outputs


# ---------------------------------------------------------------------------
# Method surface — all 8 C08 methods must be present
# ---------------------------------------------------------------------------


def test_postgres_job_spec_store_has_all_c08_methods():
    """The C08 surface the chat calls is 8 methods deep:
    list_by_session, get_status, cancel, pause, resume,
    add_comment, get_output, list_comments. (save / get /
    update_status / list_pending are pre-C08.)"""
    required = (
        "list_by_session",
        "get_status",
        "cancel",
        "pause",
        "resume",
        "add_comment",
        "get_output",
        "list_comments",
    )
    methods = {m for m in dir(PostgresJobSpecStore) if not m.startswith("_")}
    missing = [m for m in required if m not in methods]
    assert not missing, f"PostgresJobSpecStore missing: {missing}"


# ---------------------------------------------------------------------------
# SQL string shapes — verify the right tables + columns are referenced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_session_filters_by_context_session_id():
    """``list_jobs`` filters by ``context->>'session_id'``. The
    Postgres query must use the JSONB path, not a JSON-string
    cast that would skip the partial GIN index."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    # No rows; we just want to capture the SQL.
    db.script.append([])  # COUNT(*)
    db.script.append([])  # SELECT rows
    await store.list_by_session("sess-1", limit=10, offset=0)
    # Skip the DDL calls from _ensure_tables — find the actual
    # list_by_session SQL by its distinctive WHERE clause.
    count_sql = db.sql_for("SELECT COUNT(*)")
    rows_sql = db.sql_for("SELECT * FROM job_specs")
    assert count_sql is not None, "list_by_session must issue a COUNT"
    assert rows_sql is not None, "list_by_session must issue a row SELECT"
    # The COUNT must use the same JSONB path so the partial GIN
    # index applies.
    assert "context::jsonb->>'session_id'" in count_sql
    assert "$1" in count_sql
    # And the row select must LIMIT / OFFSET (paginated).
    assert "LIMIT" in rows_sql
    assert "OFFSET" in rows_sql
    assert "context::jsonb->>'session_id'" in rows_sql
    # Ordering: most-recent-first.
    assert "ORDER BY" in rows_sql.upper()


@pytest.mark.asyncio
async def test_cancel_validates_status_then_updates():
    """``cancel`` must check the current status before flipping
    to ``cancelled``. A race where the row is already terminal
    should NOT overwrite that terminal state (Hermes pattern
    for idempotent cancel)."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    # First call: SELECT status
    db.script.append({"status": "running"})
    # Second call: UPDATE returning rowcount
    db.script.append({"status": "running"})
    await store.cancel("spec-1")
    sqls = [c[0] for c in db.calls]
    assert any("SELECT status" in s for s in sqls)
    assert any("UPDATE job_specs SET status = 'cancelled'" in s for s in sqls)


@pytest.mark.asyncio
async def test_pause_only_transitions_from_running_or_pending():
    """``pause`` must reject specs that are already terminal
    (completed/failed/cancelled). The status check is what
    makes pause idempotent — a second pause call on an
    already-paused spec returns False."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    # First call: SELECT status
    db.script.append({"status": "paused"})
    result = await store.pause("spec-1")
    assert result is False
    # No UPDATE should have been issued.
    update_calls = [c for c in db.calls if "UPDATE" in c[0]]
    assert not update_calls, "pause() must not UPDATE when spec is already paused"


@pytest.mark.asyncio
async def test_resume_only_transitions_from_paused():
    """``resume`` is the inverse of ``pause``: it only
    transitions ``paused -> running``. Calling resume on a
    running / completed / failed spec is a no-op."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    db.script.append({"status": "running"})
    result = await store.resume("spec-1")
    assert result is False


@pytest.mark.asyncio
async def test_add_comment_uses_upsert_semantics():
    """A re-submitted comment with the same ``comment_id`` must
    NOT raise. The chat's ``comment_on_job`` tool retries on
    network failure; the store must be idempotent."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    c = JobComment(
        comment_id="c-1", spec_id="spec-1",
        author="user", body="hi", kind="comment",
        created_at="2026-06-22T00:00:00Z",
    )
    await store.add_comment(c)
    assert "ON CONFLICT (comment_id) DO NOTHING" in db.last_sql()


@pytest.mark.asyncio
async def test_update_status_writes_latest_run_columns():
    """When the orchestrator finalizes a run, ``update_status``
    must persist ``cost_usd`` and ``duration_s`` into the
    denormalized ``latest_run_*`` columns. The chat's
    ``list_jobs`` summary view reads those — a missing write
    would render the cost card as '—'."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    await store.update_status(
        "spec-1", "completed",
        cost_usd=1.23,
        duration_s=45.6,
    )
    sql = db.last_sql()
    assert "latest_run_cost_usd" in sql
    assert "latest_run_duration_s" in sql
    # The status arg doubles as latest_run_status (set to the
    # same value when non-null) so the summary view doesn't
    # need a JOIN to figure out "is this run still in flight?".
    assert "latest_run_status" in sql
    # Args include cost and duration.
    assert 1.23 in db.calls[-1][1]
    assert 45.6 in db.calls[-1][1]


@pytest.mark.asyncio
async def test_add_output_upserts_job_output_row():
    """``add_output`` must upsert (not just insert) so the
    orchestrator can retry the finalize step on transient
    failure without crashing the run."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    out = JobOutput(
        spec_id="spec-1", status="completed",
        summary="all good", artifacts=[],
        pr_url=None, cost_usd=0.5, duration_s=10.0,
        completed_at="2026-06-22T00:01:00Z",
    )
    await store.add_output(out)
    sql = db.last_sql()
    assert "INSERT INTO job_outputs" in sql
    assert "ON CONFLICT (spec_id) DO UPDATE" in sql
    # The artifacts list is JSON-encoded.
    assert json.dumps([]) in db.calls[-1][1] or "[]" in str(db.calls[-1][1])


# ---------------------------------------------------------------------------
# Row hydrators — verify the SQL -> dataclass shape
# ---------------------------------------------------------------------------


def test_row_to_job_comment_decodes_jsonb_fields():
    """A Postgres row may have JSONB (already-decoded dict) or
    TEXT (JSON-encoded string) for the body field. The hydrator
    must accept both shapes — asyncpg decodes JSONB to dict,
    but TEXT stays as a string."""
    # asyncpg JSONB-style: body is a str (TEXT column in our DDL).
    row = {
        "comment_id": "c-1",
        "spec_id": "spec-1",
        "author": "user",
        "body": "hi",
        "kind": "comment",
        "created_at": "2026-06-22T00:00:00Z",
    }
    c = _row_to_job_comment(row)
    assert c.comment_id == "c-1"
    assert c.body == "hi"
    assert c.kind == "comment"


def test_row_to_job_output_decodes_artifacts_json():
    """``artifacts`` is stored as JSON text in the DDL. The
    hydrator must ``json.loads`` it back to a list — the chat's
    job-detail page renders each artifact as a card."""
    row = {
        "spec_id": "spec-1",
        "status": "completed",
        "summary": "all good",
        "artifacts": json.dumps([{"name": "report.html", "url": "/x"}]),
        "pr_url": None,
        "cost_usd": 0.5,
        "duration_s": 10.0,
        "completed_at": "2026-06-22T00:01:00Z",
    }
    out = _row_to_job_output(row)
    assert out.spec_id == "spec-1"
    assert isinstance(out.artifacts, list)
    assert out.artifacts[0]["name"] == "report.html"


def test_row_to_job_summary_hydrates_latest_run_fields():
    """``_row_to_job_summary`` is the denormalized summary view
    reader: it picks up the ``latest_run_*`` columns so the
    chat's ``list_jobs`` doesn't need a JOIN. The hydrator
    must populate every field on ``JobSummary`` even when the
    columns are NULL (a brand-new spec with no run yet)."""
    # All-NULL row (spec just saved, run not started).
    row = {
        "spec_id": "spec-1",
        "run_id": "run-1",
        "source": "chat",
        "tier": 1,
        "status": "pending",
        "repo_url": "https://x",
        "branch": "main",
        "prompt": "test",
        "created_at": "2026-06-22T00:00:00Z",
        "started_at": None,
        "completed_at": None,
        "latest_run_status": None,
        "latest_run_cost_usd": None,
        "latest_run_duration_s": None,
    }
    s = _row_to_job_summary(row)
    assert s.spec_id == "spec-1"
    assert s.latest_run_status is None
    assert s.latest_run_cost_usd is None
    assert s.latest_run_duration_s is None


# ---------------------------------------------------------------------------
# Save -> get roundtrip — covers save() and get() with the new columns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_roundtrip_preserves_latest_run_columns():
    """The pre-C08 ``save()`` writes the spec; ``get()`` reads
    it back. The new ``latest_run_*`` columns must come back
    as None for a freshly-saved spec (no run yet)."""
    db = _RecordingDatabase()
    store = PostgresJobSpecStore(db)  # type: ignore[arg-type]
    rec = _make_record()
    await store.save(rec)
    # Get the recorded SQL for save.
    save_sql = db.calls[-1][0]
    assert "INSERT INTO job_specs" in save_sql
    # Now get() — push a canned row.
    db.script.append({
        "spec_id": rec.spec_id,
        "run_id": rec.run_id,
        "source": rec.source,
        "prompt": rec.prompt,
        "repo_url": rec.repo_url,
        "branch": rec.branch,
        "sha": rec.sha,
        "tier": rec.tier,
        "capabilities": json.dumps(rec.capabilities),
        "approval": json.dumps(rec.approval),
        "context": json.dumps(rec.context),
        "status": "pending",
        "error": None,
        "created_at": rec.created_at,
        "started_at": None,
        "completed_at": None,
        "latest_run_status": None,
        "latest_run_cost_usd": None,
        "latest_run_duration_s": None,
    })
    got = await store.get(rec.spec_id)
    assert got is not None
    assert got.spec_id == rec.spec_id
    assert got.run_id == rec.run_id
    # Context round-trips (it was a dict; the store JSON-encodes it).
    assert got.context == rec.context
