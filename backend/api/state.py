from __future__ import annotations

from typing import Any
from harness.memory.database import Database
from harness.trace import DatabaseTraceHandler, get_otel_handler
from harness.context import manager as scope_manager
from harness.api.state import set_agent_factory, get_agent_factory


def enrich_with_scope(data: dict[str, Any]) -> dict[str, Any]:
    scope = scope_manager.current
    if scope is None:
        return data
    enriched = {**data}
    if "pipeline_step" in scope.labels:
        enriched["pipeline_step"] = scope.labels["pipeline_step"]
    enriched["_scope_run_id"] = scope.run_id
    enriched["_scope_session_id"] = scope.session_id
    enriched["_scope_agent_id"] = scope.agent_id
    enriched["_scope_parent_id"] = scope.parent_id
    return enriched


async def trace_handler(event_type: str, data: dict[str, Any], db: Database) -> None:
    enriched = enrich_with_scope(data)
    scope = scope_manager.current
    run_id = enriched.get("_scope_run_id", "unknown")
    agent_id = enriched.get("_scope_agent_id", "")
    parent_id = enriched.get("_scope_parent_id", "")
    db_handler = DatabaseTraceHandler(db, run_id, agent_id, parent_id)
    await db_handler.emit(event_type, enriched)
    otel = get_otel_handler()
    await otel.emit(event_type, enriched)
