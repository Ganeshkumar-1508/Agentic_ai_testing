"""AgentDependencies — the single seam between Agent and infrastructure.

One object holds every external dependency the Agent needs: LLM, store,
permissions, MCP, sandbox, and the shared EventBus. Tests construct a
minimal AgentDependencies; production code in `api/main.py` builds one
with the full stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from harness.llm import LLMRouter
from harness.mcp.client import MCPClient
from harness.memory.store import PersistentStore
from harness.permissions.manager import PermissionManager
from harness.events import EventBus


__all__ = ["AgentDependencies"]


@dataclass
class AgentDependencies:
    """All infrastructure dependencies the Agent needs. One object, one seam."""
    llm: LLMRouter
    store: PersistentStore  # required — stores interactions and context
    permissions: PermissionManager
    # Database — the primary data store. Replaces the Database._instance
    # singleton pattern. Tools and modules that need DB access receive it
    # via this seam, not via class-level global state.
    db: Any = None  # Database | None — Any to avoid circular import
    mcp: MCPClient | None = None
    # Shared EventBus — cross-cutting sinks (TraceCallback, StreamCallback,
    # LogSink) are registered on it once at app startup. The Agent emits
    # trace + stream events through this bus.
    event_bus: EventBus | None = None
    # StoreRegistry — composable store interfaces (events, sessions, agents, etc.)
    store_registry: Any = None
