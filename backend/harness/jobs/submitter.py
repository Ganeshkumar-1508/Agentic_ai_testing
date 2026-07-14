"""submit_job_to_orchestrator — single entry point for all submission paths.

C08 (per docs/2026-06-21-architecture-decision-tree.md#c08):
  Q5 (locked): all submission paths durable, uniform path.
  Q6 (locked): the canonical ``POST /api/jobs`` endpoint
      accepts a JobSpec directly. The chat's ``submit_job``
      tool and the Job Detail page's resume path funnel
      through this function.

  Q7 step 2: the legacy ``/api/agent/run``,
      ``/api/delegate``, and ``/api/pipeline/from-requirements``
      endpoints have been hard-deleted (no shims). New
      callers must use ``POST /api/jobs``.

The function:
  1. Persists the spec to ``JobSpecStore`` (durable across restarts).
  2. Dispatches to ``OrchestratorEngine.run_job_spec`` (uniform
     dispatch surface — every path gets the same Run lifecycle).
  3. Returns the ``run_id`` so the caller can poll the dashboard.

If either step fails, the spec is still persisted (so the user
can recover it via ``list_jobs``). The ``run_id`` returned may be
``""`` if dispatch failed — callers should treat that as a
soft error and surface a "queued but not started" state.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from harness.jobs.spec import JobSpec, to_record

logger = logging.getLogger(__name__)


async def submit_job_to_orchestrator(
    spec: JobSpec,
    *,
    job_spec_store: Any = None,
    orchestrator_engine_factory: Any = None,
) -> str:
    """Persist + dispatch a JobSpec. Returns the ``run_id``.

    Args:
      spec: The :class:`JobSpec` to submit. The caller has
        already filled in all the required fields (prompt,
        repo_url, branch, tier, capabilities).
      job_spec_store: The :class:`JobSpecStore` to persist to.
        If ``None``, falls back to the module-level
        ``_job_spec_store()`` from :mod:`harness.jobs.spec`.
      orchestrator_engine_factory: Optional callable that
        returns an :class:`OrchestratorEngine` instance. If
        ``None``, the dispatcher uses the default
        ``OrchestratorEngine.create_default()`` (the same
        factory the chat's submit_job handler uses).

    Returns:
      The ``run_id`` of the resulting Run. May be ``""`` if
      dispatch failed but persistence succeeded.
    """
    # Lazy imports to avoid circular dependencies at module load.
    from harness.jobs.spec import _job_spec_store as _module_store

    logger.info("SUBMIT: Starting for spec_id=%s", spec.spec_id)
    store = job_spec_store if job_spec_store is not None else _module_store()
    record = to_record(spec)
    print(f"SUBMIT: Starting for spec_id={spec.spec_id}")

    # Step 1: persist (durable across restarts).
    persisted = False
    if store is not None:
        try:
            await asyncio.wait_for(store.save(record), timeout=15)
            persisted = True
            logger.info("SUBMIT: Persisted spec %s", spec.spec_id)
        except asyncio.TimeoutError:
            logger.error("submit_job: persist TIMED OUT for spec_id=%s", spec.spec_id)
        except Exception as exc:
            logger.error(
                "submit_job_to_orchestrator: persist failed spec_id=%s err=%s",
                spec.spec_id, exc,
            )
    else:
        logger.warning(
            "submit_job_to_orchestrator: no job_spec_store wired; "
            "spec %s will not be persisted",
            spec.spec_id,
        )

    # Step 2: dispatch.
    dispatched = False
    _caught_error = ""
    try:
        engine = (
            orchestrator_engine_factory()
            if orchestrator_engine_factory is not None
            else _default_orchestrator_engine()
        )
        if engine is not None:
            result = await engine.run_job_spec(spec)
            run_id = str(result.get("run_id") or spec.run_id or "")
            try:
                spec.attach_run_id(run_id)
            except Exception:
                pass
            # Step 2b: auto-create thread AFTER orchestrator returns real run_id
            if run_id:
                try:
                    await asyncio.wait_for(_auto_create_thread_for_spec(spec), timeout=5)
                except (asyncio.TimeoutError, Exception) as exc:
                    logger.warning("submit_job: thread auto-create failed: %s (non-fatal)", exc)

            if persisted:
                result_error = str(result.get("error") or "")
                result_status = "running" if (run_id and not result_error) else "failed"
                try:
                    if store is not None:
                        await store.update_status(
                            spec.spec_id, result_status,
                            run_id=run_id if run_id else None,
                            error=result_error[:500] if result_error else None,
                        )
                except Exception:
                    pass
            dispatched = True
            return run_id
    except Exception as exc:
        logger.error(
            "submit_job_to_orchestrator: dispatch failed spec_id=%s err=%s",
            spec.spec_id, exc,
        )
        _caught_error = str(exc)

    # Dispatch failed but we may have persisted. Surface a soft error.
    error_msg = _caught_error if _caught_error else "Dispatch failed"
    if persisted:
        logger.warning(
            "submit_job_to_orchestrator: spec_id=%s persisted but not "
            "dispatched (returned empty run_id): %s",
            spec.spec_id, error_msg,
        )
        try:
            if store is not None:
                await store.update_status(
                    spec.spec_id, "failed", error=error_msg[:500],
                )
        except Exception:
            pass
    return ""


def _default_orchestrator_engine() -> Any:
    """Build the default :class:`OrchestratorEngine`.

    Tries the import lazily so this module can be loaded in
    environments where the orchestrator's deps aren't available
    (e.g. unit tests).
    """
    try:
        from harness.orchestrator import OrchestratorEngine
        return OrchestratorEngine.create_default()
    except Exception as exc:
        logger.debug(
            "submit_job_to_orchestrator: OrchestratorEngine unavailable: %s",
            exc,
        )
        return None


def new_spec_id() -> str:
    """Helper: generate a fresh spec id (UUID v4 string)."""
    return str(uuid.uuid4())


async def _auto_create_thread_for_spec(spec: JobSpec) -> None:
    """Create the chat thread 1:1 with this spec's run.

    Best-effort: a failure here logs + continues, because the
    thread is recoverable (a user can list threads and find the
    run, or the auto-create on a later call to the same run will
    dedupe). The session_id comes from ``spec.context.session_id``
    (typed JobContext or dict); absent that, an empty string is
    passed and the thread is keyed by run_id only.

    The thread is keyed **strictly by run_id**: we do NOT fall
    back to looking up by session_id, because a session can
    contain multiple runs and we'd otherwise return an old thread
    from a previous run. Threads are 1:1 with runs.
    """
    if not spec.run_id:
        return
    session_id = ""
    ctx = spec.context
    if ctx is not None:
        if hasattr(ctx, "session_id"):
            session_id = ctx.session_id or ""
        elif isinstance(ctx, dict):
            session_id = str(ctx.get("session_id") or "")
    try:
        from harness.chat.threads import (
            append_message,
            create_thread,
            get_thread_by_run_id,
            new_message_id,
        )
        existing = await get_thread_by_run_id(spec.run_id, db=None)
        if existing is not None:
            return
        seed_title = (spec.prompt or "New run")[:80]
        thread = await create_thread(
            title=seed_title,
            run_id=spec.run_id,
            session_id=session_id or None,
            source="run",
            db=None,
        )
        if spec.prompt and spec.prompt.strip():
            await append_message(
                thread_id=thread.id,
                role="user",
                content=spec.prompt.strip(),
                message_id=new_message_id(),
                db=None,
            )
    except Exception as exc:
        logger.warning(
            "submit_job_to_orchestrator: auto-create thread failed for run_id=%s: %s",
            spec.run_id, exc,
        )


__all__ = ["submit_job_to_orchestrator", "new_spec_id"]
