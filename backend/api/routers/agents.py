"""Agent management API — CRUD + versioning for configurable agent definitions.

Filesystem-first (agent_workspace/agents/). DB-synced on demand via /sync.
Every PUT auto-snapshots the previous config to the agent_versions table.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from harness.agent_config import AgentConfig, AgentStore
from harness.memory import db_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])
store = AgentStore()


class AgentBody(BaseModel):
    name: str
    description: str = ""
    model: str = ""
    tools: list[str] = []
    skills: list[str] = []
    triggers: list[str] = []
    mode: str = "subagent"
    prompt: str = ""
    color: str = ""
    temperature: float = 0.3
    max_steps: int = 20
    disabled: bool = False
    toolsets: list[str] = []
    version_message: str = ""


@router.get("")
async def list_agents():
    agents = store.list_agents()
    return {"agents": [a.to_dict() for a in agents]}


@router.get("/{name}")
async def get_agent(name: str):
    agent = store.get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return {"agent": agent.to_dict()}


async def _save_version_snapshot(db: Any, name: str, agent: AgentConfig, message: str = "") -> None:
    """Snapshot the current agent config before overwriting it."""
    if not db or not hasattr(db, "fetchval"):
        return
    try:
        next_ver = await db.fetchval(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM agent_versions WHERE agent_name = $1",
            name,
        )
        await db.execute(
            "INSERT INTO agent_versions (agent_name, version, snapshot_json, message) "
            "VALUES ($1, $2, $3::jsonb, $4)",
            name, next_ver, agent.to_markdown(), message or f"v{next_ver}",
        )
    except Exception as exc:
        logger.warning("Failed to save agent version snapshot: %s", exc)


@router.put("/{name}")
async def create_or_update_agent(request: Request, name: str, body: AgentBody):
    existing = store.get_agent(name)

    agent = AgentConfig(
        name=name,
        description=body.description,
        model=body.model,
        tools=body.tools,
        skills=body.skills,
        triggers=body.triggers,
        mode=body.mode,
        prompt=body.prompt,
        color=body.color,
        temperature=body.temperature,
        max_steps=body.max_steps,
        disabled=body.disabled,
        toolsets=body.toolsets,
    )

    # Snapshot existing version before overwriting
    if existing:
        db = None
        try:
            from ..deps import get_db
            db = get_db(request)
        except Exception:
            pass
        if db:
            await _save_version_snapshot(db, name, existing, body.version_message)

    store.save_agent(agent)
    return {"status": "saved", "agent": agent.to_dict()}


@router.delete("/{name}")
async def delete_agent(name: str):
    ok = store.delete_agent(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return {"status": "deleted", "name": name}


@router.post("/{name}/reset")
async def reset_defaults():
    store._seed_defaults()
    return {"status": "seeded"}


@router.post("/sync")
async def sync_to_db():
    db = db_context.get_db()
    if not db:
        return {"synced": 0, "error": "Database not connected"}
    from harness.store.adapters.postgres import PostgresAgentStore
    agent_store = PostgresAgentStore(db)
    count = await store.sync_to_db(agent_store)
    return {"synced": count}


@router.get("/triggers/{goal}")
async def resolve_by_trigger(goal: str):
    agents = store.resolve_by_triggers(goal)
    return {"matched": [a.to_dict() for a in agents]}


# ── Version history ──────────────────────────────────────────────────


@router.get("/{name}/versions")
async def list_agent_versions(request: Request, name: str):
    """List all saved versions for an agent."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass
    if not db or not hasattr(db, "fetch"):
        return {"versions": []}

    try:
        rows = await db.fetch(
            "SELECT id, version, message, created_at FROM agent_versions "
            "WHERE agent_name = $1 ORDER BY version DESC LIMIT 50",
            name,
        )
        return {"versions": [dict(r) for r in rows]}
    except Exception as exc:
        logger.warning("list_agent_versions failed: %s", exc)
        return {"versions": []}


@router.get("/{name}/versions/{version}")
async def get_agent_version(request: Request, name: str, version: int):
    """Get a specific version's snapshot."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass
    if not db or not hasattr(db, "fetchrow"):
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db.fetchrow(
        "SELECT id, version, snapshot_json, message, created_at FROM agent_versions "
        "WHERE agent_name = $1 AND version = $2",
        name, version,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Version {version} not found for agent '{name}'")

    return {"version": dict(row)}


@router.post("/{name}/restore/{version}")
async def restore_agent_version(request: Request, name: str, version: int):
    """Restore an agent to a previous version's configuration."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass
    if not db or not hasattr(db, "fetchrow"):
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db.fetchrow(
        "SELECT snapshot_json FROM agent_versions "
        "WHERE agent_name = $1 AND version = $2",
        name, version,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    snapshot = row["snapshot_json"]
    if isinstance(snapshot, str):
        snapshot = snapshot

    # Snapshot current before restoring
    current = store.get_agent(name)
    if current:
        await _save_version_snapshot(db, name, current, f"before restore to v{version}")

    restored = AgentConfig.from_markdown(snapshot)
    store.save_agent(restored)
    return {"status": "restored", "version": version, "agent": restored.to_dict()}


@router.get("/{name}/diff")
async def diff_agent_versions(request: Request, name: str, v1: int, v2: int):
    """Get a diff between two versions."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass
    if not db or not hasattr(db, "fetch"):
        raise HTTPException(status_code=503, detail="Database not available")

    rows = await db.fetch(
        "SELECT version, snapshot_json FROM agent_versions "
        "WHERE agent_name = $1 AND version IN ($2, $3) ORDER BY version",
        name, v1, v2,
    )
    if len(rows) != 2:
        raise HTTPException(status_code=404, detail=f"Could not find both versions v{v1} and v{v2}")

    from harness.agent_config import AgentConfig as AC
    cfgs = [AC.from_markdown(r["snapshot_json"]) for r in rows]

    diffs = {}
    fields = ["model", "tools", "skills", "triggers", "prompt", "temperature", "max_steps", "toolsets", "delegation_depth", "delegation_role"]
    for field in fields:
        old_val = getattr(cfgs[0], field)
        new_val = getattr(cfgs[1], field)
        if old_val != new_val:
            diffs[field] = {"old": old_val, "new": new_val}

    return {"agent": name, "v1": v1, "v2": v2, "diffs": diffs}
