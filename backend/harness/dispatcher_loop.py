"""Kanban dispatcher — picks up ready tasks and spawns workers.

Runs as a background loop. Reads kanban_tasks with column_name='ready',
checks dependencies, then spawns a worker agent via the agent factory.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_MAX_FAILURES = 2
_HEARTBEAT_TIMEOUT_SEC = 3600
_POLL_SECONDS = 30


async def dispatch_loop(
    db: Any,
    agent_factory: Any,
) -> None:
    logger.info("Dispatcher loop started (poll_seconds=%d)", _POLL_SECONDS)
    while True:
        try:
            await _tick(db, agent_factory)
        except Exception as exc:
            logger.debug("Dispatcher tick failed: %s", exc)
        await asyncio.sleep(_POLL_SECONDS)


async def _tick(
    db: Any,
    agent_factory: Any,
) -> None:
    # 1. Reclaim tasks whose worker stopped heartbeating
    stale = await db.fetch(
        "UPDATE kanban_tasks SET column_name = 'ready', updated_at = NOW() "
        "WHERE column_name = 'in_progress' "
        "AND last_heartbeat IS NOT NULL "
        "AND last_heartbeat < NOW() - $1::interval "
        "RETURNING id",
        f"{_HEARTBEAT_TIMEOUT_SEC} seconds",
    )
    for row in stale:
        logger.info("Dispatcher reclaimed stale task %s (no heartbeat)", row["id"])

    # 2. Find ready tasks with all dependencies met
    ready = await db.fetch(
        "SELECT t.* FROM kanban_tasks t "
        "WHERE t.column_name = 'ready' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM kanban_dependencies d "
        "  JOIN kanban_tasks dep ON dep.id = d.depends_on_task_id "
        "  WHERE d.task_id = t.id AND dep.column_name != 'done'"
        ")"
        "ORDER BY t.sort_order ASC NULLS LAST, t.created_at ASC "
        "LIMIT 5",
    )

    for task in ready:
        await _spawn_worker(db, agent_factory, task)


async def _spawn_worker(
    db: Any,
    agent_factory: Any,
    task: Any,
) -> None:
    task_id = task["id"]
    agent_type = task.get("agent_type") or DEFAULT_AGENT
    goal = task.get("description") or task.get("title") or ""

    if not goal:
        logger.warning("Dispatcher: task %s has no goal, blocking", task_id)
        await db.execute(
            "UPDATE kanban_tasks SET column_name = 'blocked', updated_at = NOW() WHERE id = $1",
            task_id,
        )
        return

    now = datetime.now(timezone.utc)
    await db.execute(
        "UPDATE kanban_tasks SET column_name = 'in_progress', last_heartbeat = $1, "
        "updated_at = $1 WHERE id = $2",
        now, task_id,
    )

    from harness.agent_discovery import DEFAULT_AGENT, get_agent, get_subagent_prompt

    # Fetch user comments for this task and append to worker context
    comments_context = ""
    try:
        comment_rows = await db.fetch(
            "SELECT payload, created_at FROM kanban_events "
            "WHERE task_id = $1 AND event_type = 'task.comment' ORDER BY id ASC",
            task_id,
        )
        if comment_rows:
            parts = []
            for r in comment_rows:
                payload = r["payload"]
                if isinstance(payload, str):
                    import json as _j
                    try:
                        payload = _j.loads(payload)
                    except Exception:
                        payload = {}
                author = payload.get("author", "user") if isinstance(payload, dict) else "user"
                body = payload.get("body", "") if isinstance(payload, dict) else str(payload)
                parts.append(f"- {author}: {body}")
            if parts:
                comments_context = "\n\n## User Comments\n" + "\n".join(parts)
    except Exception:
        pass

    agent_def = get_agent(agent_type)
    allowed_tools = agent_def.tools if agent_def and agent_def.tools else ["bash", "read", "grep", "glob"]
    system_prompt = get_subagent_prompt(agent_type, goal + comments_context, context="")

    async def _run_worker():
        try:
            agent = agent_factory(
                allowed_tools=allowed_tools,
                session_id=f"kanban-{task_id}",
                system_prompt_override=system_prompt,
            )
            result = await agent.run(goal)

            await db.execute(
                "UPDATE kanban_tasks SET column_name = 'done', result_summary = $1, "
                "updated_at = NOW() WHERE id = $2",
                result[:2000] if result else "", task_id,
            )
            logger.info("Dispatcher: task %s completed by %s", task_id[:12], agent_type)

        except Exception as exc:
            logger.warning("Dispatcher: task %s failed: %s", task_id[:12], exc)
            await db.execute(
                "UPDATE kanban_tasks SET failure_count = COALESCE(failure_count, 0) + 1, "
                "updated_at = NOW() WHERE id = $1",
                task_id,
            )
            row = await db.fetchrow("SELECT failure_count FROM kanban_tasks WHERE id = $1", task_id)
            if row and row["failure_count"] >= _MAX_FAILURES:
                await db.execute(
                    "UPDATE kanban_tasks SET column_name = 'blocked', updated_at = NOW() WHERE id = $1",
                    task_id,
                )
                logger.info("Dispatcher: task %s blocked after %d failures", task_id[:12], _MAX_FAILURES)
            else:
                await db.execute(
                    "UPDATE kanban_tasks SET column_name = 'ready', updated_at = NOW() WHERE id = $1",
                    task_id,
                )

    asyncio.create_task(_run_worker(), name=f"kanban-worker-{task_id[:12]}")
