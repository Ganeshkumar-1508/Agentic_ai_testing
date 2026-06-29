"""harness.agent — Agent class (single-file query engine).

Public surface (import from here, not from submodules):
    from harness.agent import Agent, AgentDependencies, AgentProtocol
    from harness.agent import validate_subagent_output, curate_subagent_context

Standalone helpers (not inherited mixins):
    - curate_subagent_context: pre-fill context for delegate_task
    - validate_subagent_output: sanity-check subagent output

The Agent class is a single unified class combining all agent execution
logic (interrupts, emitters, tool dispatch, reflexion, run loop) that
was previously spread across 6 mixin files.

See `protocols.AgentProtocol` for the structural typing contract.
The package is PEP 561 compliant (`py.typed` marker included).
"""
from __future__ import annotations

from harness.agent.agent import Agent
from harness.agent.curation import curate_subagent_context
from harness.agent.deps import AgentDependencies
from harness.agent.protocols import AgentProtocol
from harness.agent.reflexion_memory import ReflexionMemory
from harness.agent.validation import ValidationResult, validate_subagent_output


__all__ = [
    "Agent",
    "AgentDependencies",
    "AgentProtocol",
    "ReflexionMemory",
    "ValidationResult",
    "curate_subagent_context",
    "validate_subagent_output",
]
