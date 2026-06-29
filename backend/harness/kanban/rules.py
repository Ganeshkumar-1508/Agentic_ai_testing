"""Automation rules engine for kanban boards.

Evaluates JSON when-then rules stored in board config on every task event.
Rules are evaluated when tasks are created or updated in the kanban board.

Rule format (stored in kanban_boards.config.automations):
[
  {
    "id": "auto-assign-flaky",
    "name": "Auto-assign flaky tasks",
    "enabled": true,
    "trigger": {
      "event": "task.created",  # or "task.moved", "task.assigned"
      "conditions": {
        "has_tag": "flaky",
        "assignee_is": null,
        "column_is": "backlog"
      }
    },
    "actions": [
      {"type": "assign", "params": {"assignee": "agent-alpha"}},
      {"type": "set_priority", "params": {"priority": "p1"}},
      {"type": "add_label", "params": {"tag": "auto-assigned"}}
    ]
  }
]

Action types:
  - assign: {"assignee": "agent-name"}
  - set_priority: {"priority": "p0"|"p1"|"p2"|"p3"}
  - add_label: {"tag": "label-name"}
  - move: {"column": "column-name"}
  - notify:slack: {"channel": "#channel", "message": "text"}
  - create_task: {"title": "...", "tags": "..."}
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def evaluate_rules_for_task(db: Any, board_id: str, task_id: str, event: str, task_data: dict):
    """Evaluate all enabled automation rules for a board when a task event fires."""
    board = await db.fetchrow("SELECT config FROM kanban_boards WHERE id = $1", board_id)
    if not board:
        return

    config = board["config"]
    if isinstance(config, str):
        config = json.loads(config)

    rules = config.get("automations", [])
    if not rules:
        return

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        trigger = rule.get("trigger", {})
        if trigger.get("event") != event:
            continue

        conditions = trigger.get("conditions", {})
        if not _matches_conditions(conditions, task_data):
            continue

        logger.info("Running automation rule '%s' on task %s", rule.get("name", "?"), task_id)
        for action in rule.get("actions", []):
            await _execute_action(db, board_id, task_id, action, task_data)


def _matches_conditions(conditions: dict, task: dict) -> bool:
    """Check if a task matches all conditions in a rule."""
    for key, expected in conditions.items():
        actual = _get_task_value(task, key)
        if expected is None and actual is not None:
            return False
        if expected is not None and actual != expected:
            return False
    return True


def _get_task_value(task: dict, key: str) -> Any:
    """Get a value from task data using a condition key."""
    mapping = {
        "has_tag": lambda: task.get("tags", ""),
        "assignee_is": lambda: task.get("assigned_to", task.get("assignedTo", "")),
        "column_is": lambda: task.get("column_name", task.get("column", "")),
        "priority_is": lambda: task.get("priority", ""),
        "flaky_test": lambda: task.get("flaky_test_name", task.get("flakyTestName", "")),
        "coverage_file": lambda: task.get("coverage_file", task.get("coverageFile", "")),
    }
    handler = mapping.get(key)
    if handler:
        val = handler()
        if key == "has_tag":
            return expected in val.split(",") if isinstance(expected := None if key == "has_tag" else None, str) else False
        return val
    return task.get(key)


async def _execute_action(db: Any, board_id: str, task_id: str, action: dict, task: dict):
    """Execute a single automation action."""
    atype = action.get("type", "")
    params = action.get("params", {})

    try:
        if atype == "assign":
            assignee = params.get("assignee", "")
            if assignee:
                await db.execute("UPDATE kanban_tasks SET assigned_to=$1, updated_at=NOW() WHERE id=$2", assignee, task_id)

        elif atype == "set_priority":
            priority = params.get("priority", "p2")
            await db.execute("UPDATE kanban_tasks SET priority=$1, updated_at=NOW() WHERE id=$2", priority, task_id)

        elif atype == "add_label":
            tag = params.get("tag", "")
            if tag:
                current = await db.fetchval("SELECT tags FROM kanban_tasks WHERE id=$1", task_id)
                tags_set = set(t.strip() for t in (current or "").split(",") if t.strip())
                if tag not in tags_set:
                    tags_set.add(tag)
                    await db.execute("UPDATE kanban_tasks SET tags=$1, updated_at=NOW() WHERE id=$2",
                                     ",".join(tags_set), task_id)

        elif atype == "move":
            column = params.get("column", "")
            if column:
                await db.execute("UPDATE kanban_tasks SET column_name=$1, updated_at=NOW() WHERE id=$2", column, task_id)

        elif atype == "create_task":
            title = params.get("title", f"Auto-created from {task.get('title', '?')}")
            tags = params.get("tags", "auto-created")
            await db.execute(
                "INSERT INTO kanban_tasks (board_id, title, column_name, tags) VALUES ($1, $2, 'backlog', $3)",
                board_id, title, tags,
            )

        elif atype in ("notify:slack", "notify:webhook"):
            # Log the notification — actual delivery handled by send_message tool
            channel = params.get("channel", "#general")
            message = params.get("message", "").replace("{{title}}", task.get("title", ""))
            await db.execute(
                "INSERT INTO notifications (channel, recipient, subject, body, status) VALUES ($1, $2, $3, $4, 'pending')",
                "slack" if atype == "notify:slack" else "webhook", channel, "Automation notification", message,
            )

        logger.debug("Executed automation action %s on task %s", atype, task_id)

    except Exception as e:
        logger.warning("Automation action %s failed on task %s: %s", atype, task_id, e)
