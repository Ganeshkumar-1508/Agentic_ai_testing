"""Tests for the DB-backed JobCheckpoint store (item 6).

The in-memory backend is the default; production deployments
swap to a Postgres-backed ``PostgresJobCheckpointStore`` via
``set_checkpoint_backend(pg_store)``.

API surface (item 6):
  - **Sync** (in-memory only, dev/test): ``save_checkpoint``,
    ``get_checkpoint``, ``pop_checkpoint``, ``list_checkpoints``.
  - **Async** (routes through active backend): ``asave_checkpoint``,
    ``aget_checkpoint``, ``apop_checkpoint``, ``alist_checkpoints``.
    These are used by the orchestrator's helpers.

The Postgres path raises ``RuntimeError`` on the sync variants
so dev mistakes are caught early. Production code uses the
async variants exclusively.

For the SQL itself, ``schema.sql`` is the source of truth —
the tests here just verify the in-code DDL tuple
(``JOB_CHECKPOINT_DDL``) is consistent.
"""
from __future__ import annotations

import pytest

from harness.services import job_checkpoint
from harness.services.job_checkpoint import (
    JobCheckpoint,
    aget_checkpoint,
    alist_checkpoints,
    apop_checkpoint,
    asave_checkpoint,
    clear_checkpoints,
    get_checkpoint,
    get_checkpoint_backend,
    list_checkpoints,
    pop_checkpoint,
    save_checkpoint,
    set_checkpoint_backend,
)


# ---------------------------------------------------------------------------
# Fake Postgres store
# ---------------------------------------------------------------------------


class _FakePgStore:
    """In-memory simulation of ``PostgresJobCheckpointStore``.

    Mirrors the public surface (save/get/pop/list_checkpoints)
    but stores rows in a dict instead of Postgres. The point
    is to verify the routing in ``job_checkpoint.py`` routes
    to the right backend.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def save_checkpoint(
        self, spec_id, run_id, last_result, paused_by, subagent_state=None,
    ):
        self.rows[spec_id] = {
            "spec_id": spec_id, "run_id": run_id,
            "last_result": last_result, "paused_at": "2026-06-21T00:00:00Z",
            "paused_by": paused_by, "subagent_state": subagent_state,
        }
        return self.rows[spec_id]

    async def get_checkpoint(self, spec_id):
        return self.rows.get(spec_id)

    async def pop_checkpoint(self, spec_id):
        return self.rows.pop(spec_id, None)

    async def list_checkpoints(self):
        return list(self.rows.values())


@pytest.fixture(autouse=True)
def _reset_backend():
    """Reset the backend to in-memory after each test."""
    yield
    set_checkpoint_backend(None)
    clear_checkpoints()


# ---------------------------------------------------------------------------
# Backend routing
# ---------------------------------------------------------------------------


def test_default_backend_is_memory():
    assert get_checkpoint_backend() == "memory"


def test_set_checkpoint_backend_switches_to_postgres():
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    assert get_checkpoint_backend() == "postgres"
    set_checkpoint_backend(None)
    assert get_checkpoint_backend() == "memory"


# ---------------------------------------------------------------------------
# Sync API: in-memory only
# ---------------------------------------------------------------------------


def test_sync_save_get_pop_in_memory():
    save_checkpoint(
        spec_id="spec-1", run_id="run-1",
        last_result={"phase": "post_bootstrap"},
        paused_by="sess-1",
        subagent_state={"completed_subagents": ["sa-1"]},
    )
    ckpt = get_checkpoint("spec-1")
    assert isinstance(ckpt, JobCheckpoint)
    assert ckpt.last_result == {"phase": "post_bootstrap"}
    assert ckpt.subagent_state == {"completed_subagents": ["sa-1"]}

    popped = pop_checkpoint("spec-1")
    assert popped is not None
    assert get_checkpoint("spec-1") is None


def test_sync_api_raises_when_postgres_active():
    """The sync API refuses to work with the Postgres backend
    (catches dev mistakes — production uses the async variants).
    """
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    with pytest.raises(RuntimeError, match="sync-only"):
        save_checkpoint(spec_id="spec-1", run_id="r", last_result={}, paused_by="sess")
    with pytest.raises(RuntimeError, match="sync-only"):
        get_checkpoint("spec-1")
    with pytest.raises(RuntimeError, match="sync-only"):
        pop_checkpoint("spec-1")
    with pytest.raises(RuntimeError, match="sync-only"):
        list_checkpoints()


# ---------------------------------------------------------------------------
# Async API: routes through active backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asave_get_pop_in_memory():
    """The async variants work with the in-memory backend too
    (they wrap the sync call in a coroutine).
    """
    ckpt = await asave_checkpoint(
        spec_id="spec-1", run_id="run-1",
        last_result={"phase": "post_bootstrap"},
        paused_by="sess-1",
    )
    assert isinstance(ckpt, JobCheckpoint)
    fetched = await aget_checkpoint("spec-1")
    assert fetched is not None
    assert fetched.last_result == {"phase": "post_bootstrap"}
    popped = await apop_checkpoint("spec-1")
    assert popped is not None
    assert await aget_checkpoint("spec-1") is None


@pytest.mark.asyncio
async def test_asave_get_pop_postgres():
    """When the backend is Postgres, the async variants route
    through the Postgres store. The returned value is a
    ``JobCheckpoint`` (not a dict) so callers don't need to
    know the backend.
    """
    pg = _FakePgStore()
    set_checkpoint_backend(pg)

    ckpt = await asave_checkpoint(
        spec_id="spec-1", run_id="run-1",
        last_result={"phase": "post_bootstrap"},
        paused_by="sess-1",
        subagent_state={"completed_subagents": ["sa-1", "sa-3"]},
    )
    assert isinstance(ckpt, JobCheckpoint)
    assert ckpt.last_result == {"phase": "post_bootstrap"}
    assert ckpt.subagent_state == {"completed_subagents": ["sa-1", "sa-3"]}
    # The Postgres store was called.
    assert "spec-1" in pg.rows
    # And the in-memory store was NOT touched.
    assert job_checkpoint._store == {}


@pytest.mark.asyncio
async def test_aget_returns_job_checkpoint_from_postgres():
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    await asave_checkpoint(spec_id="spec-1", run_id="r", last_result={"k": "v"}, paused_by="sess")

    ckpt = await aget_checkpoint("spec-1")
    assert isinstance(ckpt, JobCheckpoint)
    assert ckpt.last_result == {"k": "v"}


@pytest.mark.asyncio
async def test_apop_returns_and_removes_from_postgres():
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    await asave_checkpoint(spec_id="spec-1", run_id="r", last_result={}, paused_by="sess")

    popped = await apop_checkpoint("spec-1")
    assert isinstance(popped, JobCheckpoint)
    assert await aget_checkpoint("spec-1") is None
    # The Postgres store was cleared.
    assert "spec-1" not in pg.rows


@pytest.mark.asyncio
async def test_alist_checkpoints_postgres():
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    await asave_checkpoint(spec_id="spec-1", run_id="r", last_result={}, paused_by="sess")
    await asave_checkpoint(spec_id="spec-2", run_id="r", last_result={}, paused_by="sess")
    all_ckpts = await alist_checkpoints()
    assert len(all_ckpts) == 2
    spec_ids = {c.spec_id for c in all_ckpts}
    assert spec_ids == {"spec-1", "spec-2"}


@pytest.mark.asyncio
async def test_switching_back_to_memory_after_postgres():
    """set_checkpoint_backend(None) switches back; in-memory
    state is independent of the Postgres state.
    """
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    await asave_checkpoint(spec_id="spec-pg", run_id="r", last_result={}, paused_by="sess")

    set_checkpoint_backend(None)
    # In-memory is empty (fresh).
    assert get_checkpoint("spec-pg") is None
    save_checkpoint(spec_id="spec-mem", run_id="r", last_result={}, paused_by="sess")
    assert get_checkpoint("spec-mem") is not None
    # Postgres was not affected.
    assert "spec-pg" in pg.rows
    assert "spec-mem" not in pg.rows


# ---------------------------------------------------------------------------
# Cross-backend consistency
# ---------------------------------------------------------------------------


def test_subagent_state_round_trip_in_memory():
    """The full subagent_state shape from item 5 round-trips
    through the in-memory store.
    """
    state = {
        "completed_subagents": ["sa-1", "sa-3", "sa-5"],
        "in_flight_subagents": ["sa-7"],
        "completed_count": 3,
        "in_flight_count": 1,
        "paused_at_phase": "pre_coordinator",
    }
    save_checkpoint(
        spec_id="spec-1", run_id="run-1",
        last_result={"phase": "pre_coordinator"},
        paused_by="sess-1",
        subagent_state=state,
    )
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.subagent_state == state


@pytest.mark.asyncio
async def test_subagent_state_round_trip_postgres():
    """Same shape round-trips through the Postgres store."""
    pg = _FakePgStore()
    set_checkpoint_backend(pg)
    state = {
        "completed_subagents": ["sa-1", "sa-3"],
        "in_flight_subagents": ["sa-7"],
        "completed_count": 2,
        "in_flight_count": 1,
    }
    await asave_checkpoint(
        spec_id="spec-1", run_id="run-1",
        last_result={"phase": "post_kg_index"},
        paused_by="sess-1",
        subagent_state=state,
    )
    ckpt = await aget_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.subagent_state == state


# ---------------------------------------------------------------------------
# Schema consistency
# ---------------------------------------------------------------------------


def test_postgres_ddl_creates_job_checkpoints_table():
    """The in-code ``JOB_CHECKPOINT_DDL`` tuple in
    ``harness/store/adapters/postgres.py`` declares the
    ``job_checkpoints`` table. The same DDL is also in
    ``harness/memory/schema/schema.sql`` (item 6 follow-up).
    This test pins the contract so a refactor of the DDL
    tuple is caught.
    """
    from harness.store.adapters.postgres import JOB_CHECKPOINT_DDL
    # At least one DDL statement must create the table.
    assert any("CREATE TABLE" in ddl and "job_checkpoints" in ddl
               for ddl in JOB_CHECKPOINT_DDL), (
        "JOB_CHECKPOINT_DDL must include a CREATE TABLE for job_checkpoints"
    )
    # And the paused_at index.
    assert any("idx_job_checkpoints_paused_at" in ddl for ddl in JOB_CHECKPOINT_DDL), (
        "JOB_CHECKPOINT_DDL must include the paused_at index"
    )


def test_schema_sql_declares_job_checkpoints_table():
    """The production schema file must include job_checkpoints
    so the table is created at startup (not just lazily on
    first use).
    """
    from pathlib import Path
    schema_path = (
        Path(__file__).parent.parent
        / "harness" / "memory" / "schema" / "schema.sql"
    )
    content = schema_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS job_checkpoints" in content
    assert "spec_id TEXT PRIMARY KEY REFERENCES job_specs(spec_id)" in content
    assert "subagent_state TEXT NOT NULL DEFAULT '{}'" in content
    assert "paused_at TIMESTAMPTZ NOT NULL DEFAULT NOW()" in content
    assert "idx_job_checkpoints_paused_at" in content
