"""Jobs — the chat-to-orchestrator handoff module.

`JobSpec` is the payload that the chat Role's `submit_job` tool produces
and the orchestrator consumes. The chat Role is read-only; this is its
one allowed mutation.
"""
from __future__ import annotations

from .spec import DEFAULT_CAPABILITIES, JobSpec

__all__ = ["JobSpec", "DEFAULT_CAPABILITIES"]
