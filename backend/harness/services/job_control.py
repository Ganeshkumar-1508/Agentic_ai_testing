"""Chat-side job-control dispatcher.

The chat Role has a curated set of tools for managing the user's own
jobs: submit a new job, cancel / pause / resume a running one, list the
session's recent jobs, fetch a single job's status, and add a comment to
a job's record.

Before C09, each of these tools was an inline ``_handle_*_job`` method
on :class:`harness.agent.tool_dispatch.ToolDispatcher` (seven methods,
~700 lines). The methods all shared the same shape &mdash; ``args &rarr;
resolve target &rarr; act on store &rarr; emit ToolExecutionCompleted
&rarr; return user-facing string`` &mdash; and they emitted the
completion event *inconsistently* (some only on success, some never on
error), which undercounted failures in the dashboard's tool-health
panel.

C09 lifts the seven handlers into a single deep module with one
seam: :class:`JobControlDispatcher`. The chat surface calls
:meth:`JobControlDispatcher.dispatch`, which returns a structured
:class:`JobControlResult`; the caller (``ToolDispatcher``) emits the
``ToolExecutionCompleted`` event exactly once per call, with
``success=result.success`` and ``is_error=not result.success``. The
inconsistent emit pattern is closed by construction.

Public surface (stable):
    JobControlAction, JobControlContext, JobControlResult,
    JobControlDispatcher
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier override &mdash; the chat UI's tier selector is AUTHORITATIVE;
# the LLM's pick is treated as a hint. The contextvar carries the
# user's choice; submit_job reads it before falling back to llm_tier.
# ---------------------------------------------------------------------------

_USER_TIER_OVERRIDE: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "testai_user_tier_override", default=None,
)


def set_user_tier_override(tier: int | None) -> contextvars.Token:
    """Set the chat-side user-tier override. Returns a token for reset."""
    return _USER_TIER_OVERRIDE.set(tier)


def reset_user_tier_override(token: contextvars.Token) -> None:
    _USER_TIER_OVERRIDE.reset(token)


def get_user_tier_override() -> int | None:
    return _USER_TIER_OVERRIDE.get()


# ---------------------------------------------------------------------------
# Action enum &mdash; the seam between the tool registry and the dispatcher
# ---------------------------------------------------------------------------


class JobControlAction(str, Enum):
    """The seven chat-side job-control actions.

    The enum value is the tool name as it appears in the LLM tool
    schema; the enum name is the Python identifier used by the
    dispatcher internals.
    """

    SUBMIT = "submit_job"
    CANCEL = "cancel_job"
    PAUSE = "pause_job"
    RESUME = "resume_job"
    LIST = "list_jobs"
    STATUS = "get_job_status"
    COMMENT = "comment_on_job"


# ---------------------------------------------------------------------------
# Context &mdash; everything a handler needs to do its work, in one
# immutable carrier. The ToolDispatcher builds this from its own
# fields once per dispatch and passes it in.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JobControlContext:
    """The seam shape: every handler receives this, nothing more.

    ``store`` is the JobSpecStore Protocol (or any object that
    implements the same surface). ``session_id`` and ``agent_id`` are
    the chat session and agent identifiers. ``trace_id`` and
    ``llm_response_id`` are passed through to the
    ``ToolExecutionCompleted`` event. ``event_bus`` is the
    :class:`harness.events.EventBus` (or a no-op stub in tests).
    ``deps`` is the optional :class:`harness.agent.deps.AgentDependencies`
    bundle &mdash; the SUBMIT action needs ``sandbox_manager`` and
    the optional run store.
    """

    store: Any
    session_id: str
    agent_id: str
    trace_id: str
    llm_response_id: str = ""
    event_bus: Any = None
    deps: Any = None


# ---------------------------------------------------------------------------
# Result &mdash; the structured outcome the dispatcher returns. The
# caller uses ``success`` to set ``is_error`` on the completion event;
# ``output`` is the user-facing string the LLM sees; ``spec_id`` is
# for telemetry; ``emit_completed`` lets a handler suppress the
# auto-emit (rare; today only SUBMIT's background-spawn path).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JobControlResult:
    """Structured outcome of a job-control action."""

    output: str
    success: bool
    spec_id: str | None = None
    emit_completed: bool = True


# ---------------------------------------------------------------------------
# Dispatcher &mdash; the one seam. Seven private methods, one public
# dispatch. The private methods are intentionally small (~30-80
# lines each) and all follow the same shape: validate args &rarr;
# resolve target (if any) &rarr; act on the store &rarr; return the
# JobControlResult.
# ---------------------------------------------------------------------------


class JobControlDispatcher:
    """Dispatches one of seven chat-side job-control actions.

    Usage::

        ctx = JobControlContext(
            store=_job_spec_store(),
            session_id="sess-1",
            agent_id="agent-1",
            trace_id="t-1",
            llm_response_id="r-1",
            event_bus=bus,
            deps=agent_deps,
        )
        dispatcher = JobControlDispatcher(ctx)
        result = await dispatcher.dispatch(
            JobControlAction.CANCEL, {"spec_id": "spec-1"},
        )
        # caller emits ToolExecutionCompleted with success=result.success

    The dispatcher owns the action enum and the per-action handler
    methods. ``ToolDispatcher`` is the only intended caller &mdash; it
    builds the context, calls dispatch, and emits the completion
    event.
    """

    def __init__(self, ctx: JobControlContext) -> None:
        self._ctx = ctx

    # ------------------------------------------------------------------
    # Public seam
    # ------------------------------------------------------------------

    async def dispatch(
        self, action: JobControlAction, args: dict[str, Any],
    ) -> JobControlResult:
        """Run ``action`` with ``args``; return the structured result.

        Exceptions inside a handler are caught and converted to a
        failure :class:`JobControlResult` so the caller can always
        emit a ``ToolExecutionCompleted`` with the right
        ``success`` flag.
        """
        handler = self._HANDLERS.get(action)
        if handler is None:
            return JobControlResult(
                output=f"Error: unknown job-control action: {action}",
                success=False,
            )
        try:
            return await handler(self, args)
        except Exception as exc:
            logger.exception("job_control action %s failed", action.value)
            return JobControlResult(
                output=f"Error: {action.value} raised {type(exc).__name__}: {exc}",
                success=False,
            )

    # ------------------------------------------------------------------
    # Handler registry &mdash; the typed dispatch table. Adding an 8th
    # action is one entry here + one method below.
    # ------------------------------------------------------------------

    _HANDLERS: dict[JobControlAction, Callable[["JobControlDispatcher", dict[str, Any]], Awaitable[JobControlResult]]] = {
        JobControlAction.SUBMIT: lambda self, a: self._submit(a),
        JobControlAction.CANCEL: lambda self, a: self._cancel(a),
        JobControlAction.PAUSE: lambda self, a: self._pause(a),
        JobControlAction.RESUME: lambda self, a: self._resume(a),
        JobControlAction.LIST: lambda self, a: self._list(a),
        JobControlAction.STATUS: lambda self, a: self._status(a),
        JobControlAction.COMMENT: lambda self, a: self._comment(a),
    }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(s: str, n: int) -> str:
        """Truncate ``s`` to ``n`` characters with a trailing ellipsis."""
        if len(s) <= n:
            return s
        return s[: n - 1] + "…"

    async def _resolve_target(
        self, args: dict[str, Any],
    ) -> tuple[str | None, str]:
        """Resolve a target ``spec_id`` from explicit or most-recent.

        Same precedence as the legacy ``_resolve_job_target``:
          1. ``args.spec_id`` &mdash; explicit, most authoritative.
          2. ``args.recent == N`` &mdash; the Nth most recent job in
             the session (1-based, default 1).
          3. Most recent job in the session (fallback).

        Returns ``(spec_id, resolution_label)`` or ``(None,
        "reason")`` if no job could be resolved.
        """
        spec_id = (args.get("spec_id") or "").strip()
        if spec_id:
            return spec_id, "spec_id"

        store = self._ctx.store
        if store is None or not self._ctx.session_id:
            return None, "no-store"

        try:
            recent_n = int(args.get("recent", 1))
        except (TypeError, ValueError):
            recent_n = 1
        recent_n = max(1, recent_n)

        try:
            summaries, _total = await store.list_by_session(
                self._ctx.session_id, limit=max(recent_n, 5),
            )
        except Exception:
            return None, "list-failed"
        if not summaries:
            return None, "no-jobs"
        if recent_n > len(summaries):
            return None, f"recent={recent_n} but only {len(summaries)} jobs"
        return summaries[recent_n - 1].spec_id, f"recent={recent_n}"

    async def _session_scoping_check(
        self, target_spec_id: str,
    ) -> str | None:
        """Return an error string if the spec belongs to a different
        session; ``None`` if the spec is in this session or unscoped.

        Mirrors the legacy security check &mdash; chat can only act
        on jobs from its own session.
        """
        store = self._ctx.store
        if store is None:
            return None
        try:
            existing = await store.get(target_spec_id)
        except Exception as exc:
            return f"Error: failed to read spec {target_spec_id}: {exc}"
        if existing is None:
            return f"Error: spec_id={target_spec_id} not found."
        existing_session = (
            (existing.context or {}).get("session_id")
            if isinstance(existing.context, dict) else None
        )
        if existing_session and self._ctx.session_id and existing_session != self._ctx.session_id:
            return (
                f"Error: spec_id={target_spec_id} belongs to a different "
                f"session; chat can only act on jobs from its own session."
            )
        return None

    async def _emit_stream_event(
        self, event_name: str, payload: dict[str, Any],
    ) -> None:
        """Best-effort stream-event emit for dashboard / activity feed."""
        try:
            from harness.api.state import emit_stream_event
            await emit_stream_event(
                self._ctx.session_id or "", event_name, payload,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Handlers &mdash; one per JobControlAction value. All return
    # JobControlResult. None of them emit ToolExecutionCompleted
    # directly; the caller owns that.
    # ------------------------------------------------------------------

    async def _submit(self, args: dict[str, Any]) -> JobControlResult:
        """Submit a new job. Builds a JobSpec, persists it, spawns
        the orchestrator as a background task. Emits
        ``job.submitted`` for the dashboard.

        This is the one handler that does *not* emit a
        ``ToolExecutionCompleted`` (the orchestrator-spawn is
        async; the LLM's "tool returned" semantics are the "Job
        submitted" string, not a tool completion). The
        ``emit_completed=False`` flag in the result tells the
        caller to skip the auto-emit.
        """
        from harness.jobs.spec import JobSpec

        prompt = (args.get("prompt") or "").strip()
        if not prompt:
            return JobControlResult(
                output="Error: `prompt` is required for submit_job",
                success=False,
            )

        repo_url = (args.get("repo_url") or "").strip()
        branch = (args.get("branch") or "main").strip()
        try:
            llm_tier = int(args.get("tier", 1))
        except (TypeError, ValueError):
            llm_tier = 1

        # The user-requested tier (from the chat UI's tier selector)
        # is AUTHORITATIVE. The LLM's pick is a hint.
        user_tier = _USER_TIER_OVERRIDE.get()
        if user_tier is not None:
            try:
                tier = int(user_tier)
            except (TypeError, ValueError):
                tier = llm_tier
        else:
            tier = llm_tier

        capabilities = args.get("capabilities") or []
        if not isinstance(capabilities, list):
            capabilities = []

        # Resolve backend_type: JobSpec arg → sandbox_config.default_backend_type → "local"
        bt = args.get("backend_type", "")
        if not bt or bt not in ("local", "docker", "ssh"):
            try:
                row = self._ctx.deps.store.db.fetchone(
                    "SELECT value FROM sandbox_config WHERE key = 'default_backend_type'",
                )
                if row and row[0] in ("local", "docker", "ssh"):
                    bt = row[0]
                else:
                    bt = "local"
            except Exception:
                bt = "local"

        spec = JobSpec.from_chat_submission(
            prompt=prompt,
            repo_url=repo_url,
            branch=branch,
            tier=tier,
            capabilities=capabilities,
            session_id=self._ctx.session_id,
            agent_id=self._ctx.agent_id,
        )
        spec.backend_type = bt

        # Optionally create a Run row in the run store (best-effort).
        if self._ctx.deps is not None and getattr(self._ctx.deps, "store", None) is not None:
            try:
                from harness.store.adapters.postgres import PostgresRunStore
                run_store = PostgresRunStore(self._ctx.deps.store.db)
                await run_store.create_run(
                    run_id=spec.run_id,
                    session_id=self._ctx.session_id or "",
                    task_type=f"chat-job-tier{tier}",
                    repo_url=repo_url,
                    branch=branch,
                )
                logger.debug(
                    "submit_job: created Run run_id=%s spec_id=%s tier=%s",
                    spec.run_id, spec.spec_id, tier,
                )
            except Exception as exc:
                logger.warning("submit_job: failed to create Run record: %s", exc)

        # Persist the JobSpec through the JobSpecStore protocol.
        try:
            from harness.jobs.spec import _job_spec_store, to_record
            store = _job_spec_store()
            if store is not None:
                await store.save(to_record(spec))
        except Exception as exc:
            logger.warning("submit_job: failed to persist JobSpec: %s", exc)

        # Spawn the orchestrator as a background task. The chat
        # does not wait for the run; the user gets a fast response.
        try:
            from harness.orchestrator import OrchestratorEngine
            engine = OrchestratorEngine()

            async def _run_in_background() -> None:
                try:
                    await engine.run_job_spec(spec)
                except Exception as exc:
                    logger.error(
                        "submit_job: orchestrator run_job_spec FAILED for "
                        "run_id=%s: %s", spec.run_id, exc,
                    )

            asyncio.create_task(_run_in_background())
        except Exception as exc:
            logger.warning("submit_job: could not spawn orchestrator: %s", exc)

        output = (
            f"Job submitted. run_id={spec.run_id}\n"
            f"Prompt: {prompt[:200]}\n"
            f"Repo: {repo_url or '(none)'}\n"
            f"Branch: {branch}\n"
            f"Tier: {tier}\n"
            f"Track progress at: /runs/{spec.run_id}"
        )
        # Submit is special: the orchestrator-spawn is async, so
        # the LLM's "tool returned" semantics are the "Job
        # submitted" string. The caller (ToolDispatcher) skips
        # the auto-emit; we still want the activity feed event.
        await self._emit_stream_event(
            "job.submitted",
            {
                "spec_id": spec.spec_id,
                "run_id": spec.run_id,
                "tier": tier,
                "session_id": self._ctx.session_id,
            },
        )
        return JobControlResult(
            output=output,
            success=True,
            spec_id=spec.spec_id,
            emit_completed=False,
        )

    async def _cancel(self, args: dict[str, Any]) -> JobControlResult:
        """Cancel a running job by spec_id (or most-recent).

        Flips the spec's status to ``cancelled`` in the store;
        the orchestrator's cancel_watcher picks up the change and
        stops the running task.
        """
        target_spec_id, resolved_via = await self._resolve_target(args)
        if target_spec_id is None:
            return JobControlResult(
                output=(
                    "Error: `cancel_job` requires either `spec_id` "
                    "or a recent job in this session."
                ),
                success=False,
            )

        store = self._ctx.store
        if store is None:
            return JobControlResult(
                output=(
                    f"Error: JobSpecStore not configured &mdash; cancel "
                    f"could not be persisted. spec_id={target_spec_id}"
                ),
                success=False,
                spec_id=target_spec_id,
            )

        scope_err = await self._session_scoping_check(target_spec_id)
        if scope_err is not None:
            return JobControlResult(
                output=scope_err, success=False, spec_id=target_spec_id,
            )

        try:
            ok = await store.cancel(target_spec_id)
        except Exception as exc:
            return JobControlResult(
                output=f"Error: cancel failed: {exc}",
                success=False,
                spec_id=target_spec_id,
            )
        if not ok:
            try:
                existing = await store.get(target_spec_id)
                status = existing.status if existing else "unknown"
            except Exception:
                status = "unknown"
            return JobControlResult(
                output=(
                    f"Job {target_spec_id} could not be cancelled "
                    f"(already terminal: status={status})."
                ),
                success=False,
                spec_id=target_spec_id,
            )

        await self._emit_stream_event(
            "job.cancelled",
            {
                "spec_id": target_spec_id,
                "resolved_via": resolved_via,
                "source": "chat",
            },
        )
        return JobControlResult(
            output=(
                f"Cancelled spec_id={target_spec_id} (resolved via "
                f"{resolved_via}). Status: {self._resolve_target} &rarr; "
                f"cancelled. The orchestrator's cancel_watcher will "
                f"stop the running task within ~2s."
            ),
            success=True,
            spec_id=target_spec_id,
        )

    async def _pause(self, args: dict[str, Any]) -> JobControlResult:
        """Pause a job by spec_id (or most-recent).

        Same shape as cancel; the cancel_watcher treats ``paused``
        as a terminal status today (pause == cancel); a future
        sprint can add proper checkpoint-and-return semantics.
        """
        target_spec_id, resolved_via = await self._resolve_target(args)
        if target_spec_id is None:
            return JobControlResult(
                output=(
                    "Error: `pause_job` requires either `spec_id` "
                    "or a recent job in this session."
                ),
                success=False,
            )

        store = self._ctx.store
        if store is None:
            return JobControlResult(
                output="Error: JobSpecStore not configured &mdash; pause could not be persisted.",
                success=False,
                spec_id=target_spec_id,
            )

        scope_err = await self._session_scoping_check(target_spec_id)
        if scope_err is not None:
            return JobControlResult(
                output=scope_err, success=False, spec_id=target_spec_id,
            )

        try:
            ok = await store.pause(target_spec_id)
        except Exception as exc:
            return JobControlResult(
                output=f"Error: pause failed: {exc}",
                success=False,
                spec_id=target_spec_id,
            )
        if not ok:
            try:
                existing = await store.get(target_spec_id)
                status = existing.status if existing else "unknown"
            except Exception:
                status = "unknown"
            return JobControlResult(
                output=(
                    f"Job {target_spec_id} could not be paused "
                    f"(status={status}; only running/queued/submitted jobs "
                    f"can be paused)."
                ),
                success=False,
                spec_id=target_spec_id,
            )

        await self._emit_stream_event(
            "job.paused",
            {
                "spec_id": target_spec_id,
                "resolved_via": resolved_via,
                "source": "chat",
            },
        )
        return JobControlResult(
            output=(
                f"Paused spec_id={target_spec_id} (resolved via {resolved_via}). "
                f"Status: &rarr; paused. The orchestrator's cancel_watcher "
                f"will set the pause signal; the run will exit gracefully "
                f"within ~30s and save a JobCheckpoint. To continue, call "
                f"`resume_job` (the orchestrator will be re-spawned as a "
                f"background task with the saved checkpoint)."
            ),
            success=True,
            spec_id=target_spec_id,
        )

    async def _resume(self, args: dict[str, Any]) -> JobControlResult:
        """Resume a paused job.

        Re-spawns the orchestrator with the saved ``JobCheckpoint``
        (if any). A new ``run_id`` is issued; today the run
        re-starts from the top of the spec. A future sprint can
        replay from the checkpoint's ``subagent_state``.
        """
        target_spec_id, resolved_via = await self._resolve_target(args)
        if target_spec_id is None:
            return JobControlResult(
                output=(
                    "Error: `resume_job` requires either `spec_id` "
                    "or a recent job in this session."
                ),
                success=False,
            )

        store = self._ctx.store
        if store is None:
            return JobControlResult(
                output="Error: JobSpecStore not configured.",
                success=False,
                spec_id=target_spec_id,
            )

        scope_err = await self._session_scoping_check(target_spec_id)
        if scope_err is not None:
            return JobControlResult(
                output=scope_err, success=False, spec_id=target_spec_id,
            )

        try:
            existing = await store.get(target_spec_id)
        except Exception as exc:
            return JobControlResult(
                output=f"Error: failed to read spec {target_spec_id}: {exc}",
                success=False,
                spec_id=target_spec_id,
            )
        if existing is None:
            return JobControlResult(
                output=f"Error: spec_id={target_spec_id} not found.",
                success=False,
                spec_id=target_spec_id,
            )
        if existing.status != "paused":
            return JobControlResult(
                output=(
                    f"Error: spec_id={target_spec_id} is not paused "
                    f"(status={existing.status}). Nothing to resume."
                ),
                success=False,
                spec_id=target_spec_id,
            )

        try:
            from harness.orchestrator import OrchestratorEngine
            engine = OrchestratorEngine(None)
            result = await engine.run_resumed_job_spec(
                target_spec_id, resumed_by=self._ctx.session_id or "",
            )
        except Exception as exc:
            return JobControlResult(
                output=f"Error: resume spawn failed: {exc}",
                success=False,
                spec_id=target_spec_id,
            )

        if not result.get("resumed"):
            return JobControlResult(
                output=(
                    f"Resume failed for spec_id={target_spec_id}: "
                    f"{result.get('error', 'unknown error')}"
                ),
                success=False,
                spec_id=target_spec_id,
            )

        had_ckpt = bool(result.get("checkpoint"))
        ckpt_line = (
            f"resumed from checkpoint at {result['checkpoint']['paused_at']}"
            if had_ckpt else "started fresh (no checkpoint saved)"
        )
        return JobControlResult(
            output=(
                f"Resumed spec_id={target_spec_id} (resolved via {resolved_via}). "
                f"New run_id={result['run_id']}. {ckpt_line}. "
                f"Status: paused &rarr; running. The orchestrator is "
                f"re-spawned as a background task; track progress at "
                f"/jobs/{target_spec_id}."
            ),
            success=True,
            spec_id=target_spec_id,
        )

    async def _list(self, args: dict[str, Any]) -> JobControlResult:
        """List recent jobs in this session (formatted table)."""
        store = self._ctx.store
        if store is None:
            return JobControlResult(
                output="Error: JobSpecStore not configured &mdash; list unavailable.",
                success=False,
            )
        if not self._ctx.session_id:
            return JobControlResult(
                output="Error: chat session_id unknown; cannot list jobs.",
                success=False,
            )

        try:
            limit = int(args.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        try:
            summaries, _total = await store.list_by_session(
                self._ctx.session_id, limit=limit,
            )
        except Exception as exc:
            return JobControlResult(
                output=f"Error: list_by_session failed: {exc}",
                success=False,
            )

        if not summaries:
            return JobControlResult(
                output=f"No jobs in session {self._ctx.session_id}.",
                success=True,
            )

        lines = [f"Recent jobs in session {self._ctx.session_id}:"]
        for s in summaries:
            cost = (
                f"${s.latest_run_cost_usd:.3f}"
                if getattr(s, "latest_run_cost_usd", None) is not None else "&mdash;"
            )
            dur = (
                f"{s.latest_run_duration_s:.1f}s"
                if getattr(s, "latest_run_duration_s", None) is not None else "&mdash;"
            )
            lines.append(
                f"- {s.spec_id[:16]}  status={s.status:9s}  "
                f"tier={s.tier}  cost={cost:>8s}  dur={dur:>7s}  "
                f"{self._truncate(getattr(s, 'prompt', '') or '', 60)}"
            )
        return JobControlResult(
            output="\n".join(lines), success=True,
        )

    async def _status(self, args: dict[str, Any]) -> JobControlResult:
        """Return a structured status summary for one job."""
        target_spec_id, resolved_via = await self._resolve_target(args)
        if target_spec_id is None:
            return JobControlResult(
                output=(
                    "Error: `get_job_status` requires either `spec_id` "
                    "or a recent job in this session."
                ),
                success=False,
            )

        store = self._ctx.store
        if store is None:
            return JobControlResult(
                output="Error: JobSpecStore not configured.",
                success=False,
                spec_id=target_spec_id,
            )

        try:
            status_obj = await store.get_status(target_spec_id)
        except Exception as exc:
            return JobControlResult(
                output=f"Error: get_status failed: {exc}",
                success=False,
                spec_id=target_spec_id,
            )
        if status_obj is None:
            return JobControlResult(
                output=f"Error: spec_id={target_spec_id} not found.",
                success=False,
                spec_id=target_spec_id,
            )

        return JobControlResult(
            output=(
                f"spec_id={target_spec_id} (resolved via {resolved_via})\n"
                f"  status:   {status_obj.status}\n"
                f"  run_id:   {status_obj.run_id or '&mdash;'}\n"
                f"  started:  {status_obj.started_at or '&mdash;'}\n"
                f"  finished: {getattr(status_obj, 'completed_at', None) or '&mdash;'}\n"
                f"  error:    {self._truncate(status_obj.error or '&mdash;', 200)}"
            ),
            success=True,
            spec_id=target_spec_id,
        )

    async def _comment(self, args: dict[str, Any]) -> JobControlResult:
        """Add a comment to a job's record.

        Persists via the store; the comment surfaces in the Job
        Detail page (and the dashboard).
        """
        target_spec_id, resolved_via = await self._resolve_target(args)
        if target_spec_id is None:
            return JobControlResult(
                output=(
                    "Error: `comment_on_job` requires either `spec_id` "
                    "or a recent job in this session."
                ),
                success=False,
            )

        body = (args.get("body") or "").strip()
        if not body:
            return JobControlResult(
                output="Error: `body` is required for comment_on_job.",
                success=False,
                spec_id=target_spec_id,
            )
        author = (args.get("author") or "").strip() or self._ctx.session_id or "user"
        kind = (args.get("kind") or "comment").strip()
        if kind not in ("comment", "system", "approval"):
            kind = "comment"

        store = self._ctx.store
        if store is None:
            return JobControlResult(
                output="Error: JobSpecStore not configured.",
                success=False,
                spec_id=target_spec_id,
            )

        scope_err = await self._session_scoping_check(target_spec_id)
        if scope_err is not None:
            return JobControlResult(
                output=scope_err, success=False, spec_id=target_spec_id,
            )

        try:
            from harness.store.protocols import JobComment
            comment = JobComment(
                comment_id=uuid.uuid4().hex,
                spec_id=target_spec_id,
                author=author,
                body=body,
                kind=kind,
            )
            await store.add_comment(comment)
        except Exception as exc:
            return JobControlResult(
                output=f"Error: add_comment failed: {exc}",
                success=False,
                spec_id=target_spec_id,
            )
        return JobControlResult(
            output=(
                f"Added {kind} comment to spec_id={target_spec_id} "
                f"(resolved via {resolved_via}, author={author}). "
                f"comment_id={comment.comment_id}. The comment is now "
                f"visible in the Job Detail page."
            ),
            success=True,
            spec_id=target_spec_id,
        )
