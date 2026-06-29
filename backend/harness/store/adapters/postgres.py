from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from harness.memory.database import Database
from harness.store.protocols import (
    AgentDef,
    JobComment,
    JobOutput,
    JobSpecRecord,
    JobSummary,
    ProposalRecord,
    RunState,
    SessionNode,
    StreamEvent,
)

logger = logging.getLogger(__name__)


class PostgresEventStore:
    def __init__(self, db: Database):
        self._db = db

    async def append(self, session_id: str, event_type: str, payload: dict[str, Any], *, agent_id: str | None = None, subagent_id: str | None = None, parent_id: str | None = None) -> int:
        row = await self._db.fetchrow(
            "INSERT INTO stream_events (session_id, event_type, event_data, agent_id, subagent_id, parent_id) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            session_id, event_type, json.dumps(payload), agent_id, subagent_id, parent_id,
        )
        return row["id"] if row else 0

    async def poll(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[StreamEvent]:
        rows = await self._db.fetch(
            "SELECT id, session_id, event_type, event_data AS payload, parent_id, agent_id, subagent_id, created_at "
            "FROM stream_events WHERE session_id = $1 AND id > $2 ORDER BY id LIMIT $3",
            session_id, after_id, limit,
        )
        return [_row_to_event(r) for r in rows]

    async def replay(self, session_id: str, event_types: list[str] | None = None, limit: int = 1000) -> list[StreamEvent]:
        if event_types:
            rows = await self._db.fetch(
                "SELECT id, session_id, event_type, event_data AS payload, parent_id, agent_id, subagent_id, created_at "
                "FROM stream_events WHERE session_id = $1 AND event_type = ANY($2) ORDER BY id DESC LIMIT $3",
                session_id, event_types, limit,
            )
        else:
            rows = await self._db.fetch(
                "SELECT id, session_id, event_type, event_data AS payload, parent_id, agent_id, subagent_id, created_at "
                "FROM stream_events WHERE session_id = $1 ORDER BY id DESC LIMIT $2",
                session_id, limit,
            )
        return [_row_to_event(r) for r in rows]

    async def count(self, session_id: str) -> int:
        return await self._db.fetchval("SELECT COUNT(*) FROM stream_events WHERE session_id = $1", session_id) or 0


class PostgresSessionStore:
    def __init__(self, db: Database):
        self._db = db

    async def create(self, session_id: str, parent_id: str | None = None, *, status: str = "running", depth: int = 0, agent_role: str = "leaf", goal: str = "", model: str = "", backend_type: str = "local") -> SessionNode:
        await self._db.execute(
            "INSERT INTO sessions (id, status, depth, agent_role, goal, model, parent_session_id, started_at, backend_type) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8) ON CONFLICT (id) DO UPDATE SET status = $2",
            session_id, status, depth, agent_role, goal, model, parent_id, backend_type,
        )
        return SessionNode(session_id=session_id, parent_id=parent_id, status=status, depth=depth, agent_role=agent_role, goal=goal, model=model)

    async def get(self, session_id: str) -> SessionNode | None:
        row = await self._db.fetchrow(
            "SELECT id, parent_session_id, status, depth, agent_role, goal, model, total_tokens, total_cost, created_at, ended_at "
            "FROM sessions WHERE id = $1", session_id,
        )
        if not row:
            return None
        return SessionNode(
            session_id=row["id"],
            parent_id=row["parent_session_id"],
            status=row["status"],
            depth=row["depth"] or 0,
            agent_role=row["agent_role"] or "leaf",
            goal=row["goal"] or "",
            model=row["model"] or "",
            total_tokens=row["total_tokens"] or 0,
            total_cost=float(row["total_cost"] or 0),
            created_at=row["created_at"],
            ended_at=row["ended_at"],
        )

    async def update(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        sets = ", ".join(f"{k.replace(' ', '_')} = ${i+1}" for i, k in enumerate(kwargs))
        values = list(kwargs.values()) + [session_id]
        await self._db.execute(
            f"UPDATE sessions SET {sets}, updated_at = NOW() WHERE id = ${len(values)}",
            *values,
        )

    async def get_children(self, session_id: str) -> list[SessionNode]:
        rows = await self._db.fetch(
            "SELECT id, parent_session_id, status, depth, agent_role, goal, model, total_tokens, total_cost, created_at, ended_at "
            "FROM sessions WHERE parent_session_id = $1 ORDER BY created_at", session_id,
        )
        return [_row_to_session(r) for r in rows]

    async def get_tree(self, session_id: str) -> list[SessionNode]:
        rows = await self._db.fetch(
            "WITH RECURSIVE tree AS ("
            "  SELECT id, parent_session_id, status, depth, agent_role, goal, model, total_tokens, total_cost, created_at, ended_at "
            "  FROM sessions WHERE id = $1 "
            "  UNION ALL "
            "  SELECT s.id, s.parent_session_id, s.status, s.depth, s.agent_role, s.goal, s.model, s.total_tokens, s.total_cost, s.created_at, s.ended_at "
            "  FROM sessions s JOIN tree t ON s.parent_session_id = t.id"
            ") SELECT * FROM tree ORDER BY created_at",
            session_id,
        )
        return [_row_to_session(r) for r in rows]

    async def add_token_usage(self, session_id: str, prompt_tokens: int, completion_tokens: int, cost_usd: float, model: str = "") -> None:
        await self._db.execute(
            "INSERT INTO token_usage (session_id, model, input_tokens, output_tokens, estimated_cost_usd) "
            "VALUES ($1, $2, $3, $4, $5)",
            session_id, model, prompt_tokens, completion_tokens, round(cost_usd, 6),
        )
        await self._db.execute(
            "UPDATE sessions SET total_tokens = total_tokens + $1, total_cost = total_cost + $2, updated_at = NOW() WHERE id = $3",
            prompt_tokens + completion_tokens, cost_usd, session_id,
        )


class PostgresAgentStore:
    def __init__(self, db: Database):
        self._db = db

    async def list_agents(self) -> list[AgentDef]:
        rows = await self._db.fetch(
            "SELECT role, version, description, system_prompt, allowed_tools, allowed_skills, "
            "model_primary, model_fallback, delegation_depth, delegation_role, triggers, "
            "bash_constraints, output_contract, source, created_at, updated_at "
            "FROM agent_definitions ORDER BY source, role"
        )
        return [_row_to_agent(r) for r in rows]

    async def get_agent(self, role: str) -> AgentDef | None:
        row = await self._db.fetchrow(
            "SELECT role, version, description, system_prompt, allowed_tools, allowed_skills, "
            "model_primary, model_fallback, delegation_depth, delegation_role, triggers, "
            "bash_constraints, output_contract, source, created_at, updated_at "
            "FROM agent_definitions WHERE role = $1", role,
        )
        if not row:
            return None
        return _row_to_agent(row)

    async def upsert_agent(self, agent: AgentDef) -> None:
        await self._db.execute(
            "INSERT INTO agent_definitions (role, version, description, system_prompt, allowed_tools, "
            "allowed_skills, model_primary, model_fallback, delegation_depth, delegation_role, "
            "triggers, bash_constraints, output_contract, source, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW()) "
            "ON CONFLICT (role) DO UPDATE SET "
            "version = $2, description = $3, system_prompt = $4, allowed_tools = $5, "
            "allowed_skills = $6, model_primary = $7, model_fallback = $8, "
            "delegation_depth = $9, delegation_role = $10, triggers = $11, "
            "bash_constraints = $12, output_contract = $13, updated_at = NOW()",
            agent.role, agent.version, agent.description, agent.system_prompt,
            agent.allowed_tools, agent.allowed_skills, agent.model_primary, agent.model_fallback,
            agent.delegation_depth, agent.delegation_role, agent.triggers,
            json.dumps(agent.bash_constraints), agent.output_contract, agent.source,
        )

    async def delete_agent(self, role: str) -> None:
        await self._db.execute("DELETE FROM agent_definitions WHERE role = $1", role)

    async def resolve_by_trigger(self, query: str) -> list[AgentDef]:
        q = query.lower()
        rows = await self._db.fetch(
            "SELECT role, version, description, system_prompt, allowed_tools, allowed_skills, "
            "model_primary, model_fallback, delegation_depth, delegation_role, triggers, "
            "bash_constraints, output_contract, source, created_at, updated_at "
            "FROM agent_definitions WHERE triggers IS NOT NULL AND array_length(triggers, 1) > 0"
        )
        matched = []
        for r in rows:
            triggers = r["triggers"] or []
            if any(t.lower() in q for t in triggers):
                matched.append(_row_to_agent(r))
        return matched


class PostgresArtifactStore:
    def __init__(self, db: Database):
        self._db = db

    async def store(self, session_id: str, path: str, content: str, *, mime_type: str = "text/plain", description: str = "", subagent_id: str | None = None) -> str:
        artifact_id = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO artifacts (id, session_id, subagent_id, path, size_bytes, mime_type, description) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            artifact_id, session_id, subagent_id, path, len(content.encode("utf-8")), mime_type, description,
        )
        return artifact_id

    async def get(self, artifact_id: str) -> dict[str, Any] | None:
        row = await self._db.fetchrow(
            "SELECT id, session_id, subagent_id, path, size_bytes, mime_type, description, created_at "
            "FROM artifacts WHERE id = $1", artifact_id,
        )
        if not row:
            return None
        return dict(row)

    async def list_by_session(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self._db.fetch(
            "SELECT id, session_id, subagent_id, path, size_bytes, mime_type, description, created_at "
            "FROM artifacts WHERE session_id = $1 ORDER BY created_at", session_id,
        )
        return [dict(r) for r in rows]

    async def delete(self, artifact_id: str) -> None:
        await self._db.execute("DELETE FROM artifacts WHERE id = $1", artifact_id)


class PostgresSkillStore:
    def __init__(self, db: Database):
        self._db = db

    async def list_skills(self, source: str | None = None) -> list[dict[str, Any]]:
        if source:
            rows = await self._db.fetch(
                "SELECT name, description, path, source, category, tags, use_count, created_by, created_at, last_used_at "
                "FROM skills_index WHERE source = $1 ORDER BY name", source,
            )
        else:
            rows = await self._db.fetch(
                "SELECT name, description, path, source, category, tags, use_count, created_by, created_at, last_used_at "
                "FROM skills_index ORDER BY source, name"
            )
        return [dict(r) for r in rows]

    async def get_skill(self, name: str) -> dict[str, Any] | None:
        row = await self._db.fetchrow(
            "SELECT name, description, path, source, category, tags, use_count, created_by, created_at, last_used_at "
            "FROM skills_index WHERE name = $1", name,
        )
        if not row:
            return None
        return dict(row)

    async def upsert_skill(self, name: str, description: str, path: str, source: str = "user", tags: list[str] | None = None) -> None:
        await self._db.execute(
            "INSERT INTO skills_index (name, description, path, source, tags) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (name) DO UPDATE SET description = $2, path = $3, tags = $5, updated_at = NOW()",
            name, description, path, source, tags or [],
        )

    async def track_usage(self, name: str, action: str = "use") -> None:
        await self._db.execute(
            "UPDATE skills_index SET use_count = use_count + 1, last_used_at = NOW() WHERE name = $1",
            name,
        )


class PostgresRunStore:
    def __init__(self, db: Database):
        self._db = db

    async def create_run(self, run_id: str, session_id: str, task_type: str = "", repo_url: str = "", branch: str = "", sha: str = "", model_name: str = "") -> RunState:
        await self._db.execute(
            "INSERT INTO pipeline_runs (id, status, inputs) VALUES ($1, 'pending', $2)",
            run_id, json.dumps({"task_type": task_type, "session_id": session_id, "repo_url": repo_url, "branch": branch, "sha": sha, "model_name": model_name}),
        )
        return RunState(run_id=run_id, session_id=session_id, task_type=task_type, repo_url=repo_url, branch=branch, sha=sha, model_name=model_name)

    async def get_run(self, run_id: str) -> RunState | None:
        row = await self._db.fetchrow(
            "SELECT id, status, inputs, state, error, created_at, completed_at FROM pipeline_runs WHERE id = $1", run_id,
        )
        if not row:
            return None
        inputs = json.loads(row["inputs"]) if row.get("inputs") else {}
        return RunState(
            run_id=row["id"],
            session_id=inputs.get("session_id", ""),
            status=row["status"],
            task_type=inputs.get("task_type", ""),
            repo_url=inputs.get("repo_url", ""),
            branch=inputs.get("branch", ""),
            sha=inputs.get("sha", ""),
            error=row["error"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    async def update_run(self, run_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        if "completed_at" in kwargs and kwargs["completed_at"] is True:
            kwargs["completed_at"] = datetime.now(timezone.utc)
        sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(kwargs))
        values = list(kwargs.values()) + [run_id]
        await self._db.execute(
            f"UPDATE pipeline_runs SET {sets} WHERE id = ${len(values)}",
            *values,
        )

    async def list_runs(self, limit: int = 20, offset: int = 0, status: str | None = None) -> list[RunState]:
        if status:
            rows = await self._db.fetch(
                "SELECT id, status, inputs, state, error, created_at, completed_at "
                "FROM pipeline_runs WHERE status = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
                status, limit, offset,
            )
        else:
            rows = await self._db.fetch(
                "SELECT id, status, inputs, state, error, created_at, completed_at "
                "FROM pipeline_runs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
        return [_row_to_run(r) for r in rows]


class PostgresPipelineStore:
    def __init__(self, db: Database):
        self._db = db

    async def get_phases(self, run_id: str) -> list[dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# Row → dataclass helpers
# ---------------------------------------------------------------------------

def _row_to_event(r: Any) -> StreamEvent:
    payload = r["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return StreamEvent(
        id=r["id"],
        session_id=r["session_id"],
        event_type=r["event_type"],
        payload=payload or {},
        parent_id=r.get("parent_id"),
        agent_id=r.get("agent_id"),
        subagent_id=r.get("subagent_id"),
        created_at=r["created_at"],
    )


def _row_to_session(r: Any) -> SessionNode:
    return SessionNode(
        session_id=r["id"],
        parent_id=r["parent_session_id"],
        status=r["status"],
        depth=r["depth"] or 0,
        agent_role=r["agent_role"] or "leaf",
        goal=r["goal"] or "",
        model=r["model"] or "",
        total_tokens=r["total_tokens"] or 0,
        total_cost=float(r["total_cost"] or 0),
        created_at=r["created_at"],
        ended_at=r["ended_at"],
    )


def _row_to_agent(r: Any) -> AgentDef:
    bt = r["bash_constraints"]
    if isinstance(bt, str):
        bt = json.loads(bt)
    return AgentDef(
        role=r["role"],
        version=r["version"] or 1,
        description=r["description"] or "",
        system_prompt=r["system_prompt"] or "",
        allowed_tools=r["allowed_tools"] or [],
        allowed_skills=r["allowed_skills"] or [],
        model_primary=r["model_primary"] or "",
        model_fallback=r["model_fallback"] or "",
        delegation_depth=r["delegation_depth"] or 1,
        delegation_role=r["delegation_role"] or "leaf",
        triggers=r["triggers"] or [],
        bash_constraints=bt or {},
        output_contract=r["output_contract"] or "",
        source=r["source"] or "builtin",
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_run(r: Any) -> RunState:
    inputs = json.loads(r["inputs"]) if r.get("inputs") else {}
    return RunState(
        run_id=r["id"],
        session_id=inputs.get("session_id", ""),
        status=r["status"],
        task_type=inputs.get("task_type", ""),
        repo_url=inputs.get("repo_url", ""),
        branch=inputs.get("branch", ""),
        sha=inputs.get("sha", ""),
        error=r["error"],
        created_at=r["created_at"],
        completed_at=r["completed_at"],
        total_input_tokens=r.get("total_input_tokens") or inputs.get("total_input_tokens", 0),
        total_output_tokens=r.get("total_output_tokens") or inputs.get("total_output_tokens", 0),
        total_tokens=r.get("total_tokens") or inputs.get("total_tokens", 0),
        llm_call_count=r.get("llm_call_count") or inputs.get("llm_call_count", 0),
        lead_agent_tokens=r.get("lead_agent_tokens") or inputs.get("lead_agent_tokens", 0),
        subagent_tokens=r.get("subagent_tokens") or inputs.get("subagent_tokens", 0),
        model_name=inputs.get("model_name", ""),
    )


# ---------------------------------------------------------------------------
# JobSpecStore — chat → orchestrator handoff payload
#
# The chat Role (the only producer) calls `save()` with a
# `JobSpecRecord` built from a `harness.jobs.spec.JobSpec`. The
# orchestrator (the only consumer) calls `get()` to load it and
# `update_status()` as the run progresses. Both surfaces are
# protocol-bound; neither reaches into the other's internals.
#
# Schema lives in two tables: `job_specs` (one row per spec) and
# `proposals` (zero-or-more rows per spec, for Tier-2 work). Tables
# are created on first use; no separate migration step is required.
# ---------------------------------------------------------------------------


JOB_SPEC_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS job_specs (
        spec_id       TEXT PRIMARY KEY,
        run_id        TEXT NOT NULL,
        source        TEXT NOT NULL,
        prompt        TEXT NOT NULL,
        repo_url      TEXT NOT NULL DEFAULT '',
        branch        TEXT NOT NULL DEFAULT 'main',
        sha           TEXT NOT NULL DEFAULT '',
        tier          INTEGER NOT NULL DEFAULT 1,
        capabilities  TEXT NOT NULL DEFAULT '[]',
        approval      TEXT NOT NULL DEFAULT '{}',
        context       TEXT NOT NULL DEFAULT '{}',
        status        TEXT NOT NULL DEFAULT 'pending',
        error         TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at    TIMESTAMPTZ,
        completed_at  TIMESTAMPTZ,
        latest_run_status     TEXT,
        latest_run_cost_usd   REAL,
        latest_run_duration_s REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_specs_status ON job_specs(status)",
    "CREATE INDEX IF NOT EXISTS idx_job_specs_run_id ON job_specs(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_specs_source ON job_specs(source)",
    "CREATE INDEX IF NOT EXISTS idx_job_specs_tier ON job_specs(tier)",
    # Session-scoped listing (the chat's ``list_jobs`` filter
    # by ``context->>'session_id'``). A partial GIN index on
    # the JSONB cast of ``context`` keeps the query O(log n)
    # even when the ``job_specs`` table grows past 10K rows.
    # The ``context`` column is TEXT (the orchestrator
    # JSON-encodes JobContext before insert); the ``::jsonb``
    # cast lets the JSONB operator apply. The ``WHERE``
    # predicate makes this a *partial* index — only rows
    # that have a session_id get indexed, so the index stays
    # small.
    "CREATE INDEX IF NOT EXISTS idx_job_specs_context_session ON job_specs ((context::jsonb->>'session_id')) WHERE context::jsonb->>'session_id' IS NOT NULL",
)


JOB_COMMENT_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS job_comments (
        comment_id TEXT PRIMARY KEY,
        spec_id    TEXT NOT NULL REFERENCES job_specs(spec_id) ON DELETE CASCADE,
        author     TEXT NOT NULL DEFAULT '',
        body       TEXT NOT NULL DEFAULT '',
        kind       TEXT NOT NULL DEFAULT 'comment',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_comments_spec_id ON job_comments(spec_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_comments_created_at ON job_comments(created_at DESC)",
)


JOB_OUTPUT_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS job_outputs (
        spec_id       TEXT PRIMARY KEY REFERENCES job_specs(spec_id) ON DELETE CASCADE,
        status        TEXT NOT NULL DEFAULT '',
        summary       TEXT NOT NULL DEFAULT '',
        artifacts     TEXT NOT NULL DEFAULT '[]',
        pr_url        TEXT,
        cost_usd      REAL,
        duration_s    REAL,
        completed_at  TIMESTAMPTZ
    )
    """,
)


# Item 6: DB-backed JobCheckpoint storage. The orchestrator
# saves a checkpoint per-spec on pause; the LLM uses the
# saved subagent_state on resume to know what was already
# done. The pause SIGNAL is already DB-backed (the spec's
# `status='paused'` field — the watcher polls it). The
# CHECKPOINT itself is metadata layered on top; persisting
# it to Postgres lets the checkpoint survive orchestrator
# process restarts.
#
# Pattern (per Hermes/openclaude/ohmo research 2026-06):
#   - Hermes: in-memory `_active_subagents` (process-local,
#     NO cross-process)
#   - OpenCode: transcript replay (no separate state)
#   - OpenHands: Docker container pause (infrastructure-level)
#   - OpenHarness/ohmo: full message history (transcript)
# None of them have a "JobCheckpoint" — that's our addition
# (item 5, true replay). The DB-backed version below is
# the cutting-edge pattern.
JOB_CHECKPOINT_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS job_checkpoints (
        spec_id        TEXT PRIMARY KEY REFERENCES job_specs(spec_id) ON DELETE CASCADE,
        run_id         TEXT NOT NULL,
        last_result    TEXT NOT NULL DEFAULT '{}',
        paused_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        paused_by      TEXT NOT NULL DEFAULT '',
        subagent_state TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_checkpoints_paused_at ON job_checkpoints(paused_at DESC)",
)


PROPOSAL_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS proposals (
        proposal_id   TEXT PRIMARY KEY,
        spec_id       TEXT NOT NULL REFERENCES job_specs(spec_id) ON DELETE CASCADE,
        test_files    TEXT NOT NULL DEFAULT '[]',
        rationale     TEXT NOT NULL DEFAULT '',
        risk_score    INTEGER NOT NULL DEFAULT 0,
        status        TEXT NOT NULL DEFAULT 'pending_review',
        reviewer      TEXT NOT NULL DEFAULT '',
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        reviewed_at   TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_proposals_spec_id ON proposals(spec_id)",
    "CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status)",
)


def _row_to_job_spec(r: Any) -> JobSpecRecord:
    """Hydrate a `JobSpecRecord` from a SELECT result row.

    JSON-shaped columns (capabilities, approval, context) are
    stored as TEXT-encoded JSON, matching the convention used by
    other tables in the schema (e.g. pipeline_runs.inputs,
    sessions.state). The Python layer always JSON-encodes on
    write and JSON-decodes on read.
    """
    capabilities = r["capabilities"]
    if isinstance(capabilities, str):
        capabilities = json.loads(capabilities) if capabilities else []
    approval = r["approval"]
    if isinstance(approval, str):
        approval = json.loads(approval) if approval else {}
    context = r["context"]
    if isinstance(context, str):
        context = json.loads(context) if context else {}
    return JobSpecRecord(
        spec_id=r["spec_id"],
        run_id=r["run_id"],
        source=r["source"],
        prompt=r["prompt"],
        repo_url=r["repo_url"] or "",
        branch=r["branch"] or "main",
        sha=r["sha"] or "",
        tier=int(r["tier"] or 1),
        capabilities=list(capabilities or []),
        approval=dict(approval or {}),
        context=dict(context or {}),
        status=r["status"] or "pending",
        error=r["error"],
        created_at=r["created_at"],
        started_at=r["started_at"],
        completed_at=r["completed_at"],
    )


def _row_to_proposal(r: Any) -> ProposalRecord:
    test_files = r["test_files"]
    if isinstance(test_files, str):
        test_files = json.loads(test_files) if test_files else []
    return ProposalRecord(
        proposal_id=r["proposal_id"],
        spec_id=r["spec_id"],
        test_files=list(test_files or []),
        rationale=r["rationale"] or "",
        risk_score=int(r["risk_score"] or 0),
        status=r["status"] or "pending_review",
        reviewer=r["reviewer"] or "",
        created_at=r["created_at"],
        reviewed_at=r["reviewed_at"],
    )


def _row_to_job_comment(r: Any) -> JobComment:
    return JobComment(
        comment_id=r["comment_id"],
        spec_id=r["spec_id"],
        author=r["author"] or "",
        body=r["body"] or "",
        kind=r["kind"] or "comment",
        created_at=r["created_at"],
    )


def _row_to_job_output(r: Any) -> JobOutput:
    artifacts_raw = r["artifacts"]
    if isinstance(artifacts_raw, str):
        try:
            artifacts = json.loads(artifacts_raw) if artifacts_raw else []
        except (TypeError, ValueError):
            artifacts = []
    else:
        artifacts = artifacts_raw
    return JobOutput(
        spec_id=r["spec_id"],
        status=r["status"] or "",
        summary=r["summary"] or "",
        artifacts=list(artifacts or []),
        pr_url=r["pr_url"],
        cost_usd=r["cost_usd"],
        duration_s=r["duration_s"],
        completed_at=r["completed_at"],
    )


def _row_to_job_summary(r: Any) -> JobSummary:
    """Hydrate a `JobSummary` (C08 Q10) from a `job_specs` row.

    The `latest_run_*` columns are denormalized on the spec
    row — they're written by ``update_status`` when a run
    completes. The LLM (chat's ``list_jobs`` tool) cares
    about job state, not full spec details; this shape is
    actionable without follow-up ``get_job`` calls.
    """
    return JobSummary(
        spec_id=r["spec_id"],
        prompt=(r["prompt"] or "")[:200],
        repo_url=r["repo_url"] or "",
        tier=int(r["tier"] or 1),
        status=r["status"] or "pending",
        created_at=r["created_at"],
        latest_run_id=r["run_id"],
        latest_run_status=r.get("latest_run_status"),
        latest_run_started_at=r["started_at"],
        latest_run_cost_usd=r.get("latest_run_cost_usd"),
        latest_run_duration_s=r.get("latest_run_duration_s"),
    )


class PostgresJobSpecStore:
    """Postgres implementation of `JobSpecStore`.

    Tables are created on first use via `_ensure_tables()`. The
    store is safe to use in a long-running process; subsequent
    calls hit the already-created tables. The schema is also
    declared in `harness/memory/schema/schema.sql` — the
    `_ensure_tables()` call is defense in depth for environments
    that don't run `schema.sql` at startup.
    """

    def __init__(self, db: Database):
        self._db = db
        self._ensured = False

    async def _ensure_tables(self) -> None:
        if self._ensured:
            return
        for ddl in JOB_SPEC_DDL + PROPOSAL_DDL:
            await self._db.execute(ddl)
        self._ensured = True

    async def save(self, record: JobSpecRecord) -> None:
        await self._ensure_tables()
        await self._db.execute(
            """INSERT INTO job_specs (
                   spec_id, run_id, source, prompt, repo_url, branch, sha,
                   tier, capabilities, approval, context, status, error
               ) VALUES (
                   $1, $2, $3, $4, $5, $6, $7,
                   $8, $9, $10, $11, $12, $13
               )
               ON CONFLICT (spec_id) DO NOTHING""",
            record.spec_id, record.run_id, record.source, record.prompt,
            record.repo_url, record.branch, record.sha,
            record.tier, json.dumps(record.capabilities),
            json.dumps(record.approval), json.dumps(record.context),
            record.status, record.error,
        )

    async def get(self, spec_id: str) -> JobSpecRecord | None:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT * FROM job_specs WHERE spec_id = $1", spec_id,
        )
        return _row_to_job_spec(row) if row else None

    async def update_status(
        self, spec_id: str, status: str, *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        run_id: str | None = None,
        cost_usd: float | None = None,
        duration_s: float | None = None,
    ) -> None:
        await self._ensure_tables()
        # Build a dynamic SET clause so we only touch the fields the
        # caller passed. NULL means "don't change".
        sets: list[str] = ["status = $2"]
        params: list[Any] = [spec_id, status]
        if started_at is not None:
            params.append(started_at)
            sets.append(f"started_at = ${len(params)}")
        if completed_at is not None:
            params.append(completed_at)
            sets.append(f"completed_at = ${len(params)}")
        if error is not None:
            params.append(error)
            sets.append(f"error = ${len(params)}")
        if run_id is not None:
            params.append(run_id)
            sets.append(f"run_id = ${len(params)}")
        if cost_usd is not None:
            params.append(cost_usd)
            sets.append(f"latest_run_cost_usd = ${len(params)}")
        if duration_s is not None:
            params.append(duration_s)
            sets.append(f"latest_run_duration_s = ${len(params)}")
        # ``status`` doubles as the latest run status for the
        # ``list_by_session`` summary view. Always write it
        # when ``status`` is non-null.
        if status:
            params.append(status)
            sets.append(f"latest_run_status = ${len(params)}")
        await self._db.execute(
            f"UPDATE job_specs SET {', '.join(sets)} WHERE spec_id = $1",
            *params,
        )

    async def list_pending(self, limit: int = 50) -> list[JobSpecRecord]:
        await self._ensure_tables()
        rows = await self._db.fetch(
            "SELECT * FROM job_specs WHERE status = 'pending' "
            "ORDER BY created_at ASC LIMIT $1",
            limit,
        )
        return [_row_to_job_spec(r) for r in rows]

    # ----- C08 chat-facing 8-tool surface (Q9) -----

    async def list_by_session(
        self, session_id: str, *, limit: int = 20, offset: int = 0,
    ) -> tuple[list[JobSummary], int]:
        await self._ensure_tables()
        # ``context`` is TEXT (orchestrator JSON-encodes
        # JobContext before insert); cast to ``::jsonb`` to use
        # the JSONB operator and the partial GIN index.
        total_row = await self._db.fetchrow(
            "SELECT COUNT(*) AS n FROM job_specs "
            "WHERE context::jsonb->>'session_id' = $1",
            session_id,
        )
        total = int(total_row["n"]) if total_row else 0
        rows = await self._db.fetch(
            "SELECT * FROM job_specs "
            "WHERE context::jsonb->>'session_id' = $1 "
            "ORDER BY created_at DESC "
            "LIMIT $2 OFFSET $3",
            session_id, limit, offset,
        )
        return [_row_to_job_summary(r) for r in rows], total

    async def list_recent(
        self, *, limit: int = 20, offset: int = 0,
    ) -> tuple[list[JobSummary], int]:
        await self._ensure_tables()
        # Dashboard's "All jobs" view.  Most recent first, no
        # session filter.  Pairs with :meth:`list_by_session`.
        total_row = await self._db.fetchrow("SELECT COUNT(*) AS n FROM job_specs")
        total = int(total_row["n"]) if total_row else 0
        rows = await self._db.fetch(
            "SELECT * FROM job_specs "
            "ORDER BY created_at DESC "
            "LIMIT $1 OFFSET $2",
            limit, offset,
        )
        return [_row_to_job_summary(r) for r in rows], total

    async def get_status(self, spec_id: str) -> JobStatus | None:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT spec_id, status, started_at, completed_at, error, run_id "
            "FROM job_specs WHERE spec_id = $1",
            spec_id,
        )
        if row is None:
            return None
        return JobStatus(
            spec_id=row["spec_id"],
            status=row["status"] or "pending",
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error=row["error"],
            run_id=row["run_id"],
        )

    async def cancel(self, spec_id: str) -> bool:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT status FROM job_specs WHERE spec_id = $1",
            spec_id,
        )
        if row is None or (row["status"] or "") in ("completed", "failed", "cancelled"):
            return False
        await self._db.execute(
            "UPDATE job_specs SET status = 'cancelled' WHERE spec_id = $1",
            spec_id,
        )
        return True

    async def pause(self, spec_id: str) -> bool:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT status FROM job_specs WHERE spec_id = $1",
            spec_id,
        )
        if row is None or (row["status"] or "") in (
            "completed", "failed", "cancelled", "paused",
        ):
            return False
        await self._db.execute(
            "UPDATE job_specs SET status = 'paused' WHERE spec_id = $1",
            spec_id,
        )
        return True

    async def resume(self, spec_id: str) -> bool:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT status FROM job_specs WHERE spec_id = $1",
            spec_id,
        )
        if row is None or (row["status"] or "") != "paused":
            return False
        await self._db.execute(
            "UPDATE job_specs SET status = 'running' WHERE spec_id = $1",
            spec_id,
        )
        return True

    async def add_comment(self, comment: JobComment) -> None:
        await self._ensure_tables()
        await self._db.execute(
            """INSERT INTO job_comments (comment_id, spec_id, author, body, kind, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (comment_id) DO NOTHING""",
            comment.comment_id,
            comment.spec_id,
            comment.author,
            comment.body,
            comment.kind,
            comment.created_at,
        )

    async def add_output(self, output: JobOutput) -> None:
        """Upsert a ``JobOutput`` row for the given spec. The
        orchestrator writes one on natural completion so the
        dashboard's job-detail page can render the evidence
        summary without a JOIN to ``stream_events``."""
        await self._ensure_tables()
        artifacts_json = json.dumps(list(output.artifacts or []))
        await self._db.execute(
            """INSERT INTO job_outputs
                 (spec_id, status, summary, artifacts, pr_url,
                  cost_usd, duration_s, completed_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (spec_id) DO UPDATE SET
                 status = EXCLUDED.status,
                 summary = EXCLUDED.summary,
                 artifacts = EXCLUDED.artifacts,
                 pr_url = EXCLUDED.pr_url,
                 cost_usd = EXCLUDED.cost_usd,
                 duration_s = EXCLUDED.duration_s,
                 completed_at = EXCLUDED.completed_at""",
            output.spec_id,
            output.status,
            output.summary,
            artifacts_json,
            output.pr_url,
            output.cost_usd,
            output.duration_s,
            output.completed_at,
        )

    async def get_output(self, spec_id: str) -> JobOutput | None:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT * FROM job_outputs WHERE spec_id = $1",
            spec_id,
        )
        return _row_to_job_output(row) if row else None

    async def list_comments(
        self, spec_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[JobComment], int]:
        await self._ensure_tables()
        total_row = await self._db.fetchrow(
            "SELECT COUNT(*) AS n FROM job_comments WHERE spec_id = $1",
            spec_id,
        )
        total = int(total_row["n"]) if total_row else 0
        rows = await self._db.fetch(
            "SELECT * FROM job_comments WHERE spec_id = $1 "
            "ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            spec_id, limit, offset,
        )
        return [_row_to_job_comment(r) for r in rows], total


def _row_to_job_checkpoint(r: Any) -> "JobCheckpointRow":
    """Hydrate a checkpoint row from a SELECT result.

    Mirrors the in-memory ``JobCheckpoint`` dataclass in
    ``harness/services/job_checkpoint.py`` so the
    orchestrator's `run_resumed_job_spec` can consume the
    Postgres-backed checkpoint without knowing the storage
    backend.
    """
    last_result = r["last_result"]
    if isinstance(last_result, str):
        last_result = json.loads(last_result) if last_result else {}
    subagent_state = r["subagent_state"]
    if isinstance(subagent_state, str):
        subagent_state = json.loads(subagent_state) if subagent_state else None
    paused_at = r["paused_at"]
    if hasattr(paused_at, "isoformat"):
        paused_at = paused_at.isoformat()
    return {
        "spec_id": r["spec_id"],
        "run_id": r["run_id"],
        "last_result": dict(last_result or {}),
        "paused_at": str(paused_at),
        "paused_by": r["paused_by"],
        "subagent_state": subagent_state,
    }


class PostgresJobCheckpointStore:
    """Postgres-backed JobCheckpoint store (item 6).

    Per-spec checkpoint that survives orchestrator process
    restarts. The in-memory version
    (``harness/services/job_checkpoint.py``) is the default;
    production deployments wire this one via
    ``set_checkpoint_backend(pg_store)``.

    Schema (from ``JOB_CHECKPOINT_DDL``):
        job_checkpoints(
            spec_id        TEXT PRIMARY KEY REFERENCES job_specs(spec_id),
            run_id         TEXT NOT NULL,
            last_result    TEXT NOT NULL DEFAULT '{}',  -- JSON
            paused_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            paused_by      TEXT NOT NULL DEFAULT '',
            subagent_state TEXT NOT NULL DEFAULT '{}'   -- JSON
        )

    The store returns a plain dict matching the in-memory
    ``JobCheckpoint.to_dict()`` shape so callers can treat
    the two backends uniformly.
    """

    def __init__(self, db: Database):
        self._db = db
        self._ensured = False

    async def _ensure_tables(self) -> None:
        if self._ensured:
            return
        for ddl in (
            JOB_SPEC_DDL + PROPOSAL_DDL
            + JOB_COMMENT_DDL + JOB_OUTPUT_DDL
        ):
            await self._db.execute(ddl)
        self._ensured = True

    async def save_checkpoint(
        self,
        spec_id: str,
        run_id: str,
        last_result: dict[str, Any],
        paused_by: str,
        subagent_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert or replace a checkpoint for ``spec_id``.

        UPSERT semantics: a new pause overwrites the existing
        checkpoint (matches the in-memory store's behavior).
        """
        await self._ensure_tables()
        await self._db.execute(
            """INSERT INTO job_checkpoints (
                   spec_id, run_id, last_result, paused_by, subagent_state
               ) VALUES ($1, $2, $3::jsonb, $4, $5::jsonb)
               ON CONFLICT (spec_id) DO UPDATE SET
                   run_id = EXCLUDED.run_id,
                   last_result = EXCLUDED.last_result,
                   paused_at = NOW(),
                   paused_by = EXCLUDED.paused_by,
                   subagent_state = EXCLUDED.subagent_state""",
            spec_id, run_id,
            json.dumps(last_result or {}),
            paused_by,
            json.dumps(subagent_state) if subagent_state is not None else None,
        )
        # Read back to return the canonical row (with paused_at).
        row = await self.get_checkpoint(spec_id)
        if row is None:
            return {
                "spec_id": spec_id, "run_id": run_id,
                "last_result": last_result, "paused_at": "",
                "paused_by": paused_by, "subagent_state": subagent_state,
            }
        return row

    async def get_checkpoint(self, spec_id: str) -> dict[str, Any] | None:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT * FROM job_checkpoints WHERE spec_id = $1", spec_id,
        )
        return _row_to_job_checkpoint(row) if row else None

    async def pop_checkpoint(self, spec_id: str) -> dict[str, Any] | None:
        """Return and delete the checkpoint for ``spec_id``."""
        await self._ensure_tables()
        row = await self.get_checkpoint(spec_id)
        if row is None:
            return None
        await self._db.execute(
            "DELETE FROM job_checkpoints WHERE spec_id = $1", spec_id,
        )
        return row

    async def list_checkpoints(self) -> list[dict[str, Any]]:
        await self._ensure_tables()
        rows = await self._db.fetch(
            "SELECT * FROM job_checkpoints ORDER BY paused_at DESC",
        )
        return [_row_to_job_checkpoint(r) for r in rows]


class PostgresProposalStore:
    """Postgres implementation of `ProposalStore`.

    Same `CREATE TABLE IF NOT EXISTS` pattern as `PostgresJobSpecStore`.
    Shares the `job_specs` table via the `proposals.spec_id` foreign
    key with `ON DELETE CASCADE` — deleting a spec drops its
    proposals too, which matches the lifecycle expectation.
    """

    def __init__(self, db: Database):
        self._db = db
        self._ensured = False

    async def _ensure_tables(self) -> None:
        if self._ensured:
            return
        for ddl in JOB_SPEC_DDL + PROPOSAL_DDL:
            await self._db.execute(ddl)
        self._ensured = True

    async def save(self, record: ProposalRecord) -> None:
        await self._ensure_tables()
        await self._db.execute(
            """INSERT INTO proposals (
                   proposal_id, spec_id, test_files, rationale,
                   risk_score, status, reviewer, created_at
               ) VALUES (
                   $1, $2, $3, $4, $5, $6, $7, COALESCE($8, NOW())
               )
               ON CONFLICT (proposal_id) DO NOTHING""",
            record.proposal_id, record.spec_id,
            json.dumps(record.test_files), record.rationale,
            record.risk_score, record.status, record.reviewer,
            record.created_at,
        )

    async def get(self, proposal_id: str) -> ProposalRecord | None:
        await self._ensure_tables()
        row = await self._db.fetchrow(
            "SELECT * FROM proposals WHERE proposal_id = $1", proposal_id,
        )
        return _row_to_proposal(row) if row else None

    async def list_for_spec(self, spec_id: str) -> list[ProposalRecord]:
        await self._ensure_tables()
        rows = await self._db.fetch(
            "SELECT * FROM proposals WHERE spec_id = $1 "
            "ORDER BY created_at DESC",
            spec_id,
        )
        return [_row_to_proposal(r) for r in rows]

    async def list_pending(self, limit: int = 50) -> list[ProposalRecord]:
        await self._ensure_tables()
        rows = await self._db.fetch(
            "SELECT * FROM proposals WHERE status = 'pending_review' "
            "ORDER BY created_at ASC LIMIT $1",
            limit,
        )
        return [_row_to_proposal(r) for r in rows]

    async def mark_decision(
        self, proposal_id: str, decision: str, reviewer: str, *,
        reviewed_at: datetime | None = None,
    ) -> None:
        await self._ensure_tables()
        if reviewed_at is None:
            reviewed_at = datetime.now(timezone.utc)
        await self._db.execute(
            "UPDATE proposals SET status = $2, reviewer = $3, "
            "reviewed_at = $4 WHERE proposal_id = $1",
            proposal_id, decision, reviewer, reviewed_at,
        )
