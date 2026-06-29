from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RunContext:
    """Immutable context passed through each Phase of a Run.

    Each Phase receives a RunContext and returns a new RunContext with
    its field populated. Fields are never mutated in place — use
    ``dataclasses.replace(ctx, field=value)`` to create the next version.

    Identity (set once by the orchestrator):
    """
    run_id: str
    session_id: str
    spec_id: str = ""
    repo_url: str = ""
    branch: str = ""
    goal: str = ""

    # Services (injected by orchestrator, read by phases):
    db: Any = None
    sandbox: Any = None
    orchestrator: Any = None  # phases that need broader state (spec, etc.)

    # Written by phases in sequence:
    board_id: str | None = None
    kg_ctx: Any = None
    worktree_path: str | None = None
    explore_findings: str = ""
    memory_block: str = ""
    coordinator_result: dict | None = None
    # FinalizeJobSpecPhase reads this to compute duration_s.
    # Set by the orchestrator at pipeline construction time
    # (before the first phase runs).
    run_started_at: str = ""

    # Error accumulation (read by orchestrator after all phases):
    errors: tuple[str, ...] = ()


class RunPhase(Protocol):
    """A single phase of the run lifecycle — testable in isolation.

    Each Phase transforms a RunContext and returns the new version.
    The orchestrator owns lifecycle (pause checkpoints, error handling);
    each Phase owns its domain logic.
    """
    phase_name: str
    can_skip: bool = False

    async def execute(self, ctx: RunContext) -> RunContext: ...
