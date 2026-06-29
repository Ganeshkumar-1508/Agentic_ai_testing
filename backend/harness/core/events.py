"""Unified typed event hierarchy for the TestAI harness.

Replaces 4 fragmented event paths with a single StreamEvent type hierarchy.
Each event is a frozen dataclass — type-safe, isinstance-dispatchable,
with no string-typed event type fields.

Pattern: OpenHarness StreamEvent architecture.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """Base marker for all stream events.

    Subclasses get free ``type_name`` (the class name) and ``to_dict()``
    for serialization.  Sinks dispatch via isinstance() — never check
    string-typed event type fields.
    """
    timestamp: float = field(default_factory=time.time, init=False, repr=False)

    @property
    def type_name(self) -> str:
        return type(self).__name__

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for SSE / JSON transport.
        Drops timestamp (injected by the transport layer) and
        flattens nested objects into dicts.
        """
        result: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name == "timestamp":
                continue
            val = getattr(self, f.name)
            if hasattr(val, "to_dict"):
                val = val.to_dict()
            elif isinstance(val, list):
                val = [
                    v.to_dict() if hasattr(v, "to_dict") else v
                    for v in val
                ]
            result[f.name] = val
        return result


# ── Agent lifecycle ──


@dataclass(frozen=True)
class AgentStarted(StreamEvent):
    agent_id: str
    input: str
    model: str
    mode: str


@dataclass(frozen=True)
class AgentCompleted(StreamEvent):
    agent_id: str
    output_preview: str
    rounds: int
    cancelled: bool = False


# ── Rounds / Tool Calling ──


@dataclass(frozen=True)
class RoundStarted(StreamEvent):
    round: int
    message_count: int


@dataclass(frozen=True)
class RoundCompleted(StreamEvent):
    round: int
    tool_calls: int
    session_id: str = ""


# ── LLM Calls ──


@dataclass(frozen=True)
class LLMCallStarted(StreamEvent):
    call_id: str
    model: str
    round: int
    session_id: str = ""


@dataclass(frozen=True)
class LLMCallCompleted(StreamEvent):
    call_id: str
    model: str
    round: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    session_id: str = ""


# ── Tool Execution ──


@dataclass(frozen=True)
class ToolExecutionStarted(StreamEvent):
    tool_name: str
    tool_input: str  # truncated string representation
    trace_id: str
    agent_id: str = ""
    session_id: str = ""
    llm_response_id: str = ""
    """ID grouping parallel tool calls from the same LLM response (OpenHands pattern)."""


@dataclass(frozen=True)
class ToolExecutionCompleted(StreamEvent):
    tool_name: str
    output_preview: str
    success: bool
    trace_id: str
    agent_id: str = ""
    is_error: bool = False
    session_id: str = ""
    llm_response_id: str = ""


@dataclass(frozen=True)
class ToolProgress(StreamEvent):
    """Mid-execution progress signal (Claude Code pendingProgress pattern).
    
    Emitted during tool execution for real-time UI updates — 
    e.g. bash stdout lines, file read chunks, download percentages.
    Bypasses ordered-result emission and appears immediately in the UI.
    """
    tool_name: str
    content: str
    trace_id: str
    agent_id: str = ""
    session_id: str = ""
    kind: str = "progress"
    """'progress', 'stdout', 'stderr', 'status' — UI rendering hint."""


# ── Delegation (subagents) ──


@dataclass(frozen=True)
class SubagentSpawned(StreamEvent):
    subagent_id: str
    goal: str
    depth: int
    role: str
    model: str | None = None
    parent_subagent_id: str | None = None
    session_id: str = ""


@dataclass(frozen=True)
class SubagentCompleted(StreamEvent):
    subagent_id: str
    status: str  # "ok" | "error" | "cancelled"
    duration_sec: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    session_id: str = ""


# ── Approvals / Permissions ──


@dataclass(frozen=True)
class ApprovalRequired(StreamEvent):
    approval_id: str
    tool_name: str
    tool_args: str  # string representation
    mode: str = ""


# ── Reflexion ──


@dataclass(frozen=True)
class ReflexionInjected(StreamEvent):
    round: int
    tool_count: int
    reflection_count: int


# ── Error / Status ──


@dataclass(frozen=True)
class ErrorEvent(StreamEvent):
    message: str
    recoverable: bool = True
    session_id: str = ""
    agent_id: str = ""
    category: str = ""
    error_type: str = ""
    stack: str = ""


@dataclass(frozen=True)
class AgentCancelled(StreamEvent):
    reason: str
    triggered_by: str = "system"  # "user" | "system" | "timeout"
    session_id: str = ""
    agent_id: str = ""


@dataclass(frozen=True)
class StatusEvent(StreamEvent):
    message: str


@dataclass(frozen=True)
class BudgetThrottled(StreamEvent):
    run_id: str
    prev_step: int
    new_step: int
    spent_usd: float
    soft_cap_usd: float
    hitl_active: bool
    sequential_active: bool
    cheaper_model_active: bool
    pause_requested: bool
    session_id: str = ""
    spec_id: str = ""


# ── Streaming / Chat ──


@dataclass(frozen=True)
class TokenGenerated(StreamEvent):
    agent_id: str
    content: str
    session_id: str = ""


@dataclass(frozen=True)
class ReasoningGenerated(StreamEvent):
    agent_id: str
    content: str
    session_id: str = ""



