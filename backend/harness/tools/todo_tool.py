"""Todo tool — lightweight task tracking for coordinator agents.

Agent writes/reads its own todo list to track progress during a session.
Not a kanban board — just a simple per-agent checklist.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)

_TODO_STORE: dict[str, list[dict]] = {}


def _get_store() -> list[dict]:
    from harness.context import manager as scope_manager
    scope = scope_manager.current
    sid = scope.session_id if scope else "default"
    if sid not in _TODO_STORE:
        _TODO_STORE[sid] = []
    return _TODO_STORE[sid]


class TodoTool(BaseTool):
    name = "todo"
    description = (
        "Track task progress during a session. "
        "Call with 'todos' to write/update items, or without to read the current list. "
        "Use this to plan what needs to be done and track what's complete."
    )
    default_level = "allow"
    capabilities = ["can_plan"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "List of {content, status} items. status: pending|in_progress|completed|cancelled",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                        },
                    },
                },
            },
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        todos = kwargs.get("todos", None)
        store = _get_store()

        if todos is not None:
            for t in todos:
                content = t.get("content", "")
                status = t.get("status", "pending")
                existing = next((x for x in store if x["content"] == content), None)
                if existing:
                    existing["status"] = status
                else:
                    store.append({"content": content, "status": status})

        return ToolResult(
            success=True,
            output=json.dumps({"todos": store}, indent=2),
            data={"todos": store},
        )


registry.register(TodoTool(), toolset="read")
