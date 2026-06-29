"""RecoveryConfig — per-agent recovery strategy settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecoveryConfig:
    """Controls how an agent recovers from tool and LLM failures.

    Applied per-agent. Set via ``Agent(recovery=RecoveryConfig(...))``
    or loaded from Role YAML.

    Hermes multi-layer pattern:
      Layer 1: tool_retry       — retry transient tool errors with backoff
      Layer 2: circuit_breaker  — provider-level (CLOSED/OPEN/HALF_OPEN)
      Layer 3: credential_rotation — rotate API keys on 429
      Layer 4: transport_recovery — recreate client connections
      Layer 5: provider_failover   — fallback to cheaper model
      Layer 6: replan            — agent tries alternative approach
      Layer 7: context_compact   — recover from prompt_too_long
    """
    # Layer 1: tool-level retry
    tool_retry_enabled: bool = True
    tool_max_retries: int = 2
    tool_retry_delay: float = 0.5

    # Layer 6: replan on persistent tool failure
    replan_enabled: bool = True
    replan_max_attempts: int = 1
    replan_prompt: str = "The previous approach failed. Try a different approach."

    # Layer 7: context compaction
    compact_on_overflow: bool = True

    # Which error types trigger retry vs replan vs degrade
    retry_on: tuple[str, ...] = (
        "transient", "timeout", "rate_limit", "network",
    )
    replan_on: tuple[str, ...] = (
        "tool_error", "validation", "bad_request",
    )
    escalate_on: tuple[str, ...] = (
        "permission_denied", "budget_exceeded", "auth",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_retry_enabled": self.tool_retry_enabled,
            "tool_max_retries": self.tool_max_retries,
            "replan_enabled": self.replan_enabled,
            "compact_on_overflow": self.compact_on_overflow,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> RecoveryConfig:
        if not d:
            return cls()
        return cls(
            tool_retry_enabled=d.get("tool_retry_enabled", True),
            tool_max_retries=d.get("tool_max_retries", 2),
            tool_retry_delay=d.get("tool_retry_delay", 0.5),
            replan_enabled=d.get("replan_enabled", True),
            replan_max_attempts=d.get("replan_max_attempts", 1),
            compact_on_overflow=d.get("compact_on_overflow", True),
        )
