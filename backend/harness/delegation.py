"""DelegationContext — explicit delegation identity.

Replaces the current pattern of setting _delegate_depth, _subagent_id, and
_parent_subagent_id as magic attributes on the Agent object via setattr.
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DelegationContext:
    """Explicit delegation identity. Created at spawn, passed to Agent.__init__.
    Replaces _delegate_depth, _subagent_id, _parent_subagent_id magic attrs.
    """
    subagent_id: str = ""
    parent_id: str | None = None
    depth: int = 0
    max_depth: int = 5
    role: str = "leaf"
    model_override: str | None = None
    allowed_tools: list[str] | None = None
    budget_policy: Any = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    # NEW: track agent_factory kwargs that were set via setattr
    system_prompt_override: str | None = None
    backend_factory: Any = None
    session_id: str = ""
    volume_key: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def cancel(self, reason: str = "parent cancelled") -> None:
        self.cancel_event.set()
