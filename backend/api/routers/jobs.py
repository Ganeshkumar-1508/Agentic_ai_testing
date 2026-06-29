"""POST /api/jobs router — C08 canonical submission + 8-tool surface.

C08 (per docs/2026-06-21-architecture-decision-tree.md#c08):
  Q6 (locked): ``POST /api/jobs`` accepts a JobSpec directly.
  This is the canonical job submission endpoint. The three
  legacy endpoints (``/api/agent/run``, ``/api/delegate``,
  ``/api/pipeline/from-requirements``) have been hard-deleted
  (Q7 step 2).
  Q8 (locked): the chat's 8-tool surface is exposed here too:
    GET    /api/jobs/{spec_id}
    GET    /api/jobs?session_id=X
    POST   /api/jobs/{spec_id}/cancel
    POST   /api/jobs/{spec_id}/pause
    POST   /api/jobs/{spec_id}/resume
    POST   /api/jobs/{spec_id}/comments
    GET    /api/jobs/{spec_id}/output

The chat's ``submit_job`` tool calls
``submit_job_to_orchestrator`` directly (via the in-process
seam); this router is the HTTP surface for external
integrations (A2A adapter, webhooks, cron).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from harness.jobs.spec import JobSpec
from harness.jobs.submitter import submit_job_to_orchestrator

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class JobSpecRequest(BaseModel):
    """HTTP request body for ``POST /api/jobs``.

    Mirrors the in-memory :class:`JobSpec` field-for-field. The
    caller may also post a ``test_config`` sub-object for
    from-requirements callers (C08 Q3).
    """
    model_config = ConfigDict(extra="allow")

    spec_id: str | None = None
    source: str = "api"
    prompt: str
    repo_url: str = ""
    branch: str = "main"
    sha: str = ""
    tier: int = 1
    capabilities: list[str] = Field(default_factory=list)
    approval: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    backend_type: str = "local"
    # Top-level session_id. Filled into context.session_id
    # (the only key the JobSpecStore list_by_session filters on)
    # so an API submission can be discovered via
    # GET /api/jobs?session_id=... .
    session_id: str | None = None


class SubmitJobResponse(BaseModel):
    spec_id: str
    run_id: str
    thread_id: str = ""
    status: str = "submitted"


class JobSpecResponse(BaseModel):
    """HTTP response for ``GET /api/jobs/{spec_id}``."""
    spec_id: str
    run_id: str
    source: str
    prompt: str
    repo_url: str
    branch: str
    sha: str
    tier: int
    capabilities: list[str]
    approval: dict[str, Any]
    context: dict[str, Any]
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    comments: list[dict[str, Any]] = Field(default_factory=list)


class JobSummaryResponse(BaseModel):
    spec_id: str
    prompt: str
    repo_url: str
    tier: int
    status: str
    created_at: str
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    latest_run_started_at: str | None = None
    latest_run_cost_usd: float | None = None
    latest_run_duration_s: float | None = None


class JobListResponse(BaseModel):
    items: list[JobSummaryResponse]
    total: int
    limit: int
    offset: int


class CommentsListResponse(BaseModel):
    items: list[CommentResponse]
    total: int
    limit: int
    offset: int


class CancelResponse(BaseModel):
    spec_id: str
    cancelled: bool


class PauseResponse(BaseModel):
    spec_id: str
    paused: bool


class ResumeResponse(BaseModel):
    spec_id: str
    resumed: bool


class CommentRequest(BaseModel):
    author: str
    body: str
    kind: str = "comment"


class CommentResponse(BaseModel):
    comment_id: str
    spec_id: str
    author: str
    body: str
    kind: str
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_store(request: Request) -> Any:
    """Return the wired :class:`JobSpecStore` from app state.

    Falls back to the module-level injector if the FastAPI app
    didn't stash a copy.
    """
    store = getattr(request.app.state, "job_spec_store", None)
    if store is not None:
        return store
    from harness.jobs.spec import _job_spec_store as _module_store
    return _module_store()


def _get_orchestrator_factory(request: Request) -> Any:
    """Return a callable that builds an :class:`OrchestratorEngine`.

    Looks for an explicit factory first; falls back to the
    default constructor. Returns ``None`` if neither is available
    (the request handler will then surface a 503).
    """
    factory = getattr(request.app.state, "orchestrator_engine_factory", None)
    if factory is not None:
        return factory
    try:
        from harness.orchestrator import OrchestratorEngine
        return lambda: OrchestratorEngine.create_default()
    except Exception as exc:
        logger.debug("/api/jobs: OrchestratorEngine unavailable: %s", exc)
        return None


def _spec_to_response(record: Any, comments: list[Any] | None = None) -> JobSpecResponse:
    """Convert a :class:`JobSpecRecord` + comments to the HTTP shape."""
    return JobSpecResponse(
        spec_id=record.spec_id,
        run_id=record.run_id,
        source=record.source,
        prompt=record.prompt,
        repo_url=record.repo_url,
        branch=record.branch,
        sha=record.sha,
        tier=record.tier,
        capabilities=list(record.capabilities or []),
        approval=dict(record.approval or {}),
        context=dict(record.context or {}),
        status=record.status,
        created_at=(
            record.created_at.isoformat() if record.created_at else ""
        ),
        started_at=(
            record.started_at.isoformat() if record.started_at else None
        ),
        completed_at=(
            record.completed_at.isoformat() if record.completed_at else None
        ),
        error=record.error,
        comments=[c.to_dict() for c in (comments or [])],
    )


# ---------------------------------------------------------------------------
# POST /api/jobs — submit a new job
# ---------------------------------------------------------------------------


@router.post("", response_model=SubmitJobResponse, status_code=201)
async def submit_job(req: Request, body: JobSpecRequest) -> SubmitJobResponse:
    """Submit a new job. Returns the ``run_id`` (may be empty if
    dispatch failed but persistence succeeded)."""
    if not body.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    spec_id = body.spec_id or str(uuid.uuid4())
    # Ensure context.session_id is populated — the store's
    # list_by_session filters on `context::jsonb->>'session_id'`
    # (see PostgresJobSpecStore.list_by_session). Without this,
    # API-submitted jobs would be invisible to the dashboard's
    # "jobs in this session" view even though the GET endpoint
    # requires session_id.
    ctx = dict(body.context or {})
    if "session_id" not in ctx or not ctx.get("session_id"):
        ctx["session_id"] = body.session_id or f"api-{spec_id[:8]}"
    spec = JobSpec(
        spec_id=spec_id,
        run_id=str(uuid.uuid4()),  # placeholder; orchestrator overwrites
        source=body.source or "api",
        prompt=body.prompt,
        repo_url=body.repo_url,
        branch=body.branch or "main",
        sha=body.sha,
        tier=body.tier,
        capabilities=list(body.capabilities),
        approval=dict(body.approval),
        backend_type=body.backend_type,
        context=ctx,
    )

    store = _get_store(req)
    factory = _get_orchestrator_factory(req)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="JobSpecStore not configured; backend not started cleanly",
        )
    run_id = await submit_job_to_orchestrator(
        spec,
        job_spec_store=store,
        orchestrator_engine_factory=factory,
    )
    if not run_id:
        # Soft error — the spec was persisted but dispatch failed.
        # The caller can poll the spec status to recover.
        return SubmitJobResponse(
            spec_id=spec.spec_id, run_id="", thread_id="", status="queued",
        )
    thread_id = ""
    try:
        from harness.chat.threads import get_thread_by_run_id
        thread = await get_thread_by_run_id(run_id, db=req.app.state.db)
        if thread is not None:
            thread_id = thread.id
    except Exception as exc:
        logger.debug("submit_job: thread lookup failed run_id=%s: %s", run_id, exc)
    return SubmitJobResponse(
        spec_id=spec.spec_id, run_id=run_id, thread_id=thread_id, status="submitted",
    )


# ---------------------------------------------------------------------------
# GET /api/jobs/{spec_id} — full spec detail
# ---------------------------------------------------------------------------


@router.get("/{spec_id}", response_model=JobSpecResponse)
async def get_job(
    req: Request,
    spec_id: str,
    comments_limit: int = Query(default=50, ge=1, le=200),
    comments_offset: int = Query(default=0, ge=0),
) -> JobSpecResponse:
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    record = await store.get(spec_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    comments: list[Any] = []
    try:
        items, _total = await store.list_comments(
            spec_id, limit=comments_limit, offset=comments_offset,
        )
        comments = items
    except Exception:
        pass
    return _spec_to_response(record, comments)


@router.get("/{spec_id}/comments", response_model=CommentsListResponse)
async def list_job_comments(
    req: Request,
    spec_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CommentsListResponse:
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    items, total = await store.list_comments(spec_id, limit=limit, offset=offset)
    return CommentsListResponse(
        items=[CommentResponse(**c.to_dict()) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/jobs?session_id=X — list summaries
# ---------------------------------------------------------------------------


@router.get("", response_model=JobListResponse)
async def list_jobs(
    req: Request,
    session_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    """List jobs, optionally filtered by ``session_id``.

    Returns a paginated envelope ``{"items": [...], "total": N,
    "limit": L, "offset": O}`` so the dashboard can paginate
    past the default 20-item page.

    When ``session_id`` is empty (the page's default), lists the
    most recent jobs across all sessions — the dashboard's "All jobs"
    view.  Pass an explicit session_id to scope to one session.
    """
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    if not session_id:
        # "All sessions" mode: list the most recent jobs, paginated.
        items, total = await store.list_recent(limit=limit, offset=offset)
    else:
        items, total = await store.list_by_session(session_id, limit=limit, offset=offset)
    return JobListResponse(
        items=[JobSummaryResponse(**s.to_dict()) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# POST /api/jobs/{spec_id}/cancel
# ---------------------------------------------------------------------------


@router.post("/{spec_id}/cancel", response_model=CancelResponse)
async def cancel_job(req: Request, spec_id: str) -> CancelResponse:
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    ok = await store.cancel(spec_id)
    return CancelResponse(spec_id=spec_id, cancelled=ok)


# ---------------------------------------------------------------------------
# POST /api/jobs/{spec_id}/pause
# ---------------------------------------------------------------------------


@router.post("/{spec_id}/pause", response_model=PauseResponse)
async def pause_job(req: Request, spec_id: str) -> PauseResponse:
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    ok = await store.pause(spec_id)
    return PauseResponse(spec_id=spec_id, paused=ok)


# ---------------------------------------------------------------------------
# POST /api/jobs/{spec_id}/resume
# ---------------------------------------------------------------------------


@router.post("/{spec_id}/resume", response_model=ResumeResponse)
async def resume_job(req: Request, spec_id: str) -> ResumeResponse:
    """Resume a paused job by re-spawning the orchestrator.

    C08 follow-up: the resume endpoint used to just flip the
    spec's status from ``paused`` to ``running``. That left
    the user with a "running" job that wasn't actually
    running — they had to manually re-submit. This endpoint
    now calls ``OrchestratorEngine.run_resumed_job_spec``
    which:

      1. Loads the spec from the store
      2. Pops the saved :class:`JobCheckpoint` (consumes it)
      3. Builds a fresh ``JobSpec`` from the record
      4. Annotates the context with ``resumed_from_checkpoint``
      5. Spawns ``run_job_spec`` as a background task
      6. Emits a ``job.resumed`` stream event for the
         activity feed

    The new run has a fresh ``run_id`` but the same
    ``spec_id``. The orchestrator's run loop starts fresh
    (today: a full restart; future: true replay from
    checkpoint).
    """
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")

    factory = _get_orchestrator_factory(req)
    if factory is None:
        # No orchestrator wired (e.g. local dev). Fall back to
        # the old behavior: just flip the status. The user
        # can re-submit to actually run.
        ok = await store.resume(spec_id)
        return ResumeResponse(spec_id=spec_id, resumed=ok)

    # Re-spawn the orchestrator. This pops the checkpoint
    # and starts a fresh run in a background task.
    try:
        result = await factory().run_resumed_job_spec(spec_id)
    except Exception as exc:
        logger.warning("resume_job: orchestrator spawn failed: %s", exc)
        ok = await store.resume(spec_id)
        return ResumeResponse(spec_id=spec_id, resumed=ok)

    if not result.get("resumed"):
        # Spec wasn't paused, or had no spec record. Fall
        # back to the old behavior: flip the status.
        ok = await store.resume(spec_id)
        return ResumeResponse(spec_id=spec_id, resumed=ok)

    return ResumeResponse(spec_id=spec_id, resumed=True)


# ---------------------------------------------------------------------------
# POST /api/jobs/{spec_id}/comments
# ---------------------------------------------------------------------------


@router.post("/{spec_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    req: Request, spec_id: str, body: CommentRequest,
) -> CommentResponse:
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    if not body.body:
        raise HTTPException(status_code=400, detail="body is required")
    from datetime import datetime, timezone
    from harness.store.protocols import JobComment
    comment = JobComment(
        comment_id=str(uuid.uuid4()),
        spec_id=spec_id,
        author=body.author or "anonymous",
        body=body.body,
        kind=body.kind or "comment",
        created_at=datetime.now(timezone.utc),
    )
    await store.add_comment(comment)
    return CommentResponse(**comment.to_dict())


# ---------------------------------------------------------------------------
# GET /api/jobs/{spec_id}/output
# ---------------------------------------------------------------------------


@router.get("/{spec_id}/output")
async def get_job_output(req: Request, spec_id: str) -> dict[str, Any]:
    store = _get_store(req)
    if store is None:
        raise HTTPException(status_code=503, detail="JobSpecStore not configured")
    out = await store.get_output(spec_id)
    if out is None:
        raise HTTPException(status_code=404, detail="No output for this job")
    return out.to_dict()
