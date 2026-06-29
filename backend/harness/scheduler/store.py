from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from harness.memory.database import Database


async def create_table(db: Database) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            schedule_type TEXT NOT NULL,
            schedule_expr TEXT NOT NULL,
            skill TEXT,
            script TEXT,
            enabled BOOLEAN DEFAULT true,
            state TEXT DEFAULT 'scheduled',
            next_run_at TIMESTAMPTZ,
            last_run_at TIMESTAMPTZ,
            last_status TEXT,
            max_repeats INT,
            repeat_count INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


async def create_job(db: Database, job: dict[str, Any]) -> dict[str, Any]:
    row = await db.fetchrow(
        """INSERT INTO cron_jobs (name, prompt, schedule_type, schedule_expr, skill, script, max_repeats, next_run_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *""",
        job["name"], job["prompt"], job["schedule_type"],
        job["schedule_expr"], job.get("skill"), job.get("script"),
        job.get("max_repeats"), job.get("next_run_at"),
    )
    return _row_to_dict(row)


async def list_jobs(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetch("SELECT * FROM cron_jobs ORDER BY created_at DESC")
    return [_row_to_dict(r) for r in rows]


async def get_job(db: Database, job_id: str) -> dict[str, Any] | None:
    row = await db.fetchrow("SELECT * FROM cron_jobs WHERE id = $1", job_id)
    return _row_to_dict(row) if row else None


async def update_job(db: Database, job_id: str, updates: dict[str, Any]) -> bool:
    sets = []
    vals: list[Any] = []
    i = 1
    for key in ("name", "prompt", "schedule_type", "schedule_expr", "skill", "script",
                 "enabled", "state", "next_run_at", "last_run_at", "last_status",
                 "max_repeats", "repeat_count"):
        if key in updates:
            sets.append(f"{key} = ${i}")
            vals.append(updates[key])
            i += 1
    if not sets:
        return False
    sets.append("updated_at = NOW()")
    vals.append(job_id)
    await db.execute(
        f"UPDATE cron_jobs SET {', '.join(sets)} WHERE id = ${i}",
        *vals,
    )
    return True


async def delete_job(db: Database, job_id: str) -> bool:
    r = await db.execute("DELETE FROM cron_jobs WHERE id = $1", job_id)
    return "DELETE 1" in r


async def due_jobs(db: Database) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    rows = await db.fetch(
        "SELECT * FROM cron_jobs WHERE next_run_at <= $1 AND state = 'scheduled' AND enabled = true ORDER BY next_run_at ASC",
        now,
    )
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row else {}
