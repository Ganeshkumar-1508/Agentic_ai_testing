"""Daily artifact janitor.

P0 audit fix 2026-06-23: implements the documented TTL policy that
the schema columns ``expires_at`` and ``retention_kind`` were added
to support. The CONTEXT.md claim of:

    committed test files = permanent,
    trajectories          = 30 d,
    LLM transcripts       = 7 d

was unbacked by code. The janitor runs once per process start and
then on a configurable schedule (``ARTIFACT_JANITOR_INTERVAL_SECONDS``,
default 24 h) to delete rows past their ``expires_at`` and the
matching JSONL files for ``session_trajectories``.

The function is pure-Postgres + filesystem; it has no LLM calls. The
job is intentionally idempotent — re-running it on already-cleaned
data is a no-op.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Default TTLs (seconds). Override via env. The defaults mirror the
# CONTEXT.md glossary.
DEFAULT_TTLS: dict[str, int] = {
    "transcript": 7 * 24 * 3600,    # 7 d
    "trajectory": 30 * 24 * 3600,   # 30 d
    "trace": 7 * 24 * 3600,         # 7 d
    "test_file": 0,                 # 0 = permanent (never auto-delete)
    "artifact": 90 * 24 * 3600,     # 90 d default for ad-hoc artifacts
}


def _env_ttls() -> dict[str, int]:
    """Read TTL overrides from env. Missing keys fall back to default."""
    out = dict(DEFAULT_TTLS)
    for key, default in DEFAULT_TTLS.items():
        env = os.environ.get(f"ARTIFACT_TTL_{key.upper()}_SECONDS")
        if env and env.isdigit():
            out[key] = int(env)
    return out


async def _expire_unset_rows(db: Any, ttls: dict[str, int]) -> int:
    """Stamp ``expires_at`` on rows that have a ``retention_kind`` but
    no expiry yet. Returns the number of rows stamped.

    For ``test_file`` (TTL = 0) we leave ``expires_at`` NULL.
    """
    stamped = 0
    for kind, ttl in ttls.items():
        if ttl <= 0:
            continue
        # stream_events
        try:
            res = await db.execute(
                "UPDATE stream_events SET expires_at = NOW() + ($1 || ' seconds')::interval "
                "WHERE retention_kind = $2 AND expires_at IS NULL",
                str(ttl), kind,
            )
            if res:
                stamped += int(res.split()[-1]) if isinstance(res, str) and res else 0
        except Exception as exc:
            logger.debug("expire_unset stream_events %s: %s", kind, exc)
        # trace_events
        try:
            res = await db.execute(
                "UPDATE trace_events SET expires_at = NOW() + ($1 || ' seconds')::interval "
                "WHERE retention_kind = $2 AND expires_at IS NULL",
                str(ttl), kind,
            )
        except Exception as exc:
            logger.debug("expire_unset trace_events %s: %s", kind, exc)
    return stamped


async def _delete_expired_rows(db: Any) -> dict[str, int]:
    """Delete rows whose ``expires_at`` is in the past. Returns counts
    per table for the run log.
    """
    counts: dict[str, int] = {}
    for table in (
        "stream_events",
        "trace_events",
        "agent_artifacts",
        "artifacts",
    ):
        try:
            res = await db.execute(
                f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < NOW()"
            )
            if isinstance(res, str):
                parts = res.split()
                if parts and parts[-1].isdigit():
                    counts[table] = int(parts[-1])
        except Exception as exc:
            logger.debug("delete_expired %s: %s", table, exc)
    return counts


async def _delete_expired_trajectories(db: Any) -> int:
    """Delete JSONL trajectory files whose ``session_trajectories.expires_at``
    has passed. The row stays — it just points to a deleted file.
    """
    deleted = 0
    try:
        rows = await db.fetch(
            "SELECT session_id, path FROM session_trajectories "
            "WHERE expires_at IS NOT NULL AND expires_at < NOW()"
        )
    except Exception as exc:
        logger.debug("fetch expired trajectories: %s", exc)
        return 0
    for row in rows or []:
        path_str = row.get("path") if isinstance(row, dict) else row[1]
        session_id = row.get("session_id") if isinstance(row, dict) else row[0]
        if not path_str:
            continue
        try:
            p = Path(path_str)
            if p.exists():
                p.unlink()
            deleted += 1
        except Exception as exc:
            logger.debug("delete trajectory %s: %s", path_str, exc)
    return deleted


async def run_janitor_once(db: Any) -> dict[str, Any]:
    """Run a single janitor pass. Idempotent.

    Returns a small dict with counts for the run log / OTel span.
    """
    if db is None:
        return {"skipped": True, "reason": "no db"}
    ttls = _env_ttls()
    stamped = await _expire_unset_rows(db, ttls)
    counts = await _delete_expired_rows(db)
    traj_deleted = await _delete_expired_trajectories(db)
    return {
        "stamped_unset": stamped,
        "deleted_by_table": counts,
        "trajectories_deleted": traj_deleted,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_periodic(db: Any, interval_seconds: int = 24 * 3600) -> None:
    """Background task. Sleeps ``interval_seconds`` between passes.

    Catches every exception and logs; never exits the loop.
    """
    while True:
        try:
            result = await run_janitor_once(db)
            logger.info("artifact janitor: %s", result)
        except Exception as exc:
            logger.warning("artifact janitor pass failed: %s", exc)
        await asyncio.sleep(interval_seconds)
