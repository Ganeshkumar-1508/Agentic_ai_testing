"""AgentProtocol — structural type for the Agent class.

Mixins are loosely coupled (no shared base class, no `__init__` in mixins).
This Protocol declares the attributes every mixin expects on `self`, so
mypy/IDEs catch missing-attribute bugs at class-definition time rather
than at first call.

To use: `class Agent(AgentProtocol, InterruptsMixin, ...): ...`

The Protocol is structural — it doesn't require `Agent` to inherit from
it, but if it doesn't, mypy will flag any method that uses an attribute
not declared here. This is the contract every mixin assumes.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Protocol, runtime_checkable

from harness.delegation import DelegationContext
from harness.events import EventBus
from harness.llm import LLMRouter
from harness.mcp.client import MCPClient
from harness.memory.store import PersistentStore
from harness.permissions.manager import PermissionManager


__all__ = ["AgentProtocol"]


@runtime_checkable
class AgentProtocol(Protocol):
    """The shape every mixin assumes `self` has. Set in `Agent.__init__`."""

    # ----- deps -----
    _deps: Any  # AgentDependencies; structural only
    llm: LLMRouter
    store: PersistentStore | None
    mcp: MCPClient | None
    permissions: PermissionManager
    backend_factory: Any = None

    # ----- event bus -----
    _event_bus: EventBus

    # ----- interrupt (lives on Agent, not the mixin) -----
    _interrupt: threading.Event

    # ----- message state -----
    _messages: list
    mode: str
    _allowed_tools: list[str] | None
    max_tool_rounds: int
    system_prompt: str
    session_id: str
    model_override: str | None
    sandbox: Any | None
    context_compressor: Any

    # ----- delegation -----
    delegation: DelegationContext

    # ----- reflexion (used by ReflexionMixin + ReflexionMemory) -----
    _reflection_count: int
    _reflection_per_tool: dict[str, int]
    _reflexion_memory: Any  # ReflexionMemory (avoid circular import)
    _last_reflection: str | None
    _last_reflection_errors: list[tuple[str, str]]

    # ----- checkpoint -----
    _checkpoint_mgr: Any

    # ----- tool search -----
    _core_tool_names: set[str]
    _discovered_tool_names: set[str]
    _discovered_tool_schemas: list[dict[str, Any]]
