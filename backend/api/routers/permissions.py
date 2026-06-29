from __future__ import annotations

import json
import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("/allowlist")
async def list_allowlist():
    """List all permanently allowed tool patterns."""
    from harness.permissions.manager import _permanent_approved, _lock
    with _lock:
        patterns = sorted(_permanent_approved)
    return {"patterns": patterns}


@router.delete("/allowlist/{pattern_key:path}")
async def revoke_allowlist_entry(pattern_key: str):
    """Revoke a single permanently allowed pattern."""
    from harness.permissions.manager import _permanent_approved, _lock, _persist_permanent_allowlist
    pattern_key = pattern_key.strip()
    with _lock:
        removed = pattern_key in _permanent_approved
        _permanent_approved.discard(pattern_key)
    if removed:
        await _persist_permanent_allowlist()
    return {"status": "removed" if removed else "not_found", "pattern": pattern_key}


@router.get("/pending")
async def get_pending_approvals(request: Request):
    """Return all pending tool approval requests."""
    agent = getattr(request.app.state, "agent", None)
    if not agent:
        return {"pending": []}
    perms = getattr(agent, "_deps", None) or getattr(agent, "permissions", None)
    if not perms:
        return {"pending": []}
    try:
        pending = perms.pending_approvals()
        return {"pending": [
            {
                "id": p.get("id", ""),
                "tool": p.get("tool", ""),
                "args": p.get("args", {}),
                "mode": p.get("mode", ""),
            }
            for p in (pending if isinstance(pending, list) else [])
        ]}
    except Exception:
        return {"pending": []}


@router.post("/allowlist/clear")
async def clear_allowlist():
    """Clear all permanently allowed patterns."""
    from harness.permissions.manager import _permanent_approved, _lock, _persist_permanent_allowlist
    with _lock:
        count = len(_permanent_approved)
        _permanent_approved.clear()
    await _persist_permanent_allowlist()
    return {"status": "cleared", "count": count}


class ToolPermissionUpdate(BaseModel):
    tool_name: str
    level: str  # "allow", "ask", "deny"


@router.get("/tools")
async def list_tool_permissions(request: Request):
    """List all tools with their permission levels, merged with user overrides."""
    db = get_db(request)
    try:
        overrides = await db.fetch("SELECT tool_name, level FROM tool_permissions")
    except Exception:
        overrides = []
    override_map = {r["tool_name"]: r["level"] for r in overrides}

    from harness.tools.registry import registry
    tools = []
    for entry in registry.list_entries():
        name = entry.name
        default = getattr(entry, "default_level", "ask") or "ask"
        level = override_map.get(name, default)
        spec = entry.spec or {}
        desc = spec.get("description", "") if isinstance(spec, dict) else ""
        tools.append({
            "name": name,
            "level": level,
            "default": default,
            "description": (desc or "")[:120],
        })
    return {"tools": sorted(tools, key=lambda t: t["name"])}


@router.post("/tools")
async def update_tool_permission(request: Request, body: ToolPermissionUpdate):
    """Update permission level for a specific tool."""
    db = get_db(request)
    if body.level not in ("allow", "ask", "deny"):
        return {"error": "Level must be 'allow', 'ask', or 'deny'"}
    try:
        await db.execute(
            "INSERT INTO tool_permissions (tool_name, level, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (tool_name) DO UPDATE SET level = EXCLUDED.level, updated_at = NOW()",
            body.tool_name, body.level,
        )
    except Exception as exc:
        return {"error": f"Failed to update permission: {exc}"}
    return {"status": "ok", "tool": body.tool_name, "level": body.level}
