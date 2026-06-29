"""Failure forensics analyzer (Q9-D — failure forensics view).

When a run ends in failure (max-rounds, exception, hard-cap, etc.),
the dashboard surfaces a "Failure Forensics" card with:
  - The LLM's last 3 reasoning steps
  - The last 5 tool calls and their errors
  - The orphaned kanban task (if any)
  - A 1-paragraph "why this probably failed" summary (LLM-generated)

This module produces the LLM summary. The other data (last reasoning,
last tool calls, orphan task) is read directly from the session's
events table + the kanban — see `GET /api/runs/{run_id}/forensics`
in `api/routers/runs.py`.

The summary call is best-effort: a transient LLM failure is logged
and the dashboard falls back to a "no summary available" message.
The forensics endpoint still returns the other data; only the
summary is best-effort.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def summarize_failure(
    *,
    run_id: str,
    session_id: str,
    output: str,
    db: Any,
) -> dict[str, Any]:
    """Build a failure-forensics payload for the dashboard.

    Returns:
      {
        "run_id": "...",
        "session_id": "...",
        "summary": "<LLM-generated 1-paragraph 'why this failed'>",
        "last_reasoning": ["...", "...", "..."],  # up to 3
        "last_tool_calls": [{"name": "...", "result_preview": "..."}, ...],
        "orphan_kanban_task": { ... } | None,
        "generated_at": "<iso>",
        "summary_available": True | False,
      }
    """
    payload: dict[str, Any] = {
        "run_id": run_id,
        "session_id": session_id,
        "summary": "",
        "last_reasoning": [],
        "last_tool_calls": [],
        "orphan_kanban_task": None,
        "generated_at": _now_iso(),
        "summary_available": False,
    }

    # 1. Last 3 reasoning steps (from the session's events table).
    if db is not None:
        try:
            rows = await db.fetch(
                "SELECT event_data FROM stream_events "
                "WHERE session_id = $1 AND event_type = 'reasoning' "
                "ORDER BY created_at DESC LIMIT 3",
                session_id,
            )
            for r in rows:
                data = r["event_data"]
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                content = (data or {}).get("content", "")
                if content:
                    payload["last_reasoning"].append(str(content)[:1500])
        except Exception as exc:
            logger.debug("forensics: failed to read reasoning events: %s", exc)

    # 2. Last 5 tool calls (from the events table).
    if db is not None:
        try:
            rows = await db.fetch(
                "SELECT event_data FROM stream_events "
                "WHERE session_id = $1 AND event_type IN ('tool.execution.started', 'tool.execution.completed', 'tool.start', 'tool.completed') "
                "ORDER BY created_at DESC LIMIT 10",
                session_id,
            )
            for r in rows:
                data = r["event_data"]
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                if not data:
                    continue
                payload["last_tool_calls"].append({
                    "name": data.get("tool_name", "?"),
                    "result_preview": (str(data.get("output_preview", "") or data.get("tool_input", "")))[-200:],
                })
                if len(payload["last_tool_calls"]) >= 5:
                    break
        except Exception as exc:
            logger.debug("forensics: failed to read tool events: %s", exc)

    # 3. Orphan kanban task (any in_progress task on the run's board).
    if db is not None:
        try:
            row = await db.fetchrow(
                "SELECT kt.id, kt.title, kt.description, kb.name AS board_name "
                "FROM kanban_tasks kt JOIN kanban_boards kb ON kb.id = kt.board_id "
                "WHERE kt.column_name = 'in_progress' AND kt.session_id = $1 "
                "LIMIT 1",
                session_id,
            )
            if row:
                payload["orphan_kanban_task"] = {
                    "id": row["id"],
                    "title": row["title"],
                    "description": (row["description"] or "")[:500],
                    "board_name": row["board_name"],
                }
        except Exception as exc:
            logger.debug("forensics: failed to query kanban: %s", exc)

    # 4. LLM-generated summary. Best-effort.
    try:
        from harness.llm import ChatMessage
        
        # Use shared LLM router if available
        from harness.api.state import get_llm
        llm = get_llm()
        if llm is None:
            # Fallback: create fresh router and configure from DB
            from harness.llm import LLMRouter
            llm = LLMRouter()
            from harness.memory.db_context import get_db
            db_inst = get_db()
            if db_inst is not None:
                try:
                    rows = await db_inst.fetch(
                        "SELECT provider, config FROM provider_configs "
                        "WHERE config->>'enabled' = 'true' OR config->>'enabled' IS NULL"
                    )
                    if rows:
                        settings = []
                        for r in rows:
                            cfg = r["config"]
                            if isinstance(cfg, str):
                                cfg = json.loads(cfg)
                            settings.append({
                                "provider": r["provider"],
                                "model": cfg.get("model", ""),
                                "api_key": cfg.get("api_key", ""),
                                "base_url": cfg.get("base_url", ""),
                                "api_mode": cfg.get("api_mode", "openai"),
                                "enabled": cfg.get("enabled", True),
                            })
                        if settings:
                            llm.configure(settings)
                except Exception as e:
                    logger.warning("Failed to configure LLM from DB: %s", e)

        prompt = (
            "You are summarizing why a TestAI run failed for a human "
            "operator. The dashboard will show your output as a "
            "1-paragraph card.\n\n"
            "Given the run's last output (possibly truncated), the "
            "last few reasoning steps, and the last few tool calls, "
            "produce:\n"
            "  - 1 short paragraph (under 150 words) explaining the "
            "most likely root cause\n"
            "  - 1-2 specific actions the operator can take\n\n"
            "Be specific. Reference the actual tool names and errors. "
            "Do NOT include run IDs, model names, or session IDs.\n"
        )
        context = (
            f"RUN OUTPUT (truncated to 2k chars):\n"
            f"{(output or '')[:2000]}\n\n"
            f"LAST REASONING:\n"
            f"{json.dumps(payload['last_reasoning'], indent=2)[:2000]}\n\n"
            f"LAST TOOL CALLS:\n"
            f"{json.dumps(payload['last_tool_calls'], indent=2)[:1500]}\n\n"
            f"ORPHAN TASK: {payload['orphan_kanban_task'] or 'none'}\n"
        )
        response = await llm.chat([
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=context),
        ])
        text = (response.content or "").strip() if hasattr(response, "content") else str(response)
        if text:
            payload["summary"] = text
            payload["summary_available"] = True
    except Exception as exc:
        logger.warning("forensics: LLM summary failed run=%s: %s", run_id, exc)

    return payload


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
