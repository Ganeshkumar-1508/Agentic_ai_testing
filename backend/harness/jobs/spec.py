"""JobSpec — the handoff payload from the chat surface to the orchestrator.

The chat Role is read-only. The ONE mutation it can perform is producing
a `JobSpec` via the `submit_job` tool. The `JobSpec` is persisted, the
orchestrator picks it up, and a `Run` is created. The chat Role never
executes the orchestrator's work itself — it just submits and returns
the `run_id` so the user can track progress on the dashboard.

This is the data shape that connects two surfaces (chat → orchestrator)
without either one knowing about the other's internals.

C08 (per docs/2026-06-21-architecture-decision-tree.md#c08):
  - Q4: ``context`` is a Pydantic ``JobContext`` (typed sub-model
    with ``extra='allow'``) instead of a raw ``dict``.
  - Q3: ``context.test_config`` is the typed sub-model for the
    from-requirements extras.
  - Q9: ``JobSpecStore`` gains 7 new methods (list_by_session,
    get_status, cancel, pause, resume, add_comment, get_output).
  - Q5: All submission paths (chat, the chat's `submit_job`
    tool, the Job Detail page's resume path, external
    integrations via the HTTP surface) now route through
    ``jobs.submitter.submit_job_to_orchestrator`` for
    durable persistence.

  - Q7 step 2: the legacy ``/api/agent/run``,
    ``/api/delegate``, and ``/api/pipeline/from-requirements``
    endpoints have been hard-deleted. New callers must use
    ``POST /api/jobs`` (the canonical surface).

Persistence: the chat's `submit_job` handler calls
`set_job_spec_store(store)` once at app startup. The handler then
calls `_job_spec_store().save(record)` so the spec is durable
across restarts. The orchestrator calls `set_proposal_store(store)`
the same way and uses it for Tier-2 review-queue work. Both
surfaces are protocol-bound; neither reaches into the other's
internals.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# Module-level store references. Set once at app startup by
# `api/main.py`. If unset, the dispatcher's `submit_job` handler
# still builds a `JobSpec` in memory — it just can't persist it.
# The orchestrator's tier-2 path behaves the same way: the
# proposal is built in memory but never reaches the review queue.
_deps_ref: dict[str, Any] = {}


def set_job_spec_store(store: "JobSpecStore") -> None:
    """Inject the `JobSpecStore` at app startup."""
    _deps_ref["job_spec_store"] = store


def set_proposal_store(store: "ProposalStore") -> None:
    """Inject the `ProposalStore` at app startup."""
    _deps_ref["proposal_store"] = store


def _job_spec_store() -> "JobSpecStore | None":
    return _deps_ref.get("job_spec_store")


def _proposal_store() -> "ProposalStore | None":
    return _deps_ref.get("proposal_store")


def to_record(spec: "JobSpec") -> "JobSpecRecord":
    """Convert an in-memory `JobSpec` to a `JobSpecRecord` for storage."""
    from harness.store.protocols import JobSpecRecord
    # Pydantic → dict for storage. JobContext.model_dump keeps
    # ``extra`` keys.
    context_payload: Any
    if hasattr(spec.context, "model_dump"):
        context_payload = spec.context.model_dump()
    elif isinstance(spec.context, dict):
        context_payload = dict(spec.context)
    else:
        context_payload = {}
    return JobSpecRecord(
        spec_id=spec.spec_id,
        run_id=spec.run_id,
        source=spec.source,
        prompt=spec.prompt,
        repo_url=spec.repo_url,
        branch=spec.branch,
        sha=spec.sha,
        tier=spec.tier,
        capabilities=list(spec.capabilities),
        approval=dict(spec.approval),
        context=context_payload,
        status="pending",
        created_at=spec.created_at,
    )


# Default capabilities for an autonomous test-runner job. The orchestrator
# can do anything in this set. Tier-2 jobs are reviewed before merging;
# tier-3 jobs are human-authored and never auto-merged.
DEFAULT_CAPABILITIES: tuple[str, ...] = (
    "read_code",
    "write_test_files",
    "edit_existing_tests",
    "run_tests",
    "open_pr",
    "comment_on_pr",
)


# ---------------------------------------------------------------------------
# C08 Q3 + Q4: typed JobContext with extra='allow'
# ---------------------------------------------------------------------------


# Pydantic is the typing/validation layer for JobContext. If
# pydantic isn't installed in some lightweight deployment, we
# fall back to a plain dataclass with similar semantics. The
# "extra='allow'" behavior is replicated manually for the fallback.
try:
    from pydantic import BaseModel, ConfigDict
    _HAVE_PYDANTIC = True
except ImportError:  # pragma: no cover
    _HAVE_PYDANTIC = False


if _HAVE_PYDANTIC:

    class TestConfig(BaseModel):
        """Typed sub-model for from-requirements test config (C08 Q3).

        The 30+ fields of ``PipelineFromRequirements`` (e.g.
        ``pre_commands``, ``cache_directories``, ``browser``,
        ``os``, ``runtime_version``) live here. The orchestrator
        ignores this — it's for the test runner downstream.
        """
        model_config = ConfigDict(extra="allow")

        pre_commands: list[str] = []
        post_commands: list[str] = []
        cache_directories: list[str] = []
        browser: str = ""
        os: str = ""
        runtime_version: str = ""
        timeout_seconds: int = 0
        parallel_jobs: int = 1
        retry_count: int = 0
        tags: list[str] = []
        # Anything else the from-requirements flow adds is allowed
        # via ``extra="allow"`` so adding a new field doesn't
        # require a migration.

    class JobContext(BaseModel):
        """Typed context payload for a JobSpec (C08 Q4).

        The 4 well-known fields are typed; unknown fields are
        allowed via ``extra="allow"`` so the chat can keep
        passing arbitrary context without schema migrations.

        The orchestrator only sees ``JobSpec``; ``test_config``
        is opaque to it. The test runner downstream unpacks it.
        """
        model_config = ConfigDict(extra="allow")

        session_id: str | None = None
        agent_id: str | None = None
        test_config: TestConfig | None = None
        request_metadata: dict[str, Any] | None = None

        def to_payload(self) -> dict[str, Any]:
            """Return a dict for storage (used by ``to_record``)."""
            return self.model_dump()

else:
    # Plain-dataclass fallback. Mirrors the Pydantic shape
    # approximately. This path is exercised only if pydantic
    # isn't installed — production has it.

    @dataclass
    class TestConfig:  # type: ignore[no-redef]
        pre_commands: list[str] = field(default_factory=list)
        post_commands: list[str] = field(default_factory=list)
        cache_directories: list[str] = field(default_factory=list)
        browser: str = ""
        os: str = ""
        runtime_version: str = ""
        timeout_seconds: int = 0
        parallel_jobs: int = 1
        retry_count: int = 0
        tags: list[str] = field(default_factory=list)
        extras: dict[str, Any] = field(default_factory=dict)

        def to_payload(self) -> dict[str, Any]:
            base = {
                "pre_commands": list(self.pre_commands),
                "post_commands": list(self.post_commands),
                "cache_directories": list(self.cache_directories),
                "browser": self.browser,
                "os": self.os,
                "runtime_version": self.runtime_version,
                "timeout_seconds": self.timeout_seconds,
                "parallel_jobs": self.parallel_jobs,
                "retry_count": self.retry_count,
                "tags": list(self.tags),
            }
            base.update(self.extras)
            return base

    @dataclass
    class JobContext:  # type: ignore[no-redef]
        session_id: str | None = None
        agent_id: str | None = None
        test_config: TestConfig | None = None
        request_metadata: dict[str, Any] | None = None
        extras: dict[str, Any] = field(default_factory=dict)

        def to_payload(self) -> dict[str, Any]:
            base: dict[str, Any] = {}
            if self.session_id is not None:
                base["session_id"] = self.session_id
            if self.agent_id is not None:
                base["agent_id"] = self.agent_id
            if self.test_config is not None:
                base["test_config"] = self.test_config.to_payload()
            if self.request_metadata is not None:
                base["request_metadata"] = dict(self.request_metadata)
            base.update(self.extras)
            return base


def _build_context(
    *,
    session_id: str = "",
    agent_id: str = "",
    test_config: Any = None,
    request_metadata: dict[str, Any] | None = None,
) -> Any:
    """Build a :class:`JobContext` from kwargs (Pydantic or fallback)."""
    return JobContext(
        session_id=session_id or None,
        agent_id=agent_id or None,
        test_config=test_config,
        request_metadata=request_metadata,
    )


@dataclass
class JobSpec:
    """The chat-to-orchestrator handoff payload."""
    spec_id: str
    run_id: str
    source: str
    prompt: str
    repo_url: str = ""
    branch: str = "main"
    sha: str = ""
    tier: int = 1
    capabilities: list[str] = field(default_factory=list)
    approval: dict[str, Any] = field(default_factory=dict)
    backend_type: str = "local"
    # C08 Q4: ``context`` is now a typed :class:`JobContext` (or
    # a dict for legacy callers). The ``to_dict`` / ``from_dict``
    # methods handle both shapes for backwards compat.
    context: Any = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_chat_submission(
        cls,
        *,
        prompt: str,
        repo_url: str = "",
        branch: str = "main",
        tier: int = 1,
        capabilities: list[str] | None = None,
        session_id: str = "",
        agent_id: str = "",
        approval: dict[str, Any] | None = None,
        backend_type: str = "local",
    ) -> "JobSpec":
        """Build a `JobSpec` from a `submit_job` tool call."""
        return cls(
            spec_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            source="chat-submission",
            prompt=prompt,
            repo_url=repo_url,
            branch=branch or "main",
            tier=tier,
            capabilities=list(capabilities) if capabilities is not None else list(DEFAULT_CAPABILITIES),
            approval=approval or {"mode": "review_queue", "destination": "github_pr"},
            backend_type=backend_type,
            context=_build_context(
                session_id=session_id, agent_id=agent_id,
            ),
        )

    def attach_run_id(self, run_id: str) -> None:
        """Called by the orchestrator when it accepts the spec."""
        self.run_id = run_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage or wire transfer."""
        if hasattr(self.context, "to_payload"):
            context_payload = self.context.to_payload()
        elif isinstance(self.context, dict):
            context_payload = dict(self.context)
        else:
            context_payload = {}
        return {
            "spec_id": self.spec_id,
            "run_id": self.run_id,
            "source": self.source,
            "prompt": self.prompt,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "sha": self.sha,
            "tier": self.tier,
            "capabilities": list(self.capabilities),
            "approval": dict(self.approval),
            "backend_type": self.backend_type,
            "context": context_payload,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobSpec":
        # Re-hydrate context. If we get a dict back, build a
        # JobContext (Pydantic) or just use the dict (fallback).
        ctx_raw = data.get("context")
        if isinstance(ctx_raw, dict) and _HAVE_PYDANTIC:
            try:
                ctx_obj: Any = JobContext.model_validate(ctx_raw)
            except Exception:
                ctx_obj = ctx_raw
        else:
            ctx_obj = ctx_raw if ctx_raw is not None else {}
        return cls(
            spec_id=data.get("spec_id") or str(uuid.uuid4()),
            run_id=data.get("run_id", ""),
            source=data.get("source", "chat-submission"),
            prompt=data.get("prompt", ""),
            repo_url=data.get("repo_url", ""),
            branch=data.get("branch", "main"),
            sha=data.get("sha", ""),
            tier=int(data.get("tier", 1)),
            capabilities=list(data.get("capabilities") or []),
            approval=dict(data.get("approval") or {}),
            backend_type=data.get("backend_type", "local"),
            context=ctx_obj,
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc)
            ),
        )


__all__ = [
    "JobSpec", "DEFAULT_CAPABILITIES", "JobContext", "TestConfig",
    "set_job_spec_store", "set_proposal_store", "to_record",
]

