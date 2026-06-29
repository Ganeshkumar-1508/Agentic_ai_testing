from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Protocol


def _to_dict(obj: Any, slots: tuple[str, ...]) -> dict:
    d = {}
    for s in slots:
        v = getattr(obj, s)
        if isinstance(v, datetime):
            v = v.isoformat()
        d[s] = v
    return d


# ── Store interfaces (Protocols) ─────────────────────────────────────────
# These define the seam between store users and store implementations.
# Add an in-memory adapter alongside the Postgres adapter to verify the
# seam is real (two adapters = real seam).

class EventStore(Protocol):
    """Interface for event stream storage."""
    async def append(self, session_id: str, event_type: str, payload: dict[str, Any], *,
                     agent_id: str | None = None, subagent_id: str | None = None,
                     parent_id: str | None = None) -> int: ...
    async def poll(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[StreamEvent]: ...
    async def replay(self, session_id: str, event_types: list[str] | None = None,
                     limit: int = 1000) -> list[StreamEvent]: ...
    async def count(self, session_id: str) -> int: ...


class SessionStore(Protocol):
    """Interface for session tree storage."""
    async def create(self, session_id: str, parent_id: str | None = None, *,
                     status: str = "running", depth: int = 0,
                     agent_role: str = "leaf", goal: str = "",
                     model: str = "") -> SessionNode: ...
    async def get(self, session_id: str) -> SessionNode | None: ...
    async def update(self, session_id: str, **kwargs: Any) -> None: ...
    async def get_children(self, session_id: str) -> list[SessionNode]: ...
    async def get_tree(self, session_id: str) -> list[SessionNode]: ...
    async def add_token_usage(self, session_id: str, prompt_tokens: int,
                              completion_tokens: int, cost_usd: float,
                              model: str = "") -> None: ...


class AgentStore(Protocol):
    """Interface for agent definition storage."""
    async def list_agents(self) -> list[AgentDef]: ...
    async def get_agent(self, role: str) -> AgentDef | None: ...
    async def upsert_agent(self, agent: AgentDef) -> None: ...
    async def delete_agent(self, role: str) -> None: ...
    async def resolve_by_trigger(self, query: str) -> list[AgentDef]: ...


class ArtifactStore(Protocol):
    """Interface for artifact storage."""
    async def store(self, session_id: str, path: str, content: str, *,
                    mime_type: str = "text/plain", description: str = "",
                    subagent_id: str | None = None) -> str: ...
    async def get(self, artifact_id: str) -> dict[str, Any] | None: ...
    async def list_by_session(self, session_id: str) -> list[dict[str, Any]]: ...
    async def delete(self, artifact_id: str) -> None: ...


class SkillStore(Protocol):
    """Interface for skill index storage."""
    async def list_skills(self, source: str | None = None) -> list[dict[str, Any]]: ...
    async def get_skill(self, name: str) -> dict[str, Any] | None: ...
    async def upsert_skill(self, name: str, description: str, path: str,
                           source: str = "user", tags: list[str] | None = None) -> None: ...
    async def track_usage(self, name: str, action: str = "use") -> None: ...


class RunStore(Protocol):
    """Interface for pipeline run storage."""
    async def create_run(self, run_id: str, session_id: str, task_type: str = "",
                         repo_url: str = "", branch: str = "",
                         sha: str = "") -> RunState: ...
    async def get_run(self, run_id: str) -> RunState | None: ...
    async def update_run(self, run_id: str, **kwargs: Any) -> None: ...
    async def list_runs(self, limit: int = 20, offset: int = 0,
                        status: str | None = None) -> list[RunState]: ...


_DEFAULTS: dict[str, object] = {
    "role": "", "version": 1, "description": "", "system_prompt": "",
    "allowed_tools": None, "allowed_skills": None,
    "model_primary": "", "model_fallback": "",
    "delegation_depth": 1, "delegation_role": "leaf",
    "triggers": None, "bash_constraints": None,
    "output_contract": "", "source": "builtin", "source_path": "",
}

class AgentDef:
    __slots__ = tuple(_DEFAULTS.keys())
    def __init__(self, **kwargs):
        for k in self.__slots__:
            v = kwargs.get(k, _DEFAULTS[k])
            if v is None and k in ("allowed_tools", "allowed_skills", "triggers"):
                v = []
            elif v is None and k == "bash_constraints":
                v = {}
            setattr(self, k, v)
    def to_dict(self): return _to_dict(self, self.__slots__)


class SessionNode:
    __slots__ = ("session_id","parent_id","status","depth","agent_role","goal","model","total_tokens","total_cost","created_at","ended_at")
    def __init__(self, session_id="", parent_id=None, status="running", depth=0, agent_role="leaf", goal="", model="", total_tokens=0, total_cost=0.0, created_at=None, ended_at=None):
        self.session_id=session_id; self.parent_id=parent_id; self.status=status; self.depth=depth
        self.agent_role=agent_role; self.goal=goal; self.model=model; self.total_tokens=total_tokens
        self.total_cost=total_cost; self.created_at=created_at; self.ended_at=ended_at
    def to_dict(self): return _to_dict(self, self.__slots__)


class StreamEvent:
    __slots__ = ("id","session_id","event_type","payload","parent_id","agent_id","subagent_id","created_at")
    def __init__(self, id=0, session_id="", event_type="", payload=None, parent_id=None, agent_id=None, subagent_id=None, created_at=None):
        self.id=id; self.session_id=session_id; self.event_type=event_type; self.payload=payload or {}
        self.parent_id=parent_id; self.agent_id=agent_id; self.subagent_id=subagent_id; self.created_at=created_at
    def to_dict(self): return _to_dict(self, self.__slots__)


class RunState:
    __slots__ = ("run_id","session_id","status","task_type","repo_url","branch","sha","error","created_at","completed_at",
                 "total_input_tokens","total_output_tokens","total_tokens","llm_call_count",
                 "lead_agent_tokens","subagent_tokens","model_name")
    def __init__(self, run_id="", session_id="", status="running", task_type="", repo_url="", branch="", sha="",
                 error=None, created_at=None, completed_at=None,
                 total_input_tokens=0, total_output_tokens=0, total_tokens=0, llm_call_count=0,
                 lead_agent_tokens=0, subagent_tokens=0, model_name=""):
        self.run_id=run_id; self.session_id=session_id; self.status=status; self.task_type=task_type
        self.repo_url=repo_url; self.branch=branch; self.sha=sha; self.error=error
        self.created_at=created_at; self.completed_at=completed_at
        self.total_input_tokens=total_input_tokens; self.total_output_tokens=total_output_tokens
        self.total_tokens=total_tokens; self.llm_call_count=llm_call_count
        self.lead_agent_tokens=lead_agent_tokens; self.subagent_tokens=subagent_tokens
        self.model_name=model_name
    def to_dict(self): return _to_dict(self, self.__slots__)


class JobSpecRecord:
    __slots__ = ("spec_id","run_id","source","prompt","repo_url","branch","sha","tier","capabilities","approval","context","status","error","created_at","started_at","completed_at","latest_run_status","latest_run_cost_usd","latest_run_duration_s")
    def __init__(self, spec_id="", run_id="", source="api", prompt="", repo_url="", branch="main", sha="", tier=1, capabilities=None, approval=None, context=None, status="pending", error=None, created_at=None, started_at=None, completed_at=None, latest_run_status=None, latest_run_cost_usd=None, latest_run_duration_s=None):
        self.spec_id=spec_id; self.run_id=run_id; self.source=source; self.prompt=prompt
        self.repo_url=repo_url; self.branch=branch; self.sha=sha; self.tier=tier
        self.capabilities=capabilities or []; self.approval=approval or {}; self.context=context or {}
        self.status=status; self.error=error; self.created_at=created_at; self.started_at=started_at
        self.completed_at=completed_at; self.latest_run_status=latest_run_status
        self.latest_run_cost_usd=latest_run_cost_usd; self.latest_run_duration_s=latest_run_duration_s
    def to_dict(self): return _to_dict(self, self.__slots__)


class JobSummary:
    __slots__ = ("spec_id","prompt","repo_url","tier","status","created_at","latest_run_id","latest_run_status","latest_run_started_at","latest_run_cost_usd","latest_run_duration_s")
    def __init__(self, spec_id="", prompt="", repo_url="", tier=1, status="pending", created_at=None, latest_run_id=None, latest_run_status=None, latest_run_started_at=None, latest_run_cost_usd=None, latest_run_duration_s=None):
        self.spec_id=spec_id; self.prompt=prompt; self.repo_url=repo_url; self.tier=tier; self.status=status
        self.created_at=created_at; self.latest_run_id=latest_run_id; self.latest_run_status=latest_run_status
        self.latest_run_started_at=latest_run_started_at; self.latest_run_cost_usd=latest_run_cost_usd
        self.latest_run_duration_s=latest_run_duration_s
    def to_dict(self): return _to_dict(self, self.__slots__)


class JobComment:
    __slots__ = ("comment_id","spec_id","author","body","kind","created_at")
    def __init__(self, comment_id="", spec_id="", author="", body="", kind="comment", created_at=None):
        self.comment_id=comment_id; self.spec_id=spec_id; self.author=author; self.body=body
        self.kind=kind; self.created_at=created_at
    def to_dict(self): return _to_dict(self, self.__slots__)


class JobOutput:
    __slots__ = ("spec_id","status","summary","artifacts","pr_url","cost_usd","duration_s","completed_at")
    def __init__(self, spec_id="", status="", summary="", artifacts=None, pr_url=None, cost_usd=None, duration_s=None, completed_at=None):
        self.spec_id=spec_id; self.status=status; self.summary=summary; self.artifacts=artifacts or []
        self.pr_url=pr_url; self.cost_usd=cost_usd; self.duration_s=duration_s; self.completed_at=completed_at
    def to_dict(self): return _to_dict(self, self.__slots__)


class ProposalRecord:
    __slots__ = ("proposal_id","spec_id","test_files","rationale","risk_score","status","reviewer","created_at","reviewed_at")
    def __init__(self, proposal_id="", spec_id="", test_files=None, rationale="", risk_score=0, status="pending_review", reviewer="", created_at=None, reviewed_at=None):
        self.proposal_id=proposal_id; self.spec_id=spec_id; self.test_files=test_files or []
        self.rationale=rationale; self.risk_score=risk_score; self.status=status; self.reviewer=reviewer
        self.created_at=created_at; self.reviewed_at=reviewed_at
    def to_dict(self): return _to_dict(self, self.__slots__)


# ── Job spec & proposal data types ─────────────────────────────────────────

class JobStatus:
    __slots__ = ("spec_id", "status", "started_at", "completed_at", "error", "run_id")
    def __init__(self, spec_id="", status="pending", started_at=None, completed_at=None, error=None, run_id=None):
        self.spec_id=spec_id; self.status=status; self.started_at=started_at
        self.completed_at=completed_at; self.error=error; self.run_id=run_id
    def to_dict(self): return _to_dict(self, self.__slots__)


# ── Store Protocols (re-added for test compatibility) ───────────────────────

class JobSpecStore(Protocol):
    """Protocol for job spec persistence (chat → orchestrator handoff)."""
    async def save(self, record: JobSpecRecord) -> None: ...
    async def get(self, spec_id: str) -> JobSpecRecord | None: ...
    async def update_status(self, spec_id: str, status: str, *,
                            started_at: datetime | None = None,
                            completed_at: datetime | None = None,
                            error: str | None = None,
                            run_id: str | None = None,
                            cost_usd: float | None = None,
                            duration_s: float | None = None) -> None: ...
    async def list_pending(self, limit: int = 50) -> list[JobSpecRecord]: ...
    async def list_by_session(self, session_id: str, *, limit: int = 20,
                              offset: int = 0) -> tuple[list[JobSummary], int]: ...
    async def list_recent(self, *, limit: int = 20,
                          offset: int = 0) -> tuple[list[JobSummary], int]: ...
    async def get_status(self, spec_id: str) -> JobStatus | None: ...
    async def cancel(self, spec_id: str) -> bool: ...
    async def pause(self, spec_id: str) -> bool: ...
    async def resume(self, spec_id: str) -> bool: ...


class ProposalStore(Protocol):
    """Protocol for tier-2 proposal persistence."""
    async def save(self, record: ProposalRecord) -> None: ...
    async def get(self, proposal_id: str) -> ProposalRecord | None: ...
    async def list_for_spec(self, spec_id: str) -> list[ProposalRecord]: ...
    async def list_pending(self, limit: int = 50) -> list[ProposalRecord]: ...
    async def mark_decision(self, proposal_id: str, decision: str, reviewer: str, *,
                            reviewed_at: datetime | None = None) -> None: ...
