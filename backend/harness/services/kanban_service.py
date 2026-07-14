"""Kanban service — all DB queries, helpers, and background review logic.
Extracted from api/routers/kanban.py to enable testing without FastAPI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from harness.memory.database import Database
from harness.kanban.rules import evaluate_rules_for_task

logger = logging.getLogger(__name__)


def _task_row_to_dict(r) -> dict:
    return {
        "id": r["id"], "boardId": r["board_id"], "title": r["title"],
        "description": r["description"] or "", "column": r["column_name"],
        "priority": r["priority"], "tags": r["tags"] or "",
        "assignedTo": r["assigned_to"] or "", "failureCount": r["failure_count"] or 0,
        "claimToken": r["claim_token"],
        "agentType": r.get("agent_type") or "general-purpose",
        "lastHeartbeat": r["last_heartbeat"].isoformat() if r.get("last_heartbeat") else None,
        "pipelineRunId": r["pipeline_run_id"] or "",
        "coverageFile": r["coverage_file"] or "",
        "flakyTestName": r["flaky_test_name"] or "",
        "timeboxSeconds": r["timebox_seconds"] or 0,
        "estimateMinutes": r["estimate_minutes"] or 0,
        "resultSummary": r["result_summary"] or "",
        "needsReview": r.get("needs_review", False),
        "reviewStatus": r.get("review_status"),
        "reviewNotes": r.get("review_notes") or "",
        "reviewedBy": r.get("reviewed_by") or "",
        "parentTaskId": r.get("parent_task_id") or None,
        "deadline": r["deadline"].isoformat() if r.get("deadline") else None,
        "startedAt": r["started_at"].isoformat() if r.get("started_at") else None,
        "completedAt": r["completed_at"].isoformat() if r.get("completed_at") else None,
        "sprint": r.get("sprint") or "",
        "createdAt": r["created_at"].isoformat() if r.get("created_at") else "",
        "updatedAt": r["updated_at"].isoformat() if r.get("updated_at") else "",
    }


async def _enrich_with_children_stats(db, tasks: list[dict]) -> list[dict]:
    """Attach ``childrenTotal`` and ``childrenDone`` to each task.

    One grouped query instead of N+1. Only includes tasks that have
    at least one child (or whose IDs are referenced as parents by
    someone). Tasks with no children are returned with the fields
    left off (the UI treats `childrenTotal > 0` as the gate).
    """
    if not tasks:
        return tasks
    task_ids = [t["id"] for t in tasks]
    rows = await db.fetch(
        """
        SELECT parent_task_id AS pid,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE column_name = 'done') AS done
        FROM kanban_tasks
        WHERE parent_task_id = ANY($1::text[])
        GROUP BY parent_task_id
        """,
        task_ids,
    )
    by_id: dict[str, dict[str, int]] = {
        r["pid"]: {"total": int(r["total"]), "done": int(r["done"])} for r in rows
    }
    for t in tasks:
        stats = by_id.get(t["id"])
        if stats:
            t["childrenTotal"] = stats["total"]
            t["childrenDone"] = stats["done"]
    return tasks


class KanbanService:
    def __init__(self, db: Database, reviewer: Any = None) -> None:
        self.db = db
        self._reviewer = reviewer

    async def _record_event(self, board_id: str, task_id: str, event_type: str, payload: dict | None = None) -> None:
        await self.db.execute(
            "INSERT INTO kanban_events (board_id, task_id, event_type, payload) VALUES ($1, $2, $3, $4)",
            board_id, task_id, event_type, json.dumps(payload or {}),
        )

    async def _emit_board_completion_if_done(self, board_id: str) -> None:
        """If every task on ``board_id`` is in a terminal column, emit
        a single ``board.completed`` or ``board.failed`` stream event.

        C03 push-completion seam. Called from
        :meth:`complete_task` and :meth:`block_task` after the
        per-task event has been recorded, so the event ordering in
        the SSE feed is always::

          task.completed  →  (board.completed | board.failed)

        The board's ``config.session_id`` is the routing key for the
        EventSourceSink (set by :func:`cmd_orchestrate` at board
        creation). If it's missing, the event is broadcast to every
        subscriber (consumers must filter by ``board_id``).

        Failure mode: the DB query is a single SELECT — if it fails
        we log and swallow. The next :meth:`complete_task` call on
        the same board will retry, so the worst case is a delayed
        ``board.completed`` rather than a missed one. The 60s
        ``BoardWaiter`` silence-then-poll fallback catches the
        delayed case automatically.
        """
        try:
            row = await self.db.fetchrow(
                "SELECT "
                "  COUNT(*) FILTER (WHERE column_name NOT IN ('done','blocked','review'))::int AS open_tasks, "
                "  COUNT(*) FILTER (WHERE column_name = 'blocked')::int AS blocked_tasks, "
                "  COUNT(*) FILTER (WHERE column_name = 'done')::int AS done_tasks, "
                "  COUNT(*)::int AS total_tasks, "
                "  config "
                "FROM kanban_tasks WHERE board_id = $1",
                board_id,
            )
        except Exception as exc:
            logger.warning("kanban board-completion check failed board_id=%s err=%s", board_id, exc)
            return

        if not row or row["open_tasks"] > 0:
            return  # still in flight; not terminal

        total = row["total_tasks"]
        if total == 0:
            return  # empty board; nothing to announce

        done = row["done_tasks"]
        blocked = row["blocked_tasks"]
        # ``review`` counts as open (the review agent hasn't moved it
        # to ``done`` yet). The check above filtered review out of
        # ``open_tasks`` only when the row filter is in flight. Fix:
        # re-check with review included.
        if (done + blocked) < total:
            return

        # Build the canonical task list for the event payload.
        tasks = await self.list_tasks(board_id)
        # Split by column for the payload (matches cmd_orchestrate_monitor).
        blocked_list = [t for t in tasks if t.get("column") == "blocked"]
        stalled_list: list[dict] = []
        # "Stalled" in the monitor vocabulary = blocked with failure_count>2.
        for t in blocked_list:
            if (t.get("failureCount") or 0) > 2:
                stalled_list.append(t)

        # Pick the event type:
        #   - If any task is blocked → ``board.failed`` with status
        #     ``stalled`` (cascading failure) or ``blocked`` (still retryable).
        #   - Otherwise → ``board.completed``.
        if blocked > 0:
            event_type = "board.failed"
            sub_status = "stalled" if stalled_list else "blocked"
            payload: dict[str, Any] = {
                "board_id": board_id,
                "status": sub_status,
                "done": done,
                "blocked": blocked,
                "total": total,
                "tasks": tasks,
                "blocked_tasks": blocked_list,
                "stalled_tasks": stalled_list,
            }
        else:
            event_type = "board.completed"
            payload = {
                "board_id": board_id,
                "done": done,
                "total": total,
                "tasks": tasks,
            }

        # Routing: prefer the session_id stored on the board at create
        # time (set by cmd_orchestrate via the orchestrator). If
        # missing, broadcast (any subscriber filters by board_id).
        session_id = ""
        cfg = row.get("config")
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except (TypeError, ValueError):
                cfg = None
        if isinstance(cfg, dict):
            session_id = str(cfg.get("session_id") or "")

        try:
            from harness.api.state import emit_stream_event
            await emit_stream_event(session_id, event_type, payload)
        except Exception as exc:
            logger.warning(
                "kanban board-completion emit failed board_id=%s event=%s err=%s",
                board_id, event_type, exc,
            )

    async def _record_agent_log(self, task_id: str, agent_id: str, action: str, detail: str = "") -> None:
        await self.db.execute(
            "INSERT INTO kanban_agent_log (task_id, agent_id, action, detail) VALUES ($1, $2, $3, $4)",
            task_id, agent_id, action, detail,
        )

    # ── Boards ─────────────────────────────────────────────────────

    async def list_boards(self, board_id: str = "", source: str = "") -> list[dict[str, Any]]:
        """List boards, optionally filtered by board_id or source.

        The `source` parameter filters by `config->>'source'` in the
        kanban_boards JSONB column (used by the pipeline page to find
        orchestrator-created boards without fetching all boards).
        """
        if board_id:
            rows = await self.db.fetch(
                "SELECT * FROM kanban_boards WHERE id = $1 ORDER BY created_at DESC",
                board_id,
            )
        elif source:
            rows = await self.db.fetch(
                "SELECT * FROM kanban_boards WHERE config->>'source' = $1 ORDER BY created_at DESC",
                source,
            )
        else:
            rows = await self.db.fetch("SELECT * FROM kanban_boards ORDER BY created_at DESC")
        # One round-trip for ALL tasks across ALL boards; partition
        # by board_id in memory. Cheaper than N+1 queries for the
        # common case of "show me all my kanbans". The board-scope
        # path doesn't need a separate query path — the partition
        # happens to be a no-op when there's only one board.
        all_tasks = await self.db.fetch(
            "SELECT * FROM kanban_tasks ORDER BY created_at ASC"
        )
        by_board: dict[str, list[dict]] = {}
        for r in all_tasks:
            by_board.setdefault(r["board_id"], []).append(_task_row_to_dict(r))

        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r["id"], "name": r["name"], "description": r["description"],
                "columns": r["columns"] if isinstance(r["columns"], list) else json.loads(r["columns"]),
                "wipLimits": r["wip_limits"] if isinstance(r["wip_limits"], dict) else json.loads(r["wip_limits"]),
                "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"]),
                "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
                "tasks": by_board.get(r["id"], []),
            })
        return out

    async def create_board(self, name: str, description: str, columns: list[str],
                           wip_limits: dict, config: dict) -> str:
        row = await self.db.fetchrow(
            "INSERT INTO kanban_boards (name, description, columns, wip_limits, config) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            name, description, json.dumps(columns), json.dumps(wip_limits), json.dumps(config),
        )
        return row["id"]

    async def update_board(self, board_id: str, name: str, description: str,
                           columns: list[str], wip_limits: dict, config: dict) -> None:
        await self.db.execute(
            "UPDATE kanban_boards SET name=$1, description=$2, columns=$3, wip_limits=$4, config=$5, updated_at=NOW() WHERE id=$6",
            name, description, json.dumps(columns), json.dumps(wip_limits), json.dumps(config), board_id,
        )

    async def delete_board(self, board_id: str) -> None:
        await self.db.execute("DELETE FROM kanban_events WHERE board_id = $1", board_id)
        await self.db.execute("DELETE FROM kanban_tasks WHERE board_id = $1", board_id)
        await self.db.execute("DELETE FROM kanban_boards WHERE id = $1", board_id)

    # ── Tasks ──────────────────────────────────────────────────────

    async def list_tasks(self, board_id: str, sprint: str = "") -> list[dict]:
        if sprint:
            rows = await self.db.fetch(
                "SELECT * FROM kanban_tasks WHERE board_id = $1 AND sprint = $2 ORDER BY sort_order ASC, created_at DESC",
                board_id, sprint,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM kanban_tasks WHERE board_id = $1 ORDER BY sort_order ASC, created_at DESC",
                board_id,
            )
        tasks = [_task_row_to_dict(r) for r in rows]
        return await _enrich_with_children_stats(self.db, tasks)

    async def list_sprints(self, board_id: str) -> list[str]:
        rows = await self.db.fetch(
            "SELECT DISTINCT sprint FROM kanban_tasks WHERE board_id = $1 AND sprint != '' ORDER BY sprint DESC",
            board_id,
        )
        return [r["sprint"] for r in rows]

    async def get_task(self, task_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM kanban_tasks WHERE id = $1", task_id)
        if not row:
            return None
        task = _task_row_to_dict(row)
        enriched = await _enrich_with_children_stats(self.db, [task])
        return enriched[0]

    async def _default_column(self, board_id: str) -> str:
        """Return the first column for a board, or 'backlog' as fallback."""
        row = await self.db.fetchrow("SELECT columns FROM kanban_boards WHERE id = $1", board_id)
        if row:
            cols = row["columns"]
            if isinstance(cols, str):
                cols = json.loads(cols)
            if isinstance(cols, list) and cols:
                return cols[0]
        return "backlog"

    async def create_task(self, board_id: str, body: dict) -> str:
        default_col = body.get("column_name") or await self._default_column(board_id)
        row = await self.db.fetchrow(
            """INSERT INTO kanban_tasks (board_id, title, description, column_name, priority, tags,
               assigned_to, coverage_file, flaky_test_name, timebox_seconds, estimate_minutes,
               pipeline_run_id, parent_task_id, needs_review)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING id""",
            board_id, body["title"], body.get("description", ""), default_col,
            body.get("priority", "p2"), body.get("tags", ""),
            body.get("assigned_to", ""), body.get("coverage_file", ""), body.get("flaky_test_name", ""),
            body.get("timebox_seconds", 0), body.get("estimate_minutes", 0),
            body.get("pipeline_run_id", ""), body.get("parent_task_id") or None,
            body.get("needs_review", False),
        )
        await self._record_event(board_id, row["id"], "task.created", {
            "title": body.get("title"), "column": body.get("column_name"),
        })
        await evaluate_rules_for_task(self.db, board_id, row["id"], "task.created", body)
        return row["id"]

    async def update_task(self, task_id: str, updates: dict) -> None:
        sets: list[str] = []
        vals: list[Any] = []
        i = 1
        field_map = {
            "title": "title", "description": "description", "column_name": "column_name",
            "priority": "priority", "tags": "tags", "assigned_to": "assigned_to",
            "coverage_file": "coverage_file", "result_summary": "result_summary",
            "needs_review": "needs_review",
        }
        for field, col in field_map.items():
            val = updates.get(field)
            if val is not None:
                sets.append(f"{col} = ${i}")
                vals.append(val)
                i += 1
        if sets:
            sets.append("updated_at = NOW()")
            vals.append(task_id)
            await self.db.execute(f"UPDATE kanban_tasks SET {', '.join(sets)} WHERE id = ${i}", *vals)

            task = await self.db.fetchrow("SELECT board_id, column_name FROM kanban_tasks WHERE id = $1", task_id)
            if task and "column_name" in updates:
                await self._record_event(task["board_id"], task_id, "task.moved",
                                         {"to_column": updates["column_name"]})
                task_data = await self.db.fetchrow("SELECT * FROM kanban_tasks WHERE id = $1", task_id)
                if task_data:
                    await evaluate_rules_for_task(self.db, task["board_id"], task_id, "task.moved", dict(task_data))
                # C03: a manual column move to a terminal column
                # (``done`` / ``blocked``) should also trigger the
                # board-completion check. ``needs_review`` targets
                # land in ``review`` which is NOT terminal.
                if updates["column_name"] in ("done", "blocked"):
                    await self._emit_board_completion_if_done(task["board_id"])

    async def claim_task(self, task_id: str) -> dict:
        """Atomically claim a task. Auto-blocks on failure_limit exceeded.

        Hermes `kanban.failure_limit` pattern: a task that has failed
        ``failure_limit`` times (default 2) is auto-blocked instead of
        being re-claimed. This prevents spin-loops where the same task
        is re-attempted indefinitely after repeated failures.

        The limit is read from the board's ``config.failure_limit``
        JSONB column (set by `_create_kanban_board` to ``3`` for
        orchestrator-created boards, ``2`` for dispatcher-created
        boards). When the column is missing or invalid, ``2`` is used.

        Returns:
          - ``{"status": "claimed", "claimToken": "..."}`` on success
          - ``{"status": "already_claimed"}`` if another claim is live
          - ``{"status": "auto_blocked", "failure_count": N,
              "failure_limit": L}`` if the task is over the limit
        """
        row = await self.db.fetchrow(
            "SELECT t.id, t.board_id, t.failure_count, b.config "
            "FROM kanban_tasks t JOIN kanban_boards b ON b.id = t.board_id "
            "WHERE t.id = $1",
            task_id,
        )
        if not row:
            return {"status": "not_found"}
        failure_count = row["failure_count"] or 0
        limit = self._failure_limit_from_config(row["config"])
        if failure_count >= limit:
            await self.db.execute(
                "UPDATE kanban_tasks SET column_name='blocked', claim_token=NULL, "
                "updated_at=NOW() WHERE id=$1",
                task_id,
            )
            await self._record_event(
                row["board_id"], task_id, "task.auto_blocked",
                {"reason": "failure_limit", "failure_count": failure_count,
                 "failure_limit": limit},
            )
            # C03: the auto-block may be the last open task; nudge
            # the board-completion check so the orchestrator's
            # waiter can see ``board.failed`` immediately.
            await self._emit_board_completion_if_done(row["board_id"])
            return {
                "status": "auto_blocked",
                "failure_count": failure_count,
                "failure_limit": limit,
            }
        token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        claimed = await self.db.fetchrow(
            "UPDATE kanban_tasks SET claim_token=$1, claimed_at=$2, "
            "claim_expires_at=$3, column_name='in_progress', updated_at=NOW() "
            "WHERE id=$4 AND claim_token IS NULL RETURNING id, board_id",
            token, now, now.replace(hour=now.hour + 1), task_id,
        )
        if not claimed:
            return {"status": "already_claimed"}
        await self._record_event(row["board_id"], task_id, "task.claimed", {"claim_token": token})
        return {"status": "claimed", "claimToken": token}

    def _failure_limit_from_config(self, config: Any) -> int:
        """Extract ``failure_limit`` from a board's config JSONB.

        Tolerates missing keys, malformed JSON, and non-int values
        (defensive — the board's ``config`` column is JSONB, but a
        bad write or a migration could leave it as a string). On any
        error, returns the global default of 2.
        """
        default = 2
        if not config:
            return default
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (TypeError, ValueError):
                return default
        if not isinstance(config, dict):
            return default
        raw = config.get("failure_limit", default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        if value < 1:
            return default
        return value

    async def complete_task(self, task_id: str) -> dict:
        row = await self.db.fetchrow("SELECT board_id, needs_review FROM kanban_tasks WHERE id = $1", task_id)
        if not row:
            return {"status": "not_found"}
        target = "review" if row["needs_review"] else "done"
        await self.db.execute(
            "UPDATE kanban_tasks SET column_name=$1, claim_token=NULL, updated_at=NOW() WHERE id=$2",
            target, task_id,
        )
        await self._record_event(row["board_id"], task_id, "task.completed", {"target_column": target})
        # C03: nudge the board-completion check. If ``needs_review``,
        # the target column is ``review`` and the task is NOT counted
        # as ``done`` yet, so this call is a no-op until the review
        # agent moves the task to ``done`` (which calls complete_task
        # again via review_task).
        await self._emit_board_completion_if_done(row["board_id"])
        return {"status": "ok", "target_column": target}

    async def heartbeat_task(self, task_id: str, note: str = "") -> dict:
        task = await self.db.fetchrow(
            "UPDATE kanban_tasks SET claim_expires_at=NOW() + INTERVAL '1 hour', updated_at=NOW() "
            "WHERE id=$1 AND column_name='in_progress' RETURNING board_id",
            task_id,
        )
        if task:
            await self._record_event(task["board_id"], task_id, "task.heartbeat", {"note": note})
            return {"status": "ok", "claim_extended": True}
        return {"status": "ok", "claim_extended": False}

    async def review_task(self, task_id: str, action: str, reviewer: str, notes: str = "") -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM kanban_tasks WHERE id = $1", task_id)
        if not row:
            return None
        if action == "approve":
            await self.db.execute(
                "UPDATE kanban_tasks SET column_name='done', review_status='approved', "
                "reviewed_by=$1, review_notes=$2, reviewed_at=NOW(), updated_at=NOW() WHERE id=$3",
                reviewer, notes, task_id,
            )
            await self._record_event(row["board_id"], task_id, "task.approved",
                                      {"reviewer": reviewer, "notes": notes})
            # C03: approving a review moves a task to ``done``. If
            # this was the last review column task, the board is now
            # complete — emit the push event.
            await self._emit_board_completion_if_done(row["board_id"])
        elif action == "reject":
            await self.db.execute(
                "UPDATE kanban_tasks SET column_name='in_progress', review_status='rejected', "
                "claim_token=NULL, reviewed_by=$1, review_notes=$2, reviewed_at=NOW(), updated_at=NOW() WHERE id=$3",
                reviewer, notes, task_id,
            )
            await self._record_event(row["board_id"], task_id, "task.rejected",
                                      {"reviewer": reviewer, "notes": notes})
        else:
            return {"error": "action must be 'approve' or 'reject'"}
        updated = await self.db.fetchrow("SELECT * FROM kanban_tasks WHERE id = $1", task_id)
        return {"task": _task_row_to_dict(updated), "action": action}

    async def block_task(self, task_id: str) -> None:
        task = await self.db.fetchrow(
            "UPDATE kanban_tasks SET column_name='blocked', failure_count=failure_count+1, claim_token=NULL, updated_at=NOW() WHERE id=$1 RETURNING board_id",
            task_id,
        )
        if task:
            await self._record_event(task["board_id"], task_id, "task.blocked", {})
            # C03: blocking a task may be the last open task; emit
            # ``board.failed`` so the orchestrator's BoardWaiter can
            # tear down the run without polling.
            await self._emit_board_completion_if_done(task["board_id"])

    async def sweep_orphan_in_progress(
        self, board_id: str, run_succeeded: bool, reason: str = ""
    ) -> dict:
        """Sweep `in_progress` tasks left behind when a run ends.

        The orchestrator's coordinator may finish (success, failure, or
        "max tool rounds reached") without calling ``kanban_complete`` for
        every task it claimed. Those tasks would otherwise sit in
        ``in_progress`` forever, blocking the board from being archived.

        For each orphan task, we either complete it (if the run succeeded
        — assume the work got done) or block it (if the run failed —
        preserve evidence for review). Both moves emit a
        ``task.swept_orphan`` event so the dashboard can highlight the
        auto-reconciliation.

        Returns counts so callers can log / surface the sweep in their
        return payload.
        """
        rows = await self.db.fetch(
            "SELECT id FROM kanban_tasks "
            "WHERE board_id=$1 AND column_name='in_progress'",
            board_id,
        )
        completed = 0
        blocked = 0
        for row in rows:
            task_id = row["id"]
            if run_succeeded:
                await self.complete_task(task_id)
                await self._record_event(
                    board_id, task_id, "task.swept_orphan",
                    {"auto_action": "completed", "reason": reason or "run_succeeded"},
                )
                completed += 1
            else:
                await self.block_task(task_id)
                await self._record_event(
                    board_id, task_id, "task.swept_orphan",
                    {"auto_action": "blocked", "reason": reason or "run_failed"},
                )
                blocked += 1
        return {"swept": len(rows), "completed": completed, "blocked": blocked}

    async def unblock_task(self, task_id: str) -> None:
        task = await self.db.fetchrow(
            "UPDATE kanban_tasks SET column_name='ready', failure_count=0, updated_at=NOW() WHERE id=$1 AND column_name='blocked' RETURNING board_id",
            task_id,
        )
        if task:
            await self._record_event(task["board_id"], task_id, "task.unblocked", {})

    async def add_comment(self, task_id: str, author: str, body: str) -> dict:
        task = await self.db.fetchrow("SELECT board_id, title FROM kanban_tasks WHERE id = $1", task_id)
        if not task:
            return {"status": "not_found"}
        await self._record_event(task["board_id"], task_id, "task.comment", {
            "author": author, "body": body,
        })
        return {"status": "ok"}

    async def triage_task(self, task_id: str, mode: str, instructions: str = "") -> dict:
        row = await self.db.fetchrow("SELECT * FROM kanban_tasks WHERE id = $1", task_id)
        if not row:
            return {"status": "not_found"}
        if mode == "manual":
            return {"task": _task_row_to_dict(row), "mode": "manual", "plan": None}
        try:
            from harness.llm import LLMClient, ChatMessage
            client = LLMClient()
            prompt = (
                "You are a senior engineering triage agent. Analyze the following task "
                "and produce a structured execution plan. Return ONLY valid JSON with keys: "
                "title (refined title), description (expanded description), "
                "subtasks (array of {title, description, estimated_minutes}), "
                "estimated_minutes (total), tags (array of strings).\n\n"
                f"Task title: {row['title']}\n"
                f"Task description: {row['description'] or 'N/A'}\n"
                f"Priority: {row['priority']}\n"
                f"Tags: {row['tags'] or ''}\n"
                + (f"User instructions: {instructions}\n" if instructions else "")
            )
            messages = [ChatMessage(role="user", content=prompt)]
            response = await client.chat(messages)
            content = response.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            plan = json.loads(content)
            new_title = plan.get("title", row["title"])
            new_desc = plan.get("description", row["description"] or "")
            tags_str = ", ".join(plan.get("tags", [])) or row["tags"]
            await self.db.execute(
                "UPDATE kanban_tasks SET title=$1, description=$2, column_name='backlog', "
                "tags=$3, estimate_minutes=$4, updated_at=NOW() WHERE id=$5",
                new_title, new_desc, tags_str, plan.get("estimated_minutes", 0), task_id,
            )
            await self._record_event(row["board_id"], task_id, "task.triaged",
                                      {"plan": plan, "mode": "auto"})
            updated = await self.db.fetchrow("SELECT * FROM kanban_tasks WHERE id = $1", task_id)
            return {"task": _task_row_to_dict(updated), "mode": "auto",
                    "plan": plan, "subtasks_created": len(plan.get("subtasks", []))}
        except Exception as e:
            logger.warning("Auto-triage failed for %s: %s", task_id, e)
            return {"task": _task_row_to_dict(row), "mode": "auto_fallback",
                    "plan": None, "error": str(e)}

    async def delete_task(self, task_id: str) -> None:
        await self.db.execute("DELETE FROM kanban_dependencies WHERE task_id=$1 OR depends_on_task_id=$1", task_id)
        await self.db.execute("DELETE FROM kanban_agent_log WHERE task_id=$1", task_id)
        await self.db.execute("DELETE FROM kanban_tasks WHERE id=$1", task_id)

    # ── Dependencies ───────────────────────────────────────────────

    async def list_dependencies(self, task_id: str) -> list[dict]:
        deps = await self.db.fetch(
            "SELECT d.depends_on_task_id, t.title, t.column_name FROM kanban_dependencies d "
            "JOIN kanban_tasks t ON t.id = d.depends_on_task_id WHERE d.task_id = $1",
            task_id,
        )
        return [{"taskId": d["depends_on_task_id"], "title": d["title"], "status": d["column_name"]} for d in deps]

    async def add_dependency(self, task_id: str, depends_on: str) -> str:
        try:
            await self.db.execute(
                "INSERT INTO kanban_dependencies (task_id, depends_on_task_id) VALUES ($1, $2)",
                task_id, depends_on,
            )
            return "ok"
        except Exception:
            return "already_exists"

    async def remove_dependency(self, task_id: str, dep_id: str) -> None:
        await self.db.execute(
            "DELETE FROM kanban_dependencies WHERE task_id=$1 AND depends_on_task_id=$2",
            task_id, dep_id,
        )

    # ── Agent Log ──────────────────────────────────────────────────

    async def log_agent_action(self, task_id: str, agent_id: str, action: str, detail: str = "") -> None:
        await self._record_agent_log(task_id, agent_id, action, detail)

    async def get_agent_log(self, task_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM kanban_agent_log WHERE task_id = $1 ORDER BY created_at ASC",
            task_id,
        )
        return [{"agentId": r["agent_id"], "action": r["action"], "detail": r["detail"],
                  "createdAt": r["created_at"].isoformat() if r["created_at"] else ""} for r in rows]

    # ── Events ─────────────────────────────────────────────────────

    async def get_events(self, board_id: str, after: int = 0, limit: int = 50) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM kanban_events WHERE board_id = $1 AND id > $2 ORDER BY id ASC LIMIT $3",
            board_id, after, limit,
        )
        return [
            {"id": r["id"], "taskId": r["task_id"], "eventType": r["event_type"],
             "payload": r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"]),
             "createdAt": r["created_at"].isoformat() if r["created_at"] else ""}
            for r in rows
        ]

    async def get_stats(self, board_id: str) -> dict:
        total = await self.db.fetchval("SELECT COUNT(*) FROM kanban_tasks WHERE board_id = $1", board_id)
        done = await self.db.fetchval("SELECT COUNT(*) FROM kanban_tasks WHERE board_id = $1 AND column_name = 'done'", board_id)
        wip = await self.db.fetchval("SELECT COUNT(*) FROM kanban_tasks WHERE board_id = $1 AND column_name = 'in_progress'", board_id)
        flaky = await self.db.fetchval(
            "SELECT COUNT(*) FROM kanban_tasks WHERE board_id = $1 AND flaky_test_name != ''", board_id,
        )
        auto = await self.db.fetchval(
            "SELECT COUNT(*) FROM kanban_tasks WHERE board_id = $1 AND (flaky_test_name != '' OR coverage_file != '')",
            board_id,
        )
        return {"total": total or 0, "done": done or 0, "wip": wip or 0,
                "flaky": flaky or 0, "autoCreated": auto or 0}

    # ── Pipeline integration ───────────────────────────────────────

    async def create_task_from_pipeline(self, run_id: str, title: str, status: str) -> dict:
        boards = await self.db.fetch("SELECT id FROM kanban_boards ORDER BY created_at ASC LIMIT 1")
        if not boards:
            return {"error": "No boards exist"}
        column = "done" if status == "completed" else "blocked"
        row = await self.db.fetchrow(
            "INSERT INTO kanban_tasks (board_id, title, column_name, tags, pipeline_run_id) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            boards[0]["id"], title, column, "pipeline", run_id,
        )
        await self._record_event(boards[0]["id"], row["id"], "task.created_from_pipeline",
                                  {"run_id": run_id, "status": status})
        return {"id": row["id"], "status": "ok"}


# ── Background workers (started at app startup) ─────────────────────


async def _reap_stale_claims(svc: KanbanService):
    """Reclaim tasks whose claim TTL expired. Runs every 60s."""
    await svc.db.execute(
        "UPDATE kanban_tasks SET claim_token=NULL, claimed_at=NULL, claim_expires_at=NULL, "
        "column_name='ready', failure_count=failure_count+1, updated_at=NOW() "
        "WHERE claim_expires_at < NOW() AND claim_token IS NOT NULL"
    )


async def run_review_agent(app):
    """Background task that auto-reviews tasks in the review column.
    Delegates to harness.services.task_reviewer.run_review_agent_loop.
    """
    from harness.services.task_reviewer import run_review_agent_loop, LLMReviewer
    while True:
        try:
            if not hasattr(app.state, "db") or app.state.db is None:
                await asyncio.sleep(30)
                continue
            svc = KanbanService(app.state.db, reviewer=LLMReviewer())
            await run_review_agent_loop(app.state.db, svc, svc._reviewer)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("run_review_agent restarting after error: %s", e)
            await asyncio.sleep(30)


def start_review_agent(app):
    """Start the review agent + stale claim reaper as a background task."""
    task = asyncio.create_task(run_review_agent(app))
    task.set_name("kanban-review-agent")
    return task
