"""In-memory store adapters for testing — no Postgres required.

Implements the Protocol interfaces from harness/store/protocols.py.
Two adapters = a real seam (not just a hypothetical one).
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from harness.store.protocols import (
    AgentDef,
    EventStore,
    RunState,
    SessionNode,
    StreamEvent,
)


class InMemoryEventStore:
    """In-memory event stream. Thread-safe for single-threaded asyncio tests."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._counter: int = 0

    async def append(
        self, session_id: str, event_type: str, payload: dict[str, Any], *,
        agent_id: str | None = None, subagent_id: str | None = None,
        parent_id: str | None = None,
    ) -> int:
        self._counter += 1
        self._events.append({
            "id": self._counter,
            "session_id": session_id,
            "event_type": event_type,
            "payload": copy.deepcopy(payload),
            "agent_id": agent_id,
            "subagent_id": subagent_id,
            "parent_id": parent_id,
            "created_at": datetime.now(timezone.utc),
        })
        return self._counter

    async def poll(
        self, session_id: str, after_id: int = 0, limit: int = 100,
    ) -> list[StreamEvent]:
        matching = [
            e for e in self._events
            if e["session_id"] == session_id and e["id"] > after_id
        ]
        return [self._to_event(e) for e in matching[:limit]]

    async def replay(
        self, session_id: str, event_types: list[str] | None = None,
        limit: int = 1000,
    ) -> list[StreamEvent]:
        matching = [
            e for e in self._events if e["session_id"] == session_id
        ]
        if event_types:
            matching = [e for e in matching if e["event_type"] in event_types]
        return [self._to_event(e) for e in matching[-limit:]]

    async def count(self, session_id: str) -> int:
        return sum(1 for e in self._events if e["session_id"] == session_id)

    def _to_event(self, e: dict[str, Any]) -> StreamEvent:
        return StreamEvent(
            id=e["id"],
            session_id=e["session_id"],
            event_type=e["event_type"],
            payload=copy.deepcopy(e["payload"]),
            parent_id=e["parent_id"],
            agent_id=e["agent_id"],
            subagent_id=e["subagent_id"],
            created_at=e["created_at"],
        )


class InMemorySessionStore:
    """In-memory session tree."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._token_usage: list[dict[str, Any]] = []

    async def create(
        self, session_id: str, parent_id: str | None = None, *,
        status: str = "running", depth: int = 0,
        agent_role: str = "leaf", goal: str = "",
        model: str = "",
    ) -> SessionNode:
        now = datetime.now(timezone.utc)
        self._sessions[session_id] = {
            "id": session_id,
            "parent_session_id": parent_id,
            "status": status,
            "depth": depth,
            "agent_role": agent_role,
            "goal": goal,
            "model": model,
            "total_tokens": 0,
            "total_cost": 0.0,
            "created_at": now,
            "ended_at": None,
        }
        return SessionNode(
            session_id=session_id, parent_id=parent_id, status=status,
            depth=depth, agent_role=agent_role, goal=goal, model=model,
        )

    async def get(self, session_id: str) -> SessionNode | None:
        row = self._sessions.get(session_id)
        if not row:
            return None
        return SessionNode(
            session_id=row["id"],
            parent_id=row["parent_session_id"],
            status=row["status"],
            depth=row["depth"] or 0,
            agent_role=row["agent_role"] or "leaf",
            goal=row["goal"] or "",
            model=row["model"] or "",
            total_tokens=row["total_tokens"] or 0,
            total_cost=float(row["total_cost"] or 0),
            created_at=row["created_at"],
            ended_at=row["ended_at"],
        )

    async def update(self, session_id: str, **kwargs: Any) -> None:
        row = self._sessions.get(session_id)
        if row:
            row.update(kwargs)

    async def get_children(self, session_id: str) -> list[SessionNode]:
        result = []
        for row in self._sessions.values():
            if row["parent_session_id"] == session_id:
                result.append(await self.get(row["id"]))
        return result

    async def get_tree(self, session_id: str) -> list[SessionNode]:
        result = []
        stack = [session_id]
        seen = set()
        while stack:
            sid = stack.pop()
            if sid in seen:
                continue
            seen.add(sid)
            node = await self.get(sid)
            if node:
                result.append(node)
            for row in self._sessions.values():
                if row["parent_session_id"] == sid:
                    stack.append(row["id"])
        return result

    async def add_token_usage(
        self, session_id: str, prompt_tokens: int,
        completion_tokens: int, cost_usd: float,
        model: str = "",
    ) -> None:
        self._token_usage.append({
            "session_id": session_id,
            "model": model,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "estimated_cost_usd": round(cost_usd, 6),
        })
        row = self._sessions.get(session_id)
        if row:
            row["total_tokens"] = (row.get("total_tokens", 0)
                                   + prompt_tokens + completion_tokens)
            row["total_cost"] = (row.get("total_cost", 0.0) + cost_usd)
