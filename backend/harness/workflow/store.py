"""Workflow execution store — persists execution records and allows replay.

Uses Postgres via the existing get_db() pool. Falls back to in-memory
dictionary when DB is unavailable.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from harness.workflow.models import (
    ExecutionStatus,
    StepExecutionRecord,
    WorkflowExecutionRecord,
)

logger = logging.getLogger(__name__)

# In-memory fallback store when DB is unavailable
_memory_store: dict[str, WorkflowExecutionRecord] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def save_execution(
    db: Any,
    record: WorkflowExecutionRecord,
) -> str:
    """Persist a workflow execution record. Returns the execution ID."""
    if db and hasattr(db, "execute"):
        try:
            await db.execute(
                """INSERT INTO workflow_executions
                   (id, workflow_key, status, started_at, completed_at,
                    duration_sec, steps_json, error, triggered_by, retry_of)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                record.id, record.workflow_key, record.status,
                record.started_at, record.completed_at or None,
                record.duration_sec,
                json.dumps([s.__dict__ for s in record.steps]),
                record.error[:500] if record.error else "",
                record.triggered_by, record.retry_of or None,
            )
        except Exception as exc:
            logger.warning("save_execution DB failed, falling back to memory: %s", exc)
            _memory_store[record.id] = record
    else:
        _memory_store[record.id] = record
    return record.id


async def list_executions(
    db: Any,
    workflow_key: str = "",
    limit: int = 20,
) -> list[WorkflowExecutionRecord]:
    """List execution records, optionally filtered by workflow_key."""
    rows = []
    if db and hasattr(db, "fetch"):
        try:
            if workflow_key:
                rows = await db.fetch(
                    "SELECT * FROM workflow_executions WHERE workflow_key = $1 "
                    "ORDER BY started_at DESC LIMIT $2",
                    workflow_key, limit,
                )
            else:
                rows = await db.fetch(
                    "SELECT * FROM workflow_executions ORDER BY started_at DESC LIMIT $1",
                    limit,
                )
        except Exception as exc:
            logger.debug("list_executions DB failed, using memory: %s", exc)

    results = [_row_to_record(r) for r in rows]

    # Merge in-memory records
    for rec in _memory_store.values():
        if not workflow_key or rec.workflow_key == workflow_key:
            results.append(rec)

    results.sort(key=lambda r: r.started_at, reverse=True)
    return results[:limit]


async def get_execution(db: Any, execution_id: str) -> WorkflowExecutionRecord | None:
    """Get a single execution record by ID."""
    if db and hasattr(db, "fetchrow"):
        try:
            row = await db.fetchrow(
                "SELECT * FROM workflow_executions WHERE id = $1", execution_id,
            )
            if row:
                return _row_to_record(row)
        except Exception as exc:
            logger.debug("get_execution DB failed: %s", exc)

    return _memory_store.get(execution_id)


async def create_workflow_executions_table(db: Any) -> None:
    """Create the workflow_executions table if it doesn't exist."""
    if not db or not hasattr(db, "execute"):
        return
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflow_executions (
                id TEXT PRIMARY KEY,
                workflow_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                duration_sec FLOAT DEFAULT 0.0,
                steps_json TEXT DEFAULT '[]',
                error TEXT DEFAULT '',
                triggered_by TEXT DEFAULT 'manual',
                retry_of TEXT DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_exec_key
            ON workflow_executions(workflow_key, started_at DESC)
        """)
        logger.info("workflow_executions table ready")
    except Exception as exc:
        logger.warning("create_workflow_executions_table failed: %s", exc)


def _row_to_record(row: Any) -> WorkflowExecutionRecord:
    steps_data = json.loads(row.get("steps_json") or "[]")
    steps = [
        StepExecutionRecord(**s) if isinstance(s, dict) else s
        for s in steps_data
    ]
    return WorkflowExecutionRecord(
        id=row["id"],
        workflow_key=row["workflow_key"],
        status=row["status"],
        started_at=row.get("started_at", ""),
        completed_at=row.get("completed_at") or "",
        duration_sec=float(row.get("duration_sec") or 0),
        steps=steps,
        error=row.get("error") or "",
    )
