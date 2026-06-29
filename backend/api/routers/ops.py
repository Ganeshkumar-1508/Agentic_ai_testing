from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps import get_db
from harness.services.ops_service import OpsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/tools")
async def list_tools(request: Request):
    from harness.tools.registry import registry
    from harness.tools.toolsets import toolsets_for_mode, TOOLSETS

    mode = request.query_params.get("mode", "chat")
    tool_names = toolsets_for_mode(mode)
    entry_by_name = {e.name: e for e in registry.list_entries()}

    tools = []
    used_toolsets: dict[str, int] = {}
    for name in tool_names:
        spec = registry.get_spec(name)
        entry = entry_by_name.get(name)
        if spec:
            fn = spec.get("function", {})
            ts = entry.toolset if entry else "read"
            used_toolsets[ts] = used_toolsets.get(ts, 0) + 1
            tools.append({"name": name, "description": fn.get("description", ""), "toolset": ts})

    toolsets_meta = {}
    for ts_name in used_toolsets:
        ts_def = TOOLSETS.get(ts_name, {})
        toolsets_meta[ts_name] = {"label": ts_name.title(), "description": ts_def.get("description", "")}

    return {"tools": tools, "toolsets": toolsets_meta, "mode": mode, "total": len(tools)}


@router.get("/swarm/active")
async def get_active_subagents(request: Request):
    from harness.tools.delegate_task import active_subagents

    svc = OpsService(get_db(request))
    return {
        "subagents": active_subagents(),
        "active_session": await svc.get_active_session(),
        "tool_calls_total": await svc.get_tool_call_count(),
    }


@router.get("/swarm/delegate-events")
async def get_delegate_events(request: Request, limit: int = 50, run_id: str | None = None):
    svc = OpsService(get_db(request))
    active_session_id = run_id or await svc.get_active_session_id()

    trace_rows = await svc.get_trace_events(
        ["agent.started", "agent.completed", "llmcall.completed", "tool.execution.started", "tool.execution.completed", "round.started", "round.completed"], limit,
    )
    stream_rows = await svc.get_stream_events(active_session_id, limit) if active_session_id else []

    combined = list(trace_rows) + list(stream_rows)
    combined.sort(key=lambda r: r["created_at"] or "", reverse=True)
    combined = combined[:limit]

    return {"events": [svc.format_event(r) for r in combined]}


@router.get("/swarm/summary")
async def get_swarm_summary(request: Request):
    svc = OpsService(get_db(request))
    return await svc.get_swarm_summary()


@router.get("/plugins")
async def list_plugins(request: Request):
    from harness.hooks import discover_plugins, get_hook_registry, PluginManifest
    import yaml
    from pathlib import Path

    reg = get_hook_registry()
    discover_plugins(reg)

    plugins: list[dict[str, Any]] = []
    scanned: set[str] = set()
    sources = [
        ("bundled", Path(__file__).resolve().parent.parent.parent / "plugins"),
        ("user", Path.home() / ".testai" / "plugins"),
        ("project", Path.cwd() / ".testai" / "plugins"),
    ]
    for source_name, source_dir in sources:
        if not source_dir.exists():
            continue
        for child in sorted(source_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")) or child.name in scanned:
                continue
            manifest_file = child / "plugin.yaml"
            if not manifest_file.exists():
                continue
            try:
                manifest_data = yaml.safe_load(manifest_file.read_text("utf-8"))
                if not isinstance(manifest_data, dict):
                    continue
                manifest = PluginManifest(
                    name=manifest_data.get("name", child.name),
                    version=str(manifest_data.get("version", "")),
                    description=str(manifest_data.get("description", "")),
                    author=str(manifest_data.get("author", "")),
                    requires_env=manifest_data.get("requires_env", []),
                    provides_tools=manifest_data.get("provides_tools", []),
                    provides_hooks=manifest_data.get("provides_hooks", []),
                    kind=manifest_data.get("kind", "standalone"),
                    path=str(child),
                )
                plugins.append({
                    "name": manifest.name, "version": manifest.version,
                    "description": manifest.description, "author": manifest.author,
                    "source": source_name, "requires_env": manifest.requires_env,
                    "provides_tools": manifest.provides_tools,
                    "provides_hooks": manifest.provides_hooks,
                    "kind": manifest.kind, "path": manifest.path,
                })
                scanned.add(child.name)
            except Exception as exc:
                logger.warning("Failed to read plugin manifest %s: %s", manifest_file, exc)
    return {"plugins": plugins, "total": len(plugins)}


@router.get("/plugins/hooks")
async def list_hooks(request: Request):
    from harness.hooks import get_hook_registry, VALID_HOOKS

    reg = get_hook_registry()
    CATEGORY_MAP = {
        "pre_llm_call": "Agent Loop", "post_llm_call": "Agent Loop",
        "pre_tool_call": "Agent Loop", "post_tool_call": "Agent Loop",
        "on_session_start": "Agent Loop", "on_session_end": "Agent Loop",
        "transform_llm_output": "Transform", "transform_tool_result": "Transform",
        "transform_terminal_output": "Transform",
        "subagent_stop": "Subagent & Approval", "pre_approval_request": "Subagent & Approval",
        "post_approval_response": "Subagent & Approval",
    }
    categories: dict[str, list] = {}
    for hook_name in sorted(VALID_HOOKS):
        handlers = reg._handlers.get(hook_name, [])
        cat = CATEGORY_MAP.get(hook_name, "Other")
        categories.setdefault(cat, []).append({
            "name": hook_name, "handler_count": len(handlers),
            "handler_names": [getattr(h, "__name__", repr(h)) for h in handlers],
        })
    total_hooks = sum(len(v) for v in categories.values())
    total_handlers = sum(sum(h["handler_count"] for h in handlers) for handlers in categories.values())
    return {"categories": categories, "total_hooks": total_hooks, "total_handlers": total_handlers}


@router.get("/skills/curator-status")
async def get_curator_status(request: Request):
    from harness.curator import (
        _load_usage, _load_state, STALE_AFTER_DAYS, ARCHIVE_AFTER_DAYS, INTERVAL_HOURS,
    )
    from harness.tools.skill_tools import _scan_skills

    usage = _load_usage()
    state = _load_state()
    all_skills = _scan_skills()
    now = datetime.now(timezone.utc)
    active_count = stale_count = archived_count = agent_created = bundled_count = total_uses = 0

    for s in all_skills:
        name = s.get("name", "")
        u = usage.get(name, {})
        state_val = u.get("state", "active")
        created_by = u.get("created_by", "bundled")
        if state_val == "active": active_count += 1
        elif state_val == "stale": stale_count += 1
        elif state_val == "archived": archived_count += 1
        else: active_count += 1
        if created_by == "agent": agent_created += 1
        else: bundled_count += 1
        total_uses += u.get("use_count", 0)

    last_run_at = state.get("last_run_at")
    next_run_hours = 0
    if last_run_at:
        try:
            last_run = datetime.fromisoformat(last_run_at)
            last_run_utc = last_run.replace(tzinfo=timezone.utc) if last_run.tzinfo is None else last_run
            hours_since = (now - last_run_utc).total_seconds() / 3600
            next_run_hours = max(0, INTERVAL_HOURS - hours_since)
        except (ValueError, TypeError):
            pass

    return {
        "total_skills": len(all_skills), "active": active_count, "stale": stale_count,
        "archived": archived_count, "agent_created": agent_created, "bundled": bundled_count,
        "total_uses": total_uses, "pinned_count": sum(1 for u in usage.values() if u.get("pinned")),
        "last_curated_at": state.get("last_run_at"), "interval_hours": INTERVAL_HOURS,
        "stale_after_days": STALE_AFTER_DAYS, "archive_after_days": ARCHIVE_AFTER_DAYS,
        "next_run_hours": round(next_run_hours, 1), "state": state,
    }


@router.post("/skills/curator-run")
async def trigger_curator(request: Request):
    from harness.curator import maybe_run_curator
    result = await maybe_run_curator()
    return {"status": "ok", "result": str(result)}


@router.get("/skills/usage")
async def get_skill_usage(request: Request):
    from harness.curator import _load_usage
    return {"usage": _load_usage()}


@router.get("/governance/config")
async def get_governance_config(request: Request):
    db = get_db(request)
    pending = 0
    high_risk = 0
    try:
        rows = await db.fetch("SELECT count(*) as c FROM kanban_tasks WHERE column_name = 'review' AND needs_review = true")
        pending = rows[0]["c"] if rows else 0
    except Exception:
        pass
    try:
        rows = await db.fetch("SELECT count(*) as c FROM kanban_tasks WHERE column_name = 'blocked' AND failure_count > 2")
        high_risk = rows[0]["c"] if rows else 0
    except Exception:
        pass
    return {"pending_approvals": pending, "high_risk_flaky": high_risk}


@router.get("/governance/spills")
async def list_spills(request: Request, limit: int = 50):
    from harness.memory.store import PersistentStore
    store = PersistentStore(get_db(request))
    spills = await store.list_by_category("tool_spill", limit=limit)
    return {"spills": [
        {"key": s["key"], "session_id": s["key"].split(":", 1)[1] if ":" in s["key"] else "",
         "tool_call_id": s["key"].split(":", 2)[2] if s["key"].count(":") > 1 else "",
         "size_chars": len(s["value"]), "size_kb": round(len(s["value"]) / 1024, 1),
         "preview": s["value"][:200], "created_at": s["created_at"]}
        for s in spills
    ], "total": len(spills)}


@router.get("/governance/spills/{key:path}")
async def get_spill(request: Request, key: str):
    from harness.memory.store import PersistentStore
    store = PersistentStore(get_db(request))
    value = await store.get_value(key)
    if value is None:
        return JSONResponse(status_code=404, content={"error": "Spill not found"})
    return {"key": key, "content": value, "size_chars": len(value)}


@router.get("/pipeline-metrics")
async def list_pipeline_metrics(request: Request, limit: int = 20):
    svc = OpsService(get_db(request))
    return {"metrics": await svc.get_pipeline_metrics(limit)}


@router.get("/agent-delegations")
async def list_agent_delegations(request: Request, session_id: str = "", limit: int = 50):
    svc = OpsService(get_db(request))
    return {"delegations": await svc.get_agent_delegations(session_id, limit)}


@router.get("/sandbox-metrics")
async def list_sandbox_metrics(request: Request, session_id: str = "", limit: int = 20):
    svc = OpsService(get_db(request))
    return {"metrics": await svc.get_sandbox_metrics(session_id, limit)}
