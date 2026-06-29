from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional
from contextlib import asynccontextmanager


@dataclass
class ContextScope:
    run_id: str
    session_id: str
    agent_id: str = ""
    parent_id: Optional[str] = None
    labels: dict[str, str] = field(default_factory=dict)


class ScopeManager:
    def __init__(self) -> None:
        self._stack: ContextVar[tuple[ContextScope, ...]] = ContextVar("_scope_stack", default=())

    @property
    def current(self) -> Optional[ContextScope]:
        stack = self._stack.get()
        return stack[-1] if stack else None

    def push(self, scope: ContextScope) -> None:
        self._stack.set(self._stack.get() + (scope,))

    def pop(self) -> None:
        stack = self._stack.get()
        if stack:
            self._stack.set(stack[:-1])

    @asynccontextmanager
    async def scope(
        self,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: str = "",
        parent_id: Optional[str] = None,
        labels: Optional[dict[str, str]] = None,
    ) -> AsyncIterator[ContextScope]:
        parent = self.current
        if parent:
            scope = ContextScope(
                run_id=run_id or parent.run_id,
                session_id=session_id or parent.session_id,
                agent_id=agent_id or str(uuid.uuid4()),
                parent_id=parent.agent_id or None,
                labels={**parent.labels, **(labels or {})},
            )
        else:
            scope = ContextScope(
                run_id=run_id or str(uuid.uuid4()),
                session_id=session_id or str(uuid.uuid4()),
                agent_id=agent_id or str(uuid.uuid4()),
                parent_id=parent_id,
                labels=labels or {},
            )
        self.push(scope)
        try:
            yield scope
        finally:
            self.pop()


manager = ScopeManager()


def get_run_context() -> ContextScope | None:
    return manager.current
