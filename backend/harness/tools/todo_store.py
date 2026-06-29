"""In-memory todo store for task planning."""

from __future__ import annotations

import json
from typing import Any

_VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


class TodoStore:
    def __init__(self):
        self._items: list[dict[str, str]] = []

    def write(self, todos: list[dict[str, Any]], merge: bool = False) -> list[dict[str, str]]:
        if not merge:
            self._items = [self._validate(t) for t in self._dedupe(todos)]
        else:
            existing = {item["id"]: item for item in self._items}
            for t in self._dedupe(todos):
                tid = str(t.get("id", "")).strip()
                if not tid:
                    continue
                if tid in existing:
                    if t.get("content"):
                        existing[tid]["content"] = str(t["content"]).strip()
                    if t.get("status"):
                        s = str(t["status"]).strip().lower()
                        if s in _VALID_STATUSES:
                            existing[tid]["status"] = s
                else:
                    existing[tid] = self._validate(t)
                    self._items.append(existing[tid])
            seen = set()
            rebuilt = []
            for item in self._items:
                cur = existing.get(item["id"], item)
                if cur["id"] not in seen:
                    rebuilt.append(cur)
                    seen.add(cur["id"])
            self._items = rebuilt
        return self.read()

    def read(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._items]

    def has_items(self) -> bool:
        return bool(self._items)

    def format_for_injection(self) -> str | None:
        active = [i for i in self._items if i["status"] in {"pending", "in_progress"}]
        if not active:
            return None
        markers = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]", "cancelled": "[~]"}
        lines = ["[Active task list preserved across compression]"]
        for item in active:
            m = markers.get(item["status"], "[?]")
            lines.append(f"- {m} {item['id']}. {item['content']} ({item['status']})")
        return "\n".join(lines)

    @staticmethod
    def _validate(item: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(item.get("id", "")).strip() or "?",
            "content": str(item.get("content", "")).strip() or "(no description)",
            "status": str(item.get("status", "pending")).strip().lower() if str(item.get("status", "")).strip().lower() in _VALID_STATUSES else "pending",
        }

    @staticmethod
    def _dedupe(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, int] = {}
        for i, t in enumerate(todos):
            tid = str(t.get("id", "")).strip() or "?"
            seen[tid] = i
        return [todos[i] for i in sorted(seen.values())]
