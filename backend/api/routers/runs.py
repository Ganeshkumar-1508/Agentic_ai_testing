import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/api", tags=["runs"])


class CoverageReportRequest(BaseModel):
    run_id: str = ""
    language: str = "python"
    framework: str = "pytest"
    line_coverage: float = 0.0
    branch_coverage: float = 0.0
    total_lines: int = 0
    covered_lines: int = 0
    report_data: str = ""


@router.get("/runs")
async def get_runs(request: Request, limit: int = 50, offset: int = 0):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit, offset,
    )
    return {
        "runs": [
            _serialize_run(r)
            for r in rows
        ]
    }


def _serialize_run(r):
    inputs = _parse_inputs(r)
    return {
        "id": r["id"],
        "workflowId": r["workflow_id"] or "",
        "repoUrl": inputs.get("repo_url") or None,
        "repoProvider": inputs.get("repo_provider") or None,
        "branch": inputs.get("branch") or None,
        "status": r["status"],
        "testCount": r.get("test_count") or 0,
        "passedCount": r.get("passed_count") or 0,
        "failedCount": r.get("failed_count") or 0,
        "skippedCount": r.get("skipped_count") or 0,
        "duration": r.get("duration") or 0,
        "cost": r.get("cost_usd") or 0,
        "tokens": r.get("token_count") or 0,
        "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
        "completedAt": r["completed_at"].isoformat() if r["completed_at"] else None,
        "requirements": inputs.get("requirements"),
        "techStack": inputs.get("tech_stack") or None,
        "mode": inputs.get("mode") or "",
    }


def _parse_inputs(row) -> dict:
    raw = row.get("inputs")
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM pipeline_runs WHERE id = $1", run_id)
    from_session = False
    if not row:
        # Fall back to sessions table — pipeline runs created via
        # Pipeline runs write to sessions, not pipeline_runs
        # (the legacy /api/agent/run?mode=pipeline and
        # /api/pipeline/from-requirements endpoints that
        # produced these sessions have been hard-deleted in
        # C08 Q7 step 2; new runs go through /api/jobs).
        row = await db.fetchrow("SELECT * FROM sessions WHERE id = $1", run_id)
        from_session = True
    if not row:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Run not found"})

    if from_session:
        serialized = {
            "id": row["id"],
            "workflowId": "",
            "repoUrl": row.get("repo_url") or None,
            "repoProvider": None,
            "branch": None,
            "status": row["status"],
            "testCount": 0,
            "passedCount": 0,
            "failedCount": 0,
            "skippedCount": 0,
            "duration": 0,
            "cost": float(row.get("total_cost") or 0),
            "tokens": row.get("total_tokens") or 0,
            "createdAt": (row.get("created_at") or row.get("started_at")).isoformat() if row.get("created_at") or row.get("started_at") else "",
            "completedAt": row.get("ended_at").isoformat() if row.get("ended_at") else None,
            "requirements": row.get("goal") or "",
            "techStack": None,
            "mode": "pipeline",
        }
        return {
            "run": {
                **serialized,
                "repos": [row.get("repo_url")] if row.get("repo_url") else [],
                "multiRepo": False,
                "framework": "",
                "techStack": None,
                "aiPatterns": None,
                "researchReport": None,
                "logDirPath": None,
            },
            "logs": [],
            "events": [],
        }

    inputs = _parse_inputs(row)

    serialized = _serialize_run(row)
    serialized["costUsd"] = row.get("cost_usd") or 0
    serialized["budgetCap"] = row.get("budget_cap") or 5.00
    serialized["tokenCount"] = row.get("token_count") or 0
    serialized["tokenPrompt"] = row.get("token_prompt") or 0
    serialized["tokenCompletion"] = row.get("token_completion") or 0

    # Keep detailed fields from original response
    return {
        "run": {
            **serialized,
            "repos": inputs.get("repos") or [],
            "multiRepo": inputs.get("multi_repo", False),
            "framework": inputs.get("framework", ""),
            "techStack": None,
            "aiPatterns": None,
            "researchReport": None,
            "logDirPath": None,
        },
        "logs": [],
        "events": [],
    }


@router.get("/runs/{run_id}/test-results")
async def get_run_test_results(request: Request, run_id: str):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT test_name, status, duration_ms, error, retry_count, healed_by_agent, is_quarantined, flaky_score, created_at "
        "FROM test_results WHERE run_id = $1 ORDER BY created_at ASC",
        run_id,
    )
    return {
        "tests": [
            {
                "testName": r["test_name"],
                "status": r["status"],
                "durationMs": r["duration_ms"],
                "error": r["error"],
                "retryCount": r["retry_count"],
                "healedByAgent": r["healed_by_agent"],
                "isQuarantined": r["is_quarantined"],
                "flakyScore": r["flaky_score"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
            }
            for r in rows
        ]
    }


@router.get("/tests/slowest")
async def get_slowest_tests(request: Request, limit: int = 10, days: int = 30):
    """Top N slowest tests by average duration across recent runs."""
    db = get_db(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await db.fetch(
        """SELECT test_name,
                  COUNT(*) as run_count,
                  COALESCE(AVG(duration_ms), 0) as avg_duration,
                  COALESCE(MAX(duration_ms), 0) as max_duration,
                  SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as total_passed,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as total_failed
           FROM test_results
           WHERE created_at >= $1
           GROUP BY test_name
           ORDER BY avg_duration DESC
           LIMIT $2""",
        since, limit,
    )
    return {
        "tests": [
            {
                "testName": r["test_name"],
                "runCount": r["run_count"],
                "avgDurationMs": round(r["avg_duration"], 0),
                "maxDurationMs": r["max_duration"],
                "passRate": round((r["total_passed"] / max(r["run_count"], 1)) * 100, 1),
                "totalPassed": r["total_passed"],
                "totalFailed": r["total_failed"],
            }
            for r in rows
        ]
    }


@router.get("/tests/owner")
async def get_test_owner(request: Request, test_name: str = "", repo_url: str = ""):
    """Get the owning team for a test name based on CODEOWNERS patterns."""
    db = get_db(request)
    from harness.codeowners_parser import get_owner_for_test
    owner = await get_owner_for_test(db, test_name, repo_url)
    return {"testName": test_name, "owner": owner}


@router.get("/tests/owners/batch")
async def get_batch_owners(request: Request, repo_url: str = ""):
    """Get all stored test_owner patterns for a repo for client-side matching."""
    db = get_db(request)
    rows = await db.fetch(
        "SELECT team_name, pattern FROM test_owners WHERE repo_url = $1 ORDER BY updated_at ASC",
        repo_url,
    )
    return {
        "repoUrl": repo_url,
        "patterns": [{"teamName": r["team_name"], "pattern": r["pattern"]} for r in rows],
    }


@router.get("/runs/{run_id}/impact-summary")
async def get_run_impact_summary(request: Request, run_id: str):
    """Get test impact analysis for a run — which tests were affected by changes."""
    db = get_db(request)
    row = await db.fetchrow("SELECT impact_summary FROM pipeline_runs WHERE id = $1", run_id)
    if not row or not row["impact_summary"]:
        return {"available": False}
    return json.loads(row["impact_summary"])


@router.get("/stream/recent")
async def get_recent_stream_events(request: Request, limit: int = 50):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT pe.event_type, pe.event_data, pe.created_at, pr.inputs "
        "FROM pipeline_events pe "
        "LEFT JOIN pipeline_runs pr ON pe.run_id = pr.id "
        "ORDER BY pe.created_at DESC LIMIT $1",
        limit,
    )
    return {
        "events": [
            {
                "type": r["event_type"],
                "data": json.loads(r["event_data"]) if isinstance(r["event_data"], str) else r.get("event_data", {}),
                "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
                "runHint": _parse_inputs(r).get("requirements", "")[:80] if r.get("inputs") else "",
            }
            for r in rows
        ]
    }


@router.get("/runs/{run_id}/events")
async def get_run_events(request: Request, run_id: str, limit: int = 5000):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT event_type, event_data, created_at FROM pipeline_events "
        "WHERE run_id = $1 ORDER BY created_at ASC LIMIT $2",
        run_id, limit,
    )
    return {
        "events": [
            {
                "type": r["event_type"],
                "data": json.loads(r["event_data"]) if isinstance(r["event_data"], str) else r.get("event_data", {}),
                "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
            }
            for r in rows
        ]
    }


@router.get("/runs/{run_id}/trace-events")
async def get_run_trace_events(request: Request, run_id: str, limit: int = 200):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT id, event_type, event_data, parent_id, created_at "
        "FROM trace_events WHERE run_id = $1 ORDER BY created_at ASC LIMIT $2",
        run_id, limit,
    )
    return {
        "events": [
            {
                "id": r["id"],
                "eventType": r["event_type"],
                "eventData": r["event_data"],
                "parentId": r["parent_id"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
            }
            for r in rows
        ]
    }


@router.get("/sessions/search")
async def search_sessions(request: Request, q: str = "", limit: int = 20):
    db = get_db(request)
    query = "SELECT id, status, source, goal, repo_url, agent_role, depth, model, provider, estimated_cost_usd, ended_at, end_reason, created_at, updated_at FROM sessions"
    if q:
        like = f"%{q}%"
        rows = await db.fetch(f"{query} WHERE (goal ILIKE $1 OR id ILIKE $1 OR repo_url ILIKE $1) ORDER BY created_at DESC LIMIT $2", like, limit)
    else:
        rows = await db.fetch(f"{query} ORDER BY created_at DESC LIMIT $1", limit)
    return {"sessions": [{"session_id": r["id"], "id": r["id"], "status": r["status"], "source": r.get("source") or "chat", "goal": (r.get("goal") or "")[:200], "repo_url": r.get("repo_url") or "", "created_at": r["created_at"].isoformat() if r["created_at"] else ""} for r in rows]}


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 20, source: str | None = None):
    db = get_db(request)
    query = "SELECT id, status, source, goal, repo_url, agent_role, depth, model, provider, estimated_cost_usd, ended_at, end_reason, created_at, updated_at FROM sessions"
    if source:
        rows = await db.fetch(f"{query} WHERE source = $1 ORDER BY created_at DESC LIMIT $2", source, limit)
    else:
        rows = await db.fetch(f"{query} ORDER BY created_at DESC LIMIT $1", limit)

    # Enrich pipeline sessions with test counts from pipeline_runs
    session_ids = [r["id"] for r in rows]
    test_counts: dict[str, dict] = {}
    token_counts: dict[str, dict] = {}
    if session_ids:
        try:
            tc_rows = await db.fetch(
                "SELECT session_id, test_count, passed_count, failed_count, skipped_count "
                "FROM pipeline_runs WHERE session_id = ANY($1)",
                session_ids,
            )
            for tc in tc_rows:
                test_counts[tc["session_id"]] = {
                    "test_count": tc.get("test_count") or 0,
                    "passed_count": tc.get("passed_count") or 0,
                    "failed_count": tc.get("failed_count") or 0,
                    "skipped_count": tc.get("skipped_count") or 0,
                }
        except Exception:
            pass

        try:
            tu_rows = await db.fetch(
                "SELECT session_id, SUM(input_tokens) as inp, SUM(output_tokens) as out, "
                "SUM(estimated_cost_usd) as cost FROM token_usage "
                "WHERE session_id = ANY($1) GROUP BY session_id",
                session_ids,
            )
            for tu in tu_rows:
                token_counts[tu["session_id"]] = {
                    "tokens": (tu.get("inp") or 0) + (tu.get("out") or 0),
                    "cost": float(tu.get("cost") or 0),
                }
        except Exception:
            pass

    return {"sessions": [
        {
            "session_id": r["id"],
            "id": r["id"],
            "status": r["status"],
            "source": r.get("source") or "chat",
            "goal": (r.get("goal") or "")[:200],
            "repo_url": r.get("repo_url") or "",
            "agent_role": r.get("agent_role", ""),
            "depth": r.get("depth", 0),
            "model": r.get("model", ""),
            "cost": token_counts.get(r["id"], {}).get("cost", r.get("estimated_cost_usd", 0)),
            "tokens": token_counts.get(r["id"], {}).get("tokens", 0),
            "ended_at": r["ended_at"].isoformat() if r.get("ended_at") else None,
            "end_reason": r.get("end_reason", ""),
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
            **test_counts.get(r["id"], {}),
        }
        for r in rows
    ]}


@router.get("/sessions/{session_id}/export")
async def export_session(request: Request, session_id: str):
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
    if not row:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    events = await db.fetch("SELECT event_type, event_data, created_at FROM stream_events WHERE session_id = $1 ORDER BY created_at", session_id)
    return {
        "session": dict(row),
        "events": [{"type": r["event_type"], "data": r["event_data"], "created_at": r["created_at"].isoformat() if r["created_at"] else ""} for r in events],
        "exported_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
    if not row:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return {
        "id": row["id"],
        "status": row["status"],
        "source": row.get("source", ""),
        "goal": row.get("goal", ""),
        "agent_role": row.get("agent_role", ""),
        "depth": row.get("depth", 0),
        "model": row.get("model", ""),
        "provider": row.get("provider", ""),
        "estimated_cost_usd": row.get("estimated_cost_usd", 0),
        "total_tokens": row.get("total_tokens", 0),
        "total_cost": row.get("total_cost", 0),
        "created_at": row["created_at"].isoformat() if row["created_at"] else "",
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
        "ended_at": row["ended_at"].isoformat() if row.get("ended_at") else None,
        "end_reason": row.get("end_reason", ""),
    }


@router.get("/sessions/{session_id}/health")
async def get_session_health(request: Request, session_id: str):
    db = get_db(request)
    result: dict[str, Any] = {}

    # Compression stats
    comp = await db.fetchrow(
        "SELECT COUNT(*) as count, COALESCE(SUM(before_tokens), 0) as before_total, "
        "COALESCE(SUM(after_tokens), 0) as after_total "
        "FROM compressions WHERE session_id = $1", session_id,
    )
    if comp:
        before = comp["before_total"] or 0
        after = comp["after_total"] or 0
        result["compressions"] = {
            "count": comp["count"] or 0,
            "tokens_before": before,
            "tokens_after": after,
            "tokens_saved": before - after,
            "ratio": round((before - after) / before * 100, 1) if before > 0 else 0,
        }
    else:
        result["compressions"] = {"count": 0, "tokens_saved": 0, "ratio": 0}

    # L0 artifacts
    l0 = await db.fetchval(
        "SELECT COUNT(*) FROM agent_artifacts WHERE session_id = $1", session_id,
    )
    result["artifacts"] = {"l0_count": l0 or 0}

    # Checkpoints
    ckpt = await db.fetchrow(
        "SELECT COUNT(*) as count, MAX(created_at) as latest "
        "FROM checkpoints WHERE session_id = $1", session_id,
    )
    ckpt_types = await db.fetch(
        "SELECT checkpoint_type, COUNT(*) as cnt FROM checkpoints "
        "WHERE session_id = $1 GROUP BY checkpoint_type ORDER BY cnt DESC",
        session_id,
    )
    result["checkpoints"] = {
        "count": ckpt["count"] if ckpt else 0,
        "latest": ckpt["latest"].isoformat() if ckpt and ckpt["latest"] else None,
        "types": {r["checkpoint_type"]: r["cnt"] for r in ckpt_types} if ckpt_types else {},
    }

    # Token usage summary
    tok = await db.fetchrow(
        "SELECT COUNT(*) as count, COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens, "
        "COALESCE(SUM(estimated_cost_usd), 0) as total_cost "
        "FROM token_usage WHERE session_id = $1", session_id,
    )
    result["token_usage"] = {
        "records": tok["count"] if tok else 0,
        "total_tokens": tok["total_tokens"] if tok else 0,
        "total_cost": round(tok["total_cost"], 6) if tok else 0,
    }

    return result


@router.get("/sessions/{session_id}/events")
async def get_session_events(request: Request, session_id: str, limit: int = 100):
    """Get stream events for a session."""
    db = get_db(request)
    rows = await db.fetch(
        "SELECT id, event_type, event_data, created_at FROM stream_events WHERE session_id = $1 ORDER BY id DESC LIMIT $2",
        session_id, limit,
    )
    return {"events": [
        {
            "id": r["id"],
            "type": r["event_type"],
            "payload": json.loads(r["event_data"]) if isinstance(r["event_data"], str) else r["event_data"],
            "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
        }
        for r in rows
    ]}


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(request: Request, session_id: str, limit: int = 500):
    """Get structured timeline spans for a session — paired start/completed events with durations."""
    db = get_db(request)
    rows = await db.fetch(
        "SELECT id, event_type, event_data, created_at FROM stream_events "
        "WHERE session_id = $1 ORDER BY id ASC LIMIT $2",
        session_id, limit,
    )

    START_EVENTS = {"tool.execution.started", "ToolExecutionStarted", "RoundStarted", "LLMCallStarted",
                    "TokenGenerated", "subagent.spawned"}
    END_EVENTS = {"tool.execution.completed", "ToolExecutionCompleted", "RoundCompleted", "LLMCallCompleted",
                  "subagent.completed", "subagent.failed", "subagent.heartbeat"}

    pair_map: dict[str, dict] = {}
    spans: list[dict] = []

    for r in rows:
        ev_type = r["event_type"]
        payload = json.loads(r["event_data"]) if isinstance(r["event_data"], str) else (r["event_data"] or {})
        ts = r["created_at"].isoformat() if r["created_at"] else ""
        ts_epoch = r["created_at"].timestamp() if r["created_at"] else 0

        if ev_type in START_EVENTS:
            key = f"{ev_type}-{payload.get('call_id') or payload.get('round') or payload.get('subagent_id') or id(r)}"
            pair_map[key] = {"type": ev_type, "label": ev_type.replace(".", " ").title(), "started_at": ts, "ts": ts_epoch,
                             "payload": payload, "id": r["id"]}

        elif ev_type in END_EVENTS and payload.get("call_id"):
            key = f"{ev_type.replace('completed','started').replace('Completed','Started')}-{payload['call_id']}"
            start = pair_map.pop(key, None)
            dur = round((ts_epoch - start["ts"]) * 1000) if start else 0
            if start:
                spans.append({"type": "tool_call", "label": payload.get("tool_name", start["label"]),
                              "started_at": start["started_at"], "duration_ms": max(dur, 1),
                              "cost_usd": round(float(payload.get("cost_usd", 0)), 6), "status": payload.get("success", True),
                              "tokens": payload.get("prompt_tokens", 0) + payload.get("completion_tokens", 0)})

        elif ev_type in ("assistant_message",) and payload.get("content"):
            spans.append({"type": "llm_response", "label": "LLM Response",
                          "started_at": ts, "duration_ms": 0,
                          "cost_usd": round(float(payload.get("cost_usd", 0)), 6),
                          "status": "completed", "tokens": 0,
                          "preview": (payload.get("content") or "")[:200]})

        elif ev_type in ("user_message",) and payload.get("content"):
            spans.append({"type": "user", "label": "User",
                          "started_at": ts, "duration_ms": 0,
                          "cost_usd": 0, "status": "completed", "tokens": 0,
                          "preview": (payload.get("content") or "")[:200]})

    # Flush remaining unmatched start events as running spans
    for key, start in pair_map.items():
        dur = round((__import__("time").time() - start["ts"]) * 1000) if start["ts"] else 0
        spans.append({"type": "running", "label": start["label"],
                      "started_at": start["started_at"], "duration_ms": dur,
                      "cost_usd": 0, "status": "running", "tokens": 0})

    # Fetch token usage for the session
    token_rows = await db.fetch(
        "SELECT timestamp, input_tokens, output_tokens, estimated_cost_usd, model "
        "FROM token_usage WHERE session_id = $1 ORDER BY timestamp ASC", session_id,
    )

    return {"spans": sorted(spans, key=lambda s: s["started_at"]),
            "token_usage": [{"timestamp": r["timestamp"].isoformat() if r["timestamp"] else "",
                             "tokens": (r["input_tokens"] or 0) + (r["output_tokens"] or 0),
                             "cost_usd": round(float(r["estimated_cost_usd"] or 0), 6),
                             "model": r.get("model", "")} for r in token_rows]}


@router.post("/sessions/cleanup")
async def cleanup_sessions(request: Request, body: dict | None = None):
    """Delete sessions older than N days. Body: {older_than_days: int}"""
    db = get_db(request)
    days = (body or {}).get("older_than_days", 30)
    try:
        rows = await db.fetch("SELECT id FROM sessions WHERE created_at < NOW() - INTERVAL '1 day' * $1", days)
        ids = [r["id"] for r in rows]
        for sid in ids:
            await db.execute("DELETE FROM stream_events WHERE session_id = $1", sid)
            await db.execute("DELETE FROM token_usage WHERE session_id = $1", sid)
        result = await db.execute("DELETE FROM sessions WHERE id = ANY($1)", ids)
        return {"status": "ok", "deleted": len(ids)}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    """Delete a session and its associated data."""
    db = get_db(request)
    try:
        await db.execute("DELETE FROM stream_events WHERE session_id = $1", session_id)
        await db.execute("DELETE FROM token_usage WHERE session_id = $1", session_id)
        await db.execute("DELETE FROM trace_events WHERE run_id = $1", session_id)
        await db.execute("DELETE FROM sessions WHERE id = $1", session_id)
        return {"status": "ok", "session_id": session_id}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/dashboard/stats")
async def get_dashboard_stats(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT status, COUNT(*) as cnt FROM pipeline_runs GROUP BY status")
    total = sum(r["cnt"] for r in rows)
    passed = next((r["cnt"] for r in rows if r["status"] == "completed"), 0)
    failed = next((r["cnt"] for r in rows if r["status"] == "failed"), 0)
    pending = sum(r["cnt"] for r in rows if r["status"] in ("pending", "running"))

    artifact_rows = await db.fetch("SELECT artifacts FROM pipeline_runs WHERE artifacts IS NOT NULL")
    by_type: dict[str, int] = {}
    for r in artifact_rows:
        try:
            artifacts = json.loads(r["artifacts"])
            for a in artifacts:
                t = a.get("type", "unknown")
                by_type[t] = by_type.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

    recent = await db.fetch(
        "SELECT id, status, created_at, completed_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 5"
    )
    recent_runs = [
        {
            "id": r["id"],
            "name": f"Pipeline Run {r['id'][:8]}",
            "status": r["status"],
            "duration": int((r["completed_at"] - r["created_at"]).total_seconds() * 1000) if r["completed_at"] and r["created_at"] else 0,
            "executedAt": (r["completed_at"] or r["created_at"]).isoformat() if r["created_at"] else "",
        }
        for r in recent
    ]

    pass_rate = (passed / total * 100) if total > 0 else 0

    return {
        "stats": {
            "totalTests": total,
            "passed": passed,
            "failed": failed,
            "pending": pending,
            "passRate": round(pass_rate, 1),
            "byType": [{"type": t, "count": c} for t, c in by_type.items()],
        },
        "recentTestRuns": recent_runs,
        "recentTestCases": [],
        "activeAgents": 0,
    }


@router.post("/tests/coverage")
async def save_coverage_report(request: Request, req: CoverageReportRequest):
    db = get_db(request)
    row = await db.fetchrow(
        "INSERT INTO coverage_reports (run_id, language, framework, line_coverage, branch_coverage, total_lines, covered_lines, report_data) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
        req.run_id, req.language, req.framework, req.line_coverage, req.branch_coverage,
        req.total_lines, req.covered_lines, req.report_data,
    )
    return {"status": "ok", "report_id": row["id"]}


class CostUpdateRequest(BaseModel):
    cost_usd: float = 0
    token_count: int = 0
    token_prompt: int = 0
    token_completion: int = 0


@router.post("/runs/{run_id}/cost")
async def update_run_cost(request: Request, run_id: str, body: CostUpdateRequest):
    db = get_db(request)
    await db.execute(
        "UPDATE pipeline_runs SET cost_usd = cost_usd + $1, token_count = token_count + $2, "
        "token_prompt = token_prompt + $3, token_completion = token_completion + $4 WHERE id = $5",
        body.cost_usd, body.token_count, body.token_prompt, body.token_completion, run_id,
    )
    return {"status": "ok"}


class BatchRerunRequest(BaseModel):
    test_names: list[str]
    requirements: str | None = None


class MultiRepoRunRequest(BaseModel):
    repos: list[str]
    branch: str = "main"
    requirements: str = ""
    mode: str = "auto"


async def create_run_internal(
    requirements: str = "",
    repos: list[str] | None = None,
    repo_url: str = "",
    branch: str = "main",
    mode: str = "auto",
) -> str:
    """Create a run row and return its ID. Used by both the REST API and webhook handlers."""
    import uuid
    from ..deps import get_db
    from fastapi import Request
    # This is called from both HTTP handlers and background tasks.
    # When called from a background task without a request context,
    # we use a direct DB helper.
    run_id = str(uuid.uuid4())
    inputs = {
        "requirements": requirements,
        "mode": mode,
        "branch": branch,
    }
    if repos:
        inputs["repos"] = repos
        inputs["multi_repo"] = True
    if repo_url:
        inputs["repo_url"] = repo_url
        # Infer provider from URL if needed
        if "gitlab" in repo_url.lower():
            inputs["repo_provider"] = "gitlab"
        elif "bitbucket" in repo_url.lower():
            inputs["repo_provider"] = "bitbucket"
        else:
            inputs["repo_provider"] = "github"

    try:
        from harness.db_helpers import get_db_direct
        db = await get_db_direct()
        await db.execute(
            "INSERT INTO pipeline_runs (id, workflow_id, status, inputs) VALUES ($1, $2, $3, $4)",
            run_id, f"run-{mode}", "pending", json.dumps(inputs),
        )
    except Exception:
        pass
    return run_id


@router.post("/runs/multi-repo")
async def create_multi_repo_run(request: Request, body: MultiRepoRunRequest):
    """Create a run that spans multiple repositories."""
    import uuid
    run_id = str(uuid.uuid4())
    db = get_db(request)
    inputs = {
        "requirements": body.requirements,
        "repos": body.repos,
        "branch": body.branch,
        "mode": body.mode,
        "multi_repo": True,
    }
    await db.execute(
        "INSERT INTO pipeline_runs (id, workflow_id, status, inputs) VALUES ($1, $2, $3, $4)",
        run_id, f"multi-{len(body.repos)}", "pending", json.dumps(inputs),
    )
    return {"run_id": run_id, "repo_count": len(body.repos), "repos": body.repos}


@router.post("/runs/{run_id}/rerun")
async def batch_rerun(request: Request, run_id: str, body: BatchRerunRequest):
    """Create a new run that re-runs only the selected tests from a previous run."""
    db = get_db(request)
    original = await db.fetchrow("SELECT inputs FROM pipeline_runs WHERE id = $1", run_id)
    if not original:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Original run not found"})

    import uuid
    new_id = str(uuid.uuid4())
    req_text = body.requirements or "Re-run selected tests"
    inputs = {"requirements": req_text, "rerun_of": run_id, "selected_tests": body.test_names}
    await db.execute(
        "INSERT INTO pipeline_runs (id, workflow_id, status, inputs) VALUES ($1, $2, $3, $4)",
        new_id, f"rerun-{run_id}", "pending", json.dumps(inputs),
    )
    return {"run_id": new_id, "status": "created"}


@router.get("/coverage/history")
async def get_coverage_history(request: Request, limit: int = 20):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT * FROM coverage_reports ORDER BY created_at DESC LIMIT $1", limit,
    )
    return {"reports": [
        {
            "id": r["id"],
            "runId": r["run_id"],
            "language": r["language"],
            "framework": r["framework"],
            "lineCoverage": round(r["line_coverage"], 1),
            "branchCoverage": round(r["branch_coverage"], 1),
            "totalLines": r["total_lines"],
            "coveredLines": r["covered_lines"],
            "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
        }
        for r in rows
    ]}


@router.post("/runs/{run_id}/resume")
async def resume_run(request: Request, run_id: str):
    """Resume a run from its last known state."""
    db = get_db(request)
    run = await db.fetchrow("SELECT * FROM pipeline_runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Re-mark run as running
    await db.execute(
        "UPDATE pipeline_runs SET status = 'running' WHERE id = $1 AND status IN ('pending', 'failed')",
        run_id,
    )

    return {
        "status": "resumed",
        "run_id": run_id,
    }



# Q9-D: failure forensics endpoint. Powers the dashboard's
# "Why did this run fail?" card. Returns the last reasoning,
# last tool calls, any orphan kanban task, and a 1-paragraph
# LLM-generated summary. The summary is best-effort; the rest
# of the payload is always available.
@router.get("/runs/{run_id}/forensics")
async def get_run_forensics(request: Request, run_id: str) -> dict:
    db = get_db(request)
    run_row = await db.fetchrow(
        "SELECT id, session_id, status, state AS output FROM pipeline_runs WHERE id = $1",
        run_id,
    )
    if not run_row:
        # Fall back to sessions table
        run_row = await db.fetchrow(
            "SELECT id, id AS session_id, status, goal AS output FROM sessions WHERE id = $1",
            run_id,
        )
    if not run_row:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        from harness.services.failure_analyzer import summarize_failure
        return await summarize_failure(
            run_id=run_id,
            session_id=run_row["session_id"] or run_id,
            output=run_row["output"] or "",
            db=db,
        )
    except Exception as exc:
        return {
            "run_id": run_id,
            "session_id": run_row["session_id"] or run_id,
            "summary": "",
            "last_reasoning": [],
            "last_tool_calls": [],
            "orphan_kanban_task": None,
            "summary_available": False,
            "error": str(exc),
        }
