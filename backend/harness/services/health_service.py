"""Health service — system health checks (DB, queues, containers)."""

from __future__ import annotations

from typing import Any

from harness.memory.database import Database


class HealthService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_system_health(self) -> dict[str, Any]:
        status: dict[str, Any] = {"database": "unknown", "queues": {}, "containers": {}, "services": {}}
        try:
            await self.db.fetchval("SELECT 1")
            status["database"] = "healthy"
        except Exception:
            status["database"] = "unreachable"
        try:
            row = await self.db.fetchrow("SELECT COUNT(*) as pending FROM tasks WHERE status = 'pending'")
            status["queues"]["pending_tasks"] = row["pending"] if row else 0
        except Exception:
            status["queues"]["pending_tasks"] = 0
        try:
            row = await self.db.fetchrow("SELECT COUNT(*) as active FROM sessions WHERE status = 'running'")
            status["queues"]["active_sessions"] = row["active"] if row else 0
        except Exception:
            status["queues"]["active_sessions"] = 0
        try:
            recent = await self.db.fetchrow(
                "SELECT COUNT(*) as total, SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed "
                "FROM pipeline_runs WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
            if recent:
                total = recent["total"] or 0
                failed = recent["failed"] or 0
                status["queues"]["pipelines_24h"] = total
                status["queues"]["pipeline_failures_24h"] = failed
                status["queues"]["pipeline_health"] = (
                    "healthy" if failed == 0
                    else "degraded" if failed / max(total, 1) < 0.3
                    else "unhealthy"
                )
        except Exception:
            pass
        from harness.tools.delegate_task import active_subagents
        status["queues"]["active_subagents"] = len(active_subagents())
        return status
