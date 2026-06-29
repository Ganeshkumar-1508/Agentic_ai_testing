"""Kanban agent tools — agents interact with the board via these tools.

Tools: list, show, create, assign, start, complete, block, unblock, comment

The kanban tools run IN-PROCESS with the backend (the orchestrator /
subagent process imports these and the call happens on the same
host). They talk to the backend's own HTTP listener via
`http://localhost:8000` (the IN-CONTAINER port). The HOST port
(`8001` in `docker-compose.yml`) is not reachable from inside the
container — using it yields `ConnectError` on every call.

History: the file previously had `API = "http://localhost:8001"`
(the host port), which made every `kanban_create` die with
`ConnectError: All connection attempts failed` and left the
Kanban empty even when the orchestrator was actively trying to
create cards. Fixed in the e2e-test round (June 2026).
"""
from __future__ import annotations

import json
import os
from typing import Any

from harness.tools.base import ToolResult, ToolSpec
from harness.tools.registry import registry

# In-container port. The uvicorn listener inside the backend container
# binds to 0.0.0.0:8000; the host maps that to 8001 via docker-compose.
# The kanban tools are in-process so they MUST use the in-container port.
# Override with `TESTAI_INTERNAL_API` if you front the backend with a
# sidecar / proxy inside the same pod.
API = os.environ.get("TESTAI_INTERNAL_API", "http://localhost:8000")


def _board_scope_headers() -> dict:
    """Q10-C: return request headers that scope kanban queries to a
    specific board.

    When a subagent is spawned against a specific board, the
    orchestrator sets `os.environ["TESTAI_KANBAN_BOARD"] = <board_id>`.
    The kanban tools read that env var on every request and pass
    it to the API as `X-TestAI-Board-Id`. The kanban API filters
    queries by this header so a subagent working on board A cannot
    read or mutate board B's tasks.

    Returns an empty dict when the env var is unset (i.e. the
    call is from a context that doesn't have a board scope — e.g.
    a human operator using the dashboard directly). In that case
    the API returns boards / tasks unfiltered.
    """
    board = os.environ.get("TESTAI_KANBAN_BOARD", "").strip()
    if not board:
        return {}
    return {"X-TestAI-Board-Id": board}


async def _api_get(path: str) -> dict:
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{API}{path}", headers=_board_scope_headers(), timeout=10)
        return r.json()


async def _api_post(path: str, body: dict | None = None) -> dict:
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{API}{path}", json=body or {}, headers=_board_scope_headers(), timeout=10)
        return r.json()


async def _api_patch(path: str, body: dict) -> dict:
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{API}{path}", json=body, headers=_board_scope_headers(), timeout=10)
        return r.json()


async def _api_delete(path: str) -> dict:
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{API}{path}", timeout=10)
        return r.json()


async def cmd_kanban_list(board_id: str = "", status: str = "", assignee: str = "") -> str:
    """List tasks on a board, filterable by status/assignee."""
    boards = await _api_get("/api/kanban/boards")
    all_b = boards.get("boards", [])
    if not all_b:
        return tool_result(message="No boards found.")
    bid = board_id or all_b[0]["id"]
    data = await _api_get(f"/api/kanban/boards/{bid}/tasks")
    tasks = data.get("tasks", [])
    if status:
        tasks = [t for t in tasks if t["column"] == status]
    if assignee:
        tasks = [t for t in tasks if t["assignedTo"] == assignee]
    if not tasks:
        return tool_result(message="No tasks match your filters.")
    return tool_result(tasks=[{"id": t["id"], "title": t["title"], "column": t["column"],
                               "priority": t["priority"], "assignee": t["assignedTo"]} for t in tasks[:20]])


async def cmd_kanban_show(task_id: str) -> str:
    """View task details, dependencies, prior attempts, and history."""
    task = await _api_get(f"/api/kanban/tasks/{task_id}")
    t = task.get("task", {})
    if not t:
        return tool_error("Task not found.")
    deps = await _api_get(f"/api/kanban/tasks/{task_id}/dependencies")
    events = await _api_get(f"/api/kanban/boards/{t.get('boardId', t.get('board_id', ''))}/events?task_id={task_id}&limit=5")
    logs = await _api_get(f"/api/kanban/tasks/{task_id}/logs?limit=5")
    return tool_result(
        task=t,
        dependencies=deps.get("dependencies", []),
        history={
            "events": events.get("events", []),
            "agent_logs": logs.get("logs", []),
        },
        prior_outcomes=[l.get("detail") for l in logs.get("logs", []) if l.get("action") in ("completed", "blocked")],
    )


async def cmd_kanban_create(board_id: str, title: str, description: str = "",
                             priority: str = "p2", tags: str = "",
                             assignee: str = "") -> str:
    """Create a new task on a board. Optionally assign to an agent.

    The `assignee` parameter is the LLM-favored convenience: it lets
    the model combine `kanban_create` + `kanban_assign` into a single
    tool call. The earlier signature rejected `assignee` with a
    `TypeError`, which the orchestrator surfaced to the LLM and
    caused it to spiral into retries. The deepseek-v4-flash model
    used in the e2e-test (June 2026) was particularly prone to
    sending `assignee` even when the tool spec didn't list it.
    """
    boards = await _api_get("/api/kanban/boards")
    all_b = boards.get("boards", [])
    bid = board_id or (all_b[0]["id"] if all_b else "")
    if not bid:
        return tool_error("No board_id provided and no boards exist.")
    result = await _api_post(f"/api/kanban/boards/{bid}/tasks", {
        "board_id": bid, "title": title, "description": description,
        "priority": priority, "tags": tags, "column_name": "backlog",
    })
    task_id = result.get("id", "")
    if task_id and assignee:
        # Inline follow-up: assign immediately. The standalone
        # `kanban_assign` tool is still available for later reassign.
        await _api_patch(f"/api/kanban/tasks/{task_id}", {"assigned_to": assignee})
    return tool_result(task_id=task_id, status="created",
                      assigned_to=assignee if assignee else None)


async def cmd_kanban_assign(task_id: str, assignee: str) -> str:
    """Assign a task to an agent."""
    await _api_patch(f"/api/kanban/tasks/{task_id}", {"assigned_to": assignee})
    return tool_result(status="assigned", task_id=task_id, assignee=assignee)


async def cmd_kanban_start(task_id: str) -> str:
    """Claim a task and move it to in_progress."""
    result = await _api_post(f"/api/kanban/tasks/{task_id}/claim")
    return tool_result(**result)


async def cmd_kanban_complete(task_id: str, summary: str = "", metadata: str = "") -> str:
    """Mark a task as done with summary and structured metadata."""
    body = {"result_summary": summary}
    if metadata:
        try:
            parsed = json.loads(metadata)
            body["result_summary"] = summary + "\n" + json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            body["result_summary"] = summary + "\n" + metadata
    await _api_patch(f"/api/kanban/tasks/{task_id}", body)
    await _api_post(f"/api/kanban/tasks/{task_id}/complete")
    await _api_post(f"/api/kanban/tasks/{task_id}/log",
                    {"agent_id": "worker", "action": "completed", "detail": summary[:200]})
    return tool_result(status="completed", task_id=task_id)


async def cmd_kanban_block(task_id: str, reason: str = "") -> str:
    """Mark a task as blocked. Reason can be plain text or JSON with findings."""
    await _api_post(f"/api/kanban/tasks/{task_id}/block")
    try:
        parsed = json.loads(reason)
        detail = json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, TypeError):
        detail = reason
    await _api_post(f"/api/kanban/tasks/{task_id}/log",
                    {"agent_id": "reviewer", "action": "blocked", "detail": detail})
    return tool_result(status="blocked", task_id=task_id, reason=reason)


async def cmd_kanban_unblock(task_id: str) -> str:
    """Unblock a task and return it to ready."""
    await _api_patch(f"/api/kanban/tasks/{task_id}", {"column_name": "ready"})
    return tool_result(status="unblocked", task_id=task_id)


async def cmd_kanban_comment(task_id: str, comment: str) -> str:
    """Add a comment to a task (stored in agent log)."""
    await _api_post(f"/api/kanban/tasks/{task_id}/log",
                    {"agent_id": "orchestrator", "action": "commented", "detail": comment})
    return tool_result(status="comment_added", task_id=task_id)


async def cmd_kanban_link(task_id: str, depends_on_task_id: str) -> str:
    """Add a dependency between two tasks (task_id blocks on depends_on_task_id)."""
    result = await _api_post(f"/api/kanban/tasks/{task_id}/dependencies",
                              {"depends_on_task_id": depends_on_task_id})
    return tool_result(**result)


async def cmd_kanban_heartbeat(task_id: str = "", note: str = "") -> str:
    """Signal that the worker is still alive during a long operation.
    Extends claim TTL and records a heartbeat event.
    """
    result = await _api_post(f"/api/kanban/tasks/{task_id}/heartbeat" if task_id else "/api/kanban/heartbeat",
                              {"note": note} if note else {})
    return tool_result(**result)


def tool_result(**kwargs) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


def tool_error(msg: str) -> str:
    return json.dumps({"error": msg}, ensure_ascii=False)


# Register all tools
TOOLS = [
    ("kanban_list", "List tasks on a board. Filter by status (column) or assignee.", {
        "board_id": {"type": "string", "description": "Board ID (optional, uses first board)"},
        "status": {"type": "string", "description": "Filter by column: backlog, ready, in_progress, review, done"},
        "assignee": {"type": "string", "description": "Filter by assignee name"},
    }),
    ("kanban_show", "View task details, dependencies, prior attempts, and event history. Check prior_outcomes to see what failed before.", {
        "task_id": {"type": "string", "description": "Task ID"},
    }),
    ("kanban_create", "Create a new task on a board. Optionally assign to an agent in the same call.", {
        "board_id": {"type": "string", "description": "Board ID (optional, uses first board)"},
        "title": {"type": "string", "description": "Task title"},
        "description": {"type": "string", "description": "Task description"},
        "priority": {"type": "string", "description": "p0 (critical) / p1 (high) / p2 (medium) / p3 (low)"},
        "tags": {"type": "string", "description": "Comma-separated tags: flaky, coverage, pipeline, etc."},
        "assignee": {"type": "string", "description": "Agent name to assign immediately (e.g. 'coordinator', 'fixer', 'tester')"},
    }),
    ("kanban_assign", "Assign a task to an agent.", {
        "task_id": {"type": "string"}, "assignee": {"type": "string"},
    }),
    ("kanban_start", "Claim a task and start working on it.", {
        "task_id": {"type": "string"},
    }),
    ("kanban_complete", "Complete a task with summary and optional JSON metadata (changed_files, tests_run, findings).", {
        "task_id": {"type": "string"}, "summary": {"type": "string", "description": "Human-readable handoff summary"},
        "metadata": {"type": "string", "description": "JSON: {changed_files, verification, residual_risk}"},
    }),
    ("kanban_block", "Block a task. Reason can be plain text or JSON with structured findings.", {
        "task_id": {"type": "string"}, "reason": {"type": "string", "description": "Plain text or JSON: {severity, findings: [{file, issue, suggestion}], residual_risk}"},
    }),
    ("kanban_unblock", "Unblock a task and move it back to ready.", {
        "task_id": {"type": "string"},
    }),
    ("kanban_comment", "Add a comment to a task.", {
        "task_id": {"type": "string"}, "comment": {"type": "string"},
    }),
    ("kanban_link", "Add a dependency between two tasks (blocks on).", {
        "task_id": {"type": "string", "description": "Task that will be blocked"},
        "depends_on_task_id": {"type": "string", "description": "Task it depends on"},
    }),
    ("kanban_heartbeat", "Signal that the worker is still alive during a long operation. Call every few minutes.", {
        "task_id": {"type": "string", "description": "Task ID (from env if omitted)"},
        "note": {"type": "string", "description": "Optional note about what's happening"},
    }),
]

HANDLERS = {
    "kanban_list": cmd_kanban_list, "kanban_show": cmd_kanban_show,
    "kanban_create": cmd_kanban_create, "kanban_assign": cmd_kanban_assign,
    "kanban_start": cmd_kanban_start, "kanban_complete": cmd_kanban_complete,
    "kanban_block": cmd_kanban_block, "kanban_unblock": cmd_kanban_unblock,
    "kanban_comment": cmd_kanban_comment, "kanban_link": cmd_kanban_link,
    "kanban_heartbeat": cmd_kanban_heartbeat,
}

for name, desc, props in TOOLS:
    registry.register_raw(
        name=name, toolset="kanban",
        schema={"name": name, "description": desc, "input_schema": {"type": "object", "properties": props, "required": list(props.keys())}},
        handler=HANDLERS[name],
    )
