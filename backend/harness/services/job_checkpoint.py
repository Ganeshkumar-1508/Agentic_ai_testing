"""JobCheckpoint — per-spec pause-checkpoint storage.

When the orchestrator's :func:`run_single` observes the pause
signal, it saves a :class:`JobCheckpoint` before returning
cleanly. The checkpoint captures:

  - spec_id, run_id — which run was paused
  - last_result    — the partial result the run produced
                     (e.g. test files written, PRs opened)
  - paused_at      — ISO timestamp
  - paused_by      — the session that issued the pause
                     (so audit knows who clicked "pause")
  - subagent_state — a snapshot of which subagents had
                     completed, which were in-flight, etc.

The subagent_state shape (item 5 — true replay):
  {
    "completed_subagents": ["sa-1", "sa-3", "sa-5"],
    "in_flight_subagents": ["sa-7"],
    "completed_count": 3,
    "in_flight_count": 1,
    "paused_at_phase": "pre_coordinator",
  }

On resume, the LLM gets this state in the spec's context
(``resumed_subagent_state``) and can skip re-doing work that
was already done. The orchestrator itself doesn't reconstruct
the subagent tree — the LLM does the actual skipping.

Storage backends (item 6):

  - **In-memory** (default, the MVP): the ``_store`` dict
    below. Process-local; lost on restart.

  - **Postgres-backed** (item 6, production): a
    ``PostgresJobCheckpointStore`` instance wired via
    :func:`set_checkpoint_backend`. The checkpoint lives
    in the ``job_checkpoints`` table and survives process
    restarts. The module-level :func:`save_checkpoint` /
    :func:`get_checkpoint` / :func:`pop_checkpoint` route
    through whichever backend is active.

Why both: the in-memory backend is the default for
local dev / tests / single-process deployments. The
Postgres backend is for production multi-worker deployments
where the checkpoint must survive an orchestrator restart.
The orchestrator itself doesn't need to know which
backend is active.

Per Hermes/openclaude/ohmo research (2026-06-21): none of
the other agent harnesses have a "JobCheckpoint" concept.
Hermes uses an in-memory `_active_subagents` registry
(process-local, no durability). OpenCode replays from
transcript (no separate state). OpenHands pauses at the
Docker container level. OpenHarness/ohmo saves the full
message history. Our JobCheckpoint is a unique
contribution — it gives the LLM the per-subagent state
needed for true replay (item 5).

Public surface (stable):
  - save_checkpoint(spec_id, run_id, last_result, paused_by, subagent_state=None)
  - get_checkpoint(spec_id) -> JobCheckpoint | None
  - pop_checkpoint(spec_id) -> JobCheckpoint | None
  - list_checkpoints() -> list[JobCheckpoint]
  - clear_checkpoints()                                (test-only)
  - set_checkpoint_backend(pg_store)                   (production)
  - get_checkpoint_backend() -> str                     ("memory" | "postgres")
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class JobCheckpoint:
    """A pause-checkpoint for a single spec."""
    spec_id: str
    run_id: str
    last_result: Dict[str, Any]
    paused_at: str  # ISO 8601 UTC
    paused_by: str
    subagent_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "run_id": self.run_id,
            "last_result": self.last_result,
            "paused_at": self.paused_at,
            "paused_by": self.paused_by,
            "subagent_state": self.subagent_state,
        }

    def __repr__(self) -> str:
        return (
            f"JobCheckpoint(spec_id={self.spec_id!r}, run_id={self.run_id!r}, "
            f"paused_at={self.paused_at!r}, paused_by={self.paused_by!r})"
        )


# ---------------------------------------------------------------------------
# Storage backend
# ---------------------------------------------------------------------------

# In-memory store (default). Keyed by spec_id. A spec can
# have at most one checkpoint at a time — a new pause
# overwrites the old one (with a fresh timestamp).
_store: Dict[str, JobCheckpoint] = {}

# Optional Postgres-backed store. When set (via
# ``set_checkpoint_backend``), the module-level
# ``save_checkpoint`` / ``get_checkpoint`` / ``pop_checkpoint``
# route through it instead of the in-memory dict.
_pg_store: Optional[Any] = None  # PostgresJobCheckpointStore
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_checkpoint_backend() -> str:
    """Return the active backend name: ``"memory"`` or ``"postgres"``."""
    with _lock:
        return "postgres" if _pg_store is not None else "memory"


def set_checkpoint_backend(pg_store: Any) -> None:
    """Switch to a Postgres-backed checkpoint store.

    The argument is a ``PostgresJobCheckpointStore`` instance
    (or any object with the same ``save_checkpoint`` /
    ``get_checkpoint`` / ``pop_checkpoint`` /
    ``list_checkpoints`` async methods). Production code
    wires this at startup:

        from harness.store.adapters.postgres import (
            PostgresJobCheckpointStore,
        )
        from harness.services.job_checkpoint import (
            set_checkpoint_backend,
        )
        set_checkpoint_backend(PostgresJobCheckpointStore(db))

    After this call, all module-level checkpoint operations
    (``save_checkpoint``, etc.) route through the Postgres
    store. The in-memory ``_store`` is bypassed.

    Pass ``None`` to switch back to the in-memory backend
    (mostly used in tests).
    """
    global _pg_store
    with _lock:
        _pg_store = pg_store


def _to_ckpt_dict(ckpt: JobCheckpoint) -> Dict[str, Any]:
    """Normalize to the dict shape callers expect."""
    return {
        "spec_id": ckpt.spec_id,
        "run_id": ckpt.run_id,
        "last_result": dict(ckpt.last_result or {}),
        "paused_at": ckpt.paused_at,
        "paused_by": ckpt.paused_by,
        "subagent_state": ckpt.subagent_state,
    }


def save_checkpoint(
    spec_id: str,
    run_id: str,
    last_result: Dict[str, Any],
    paused_by: str,
    subagent_state: Optional[Dict[str, Any]] = None,
) -> JobCheckpoint:
    """Save a checkpoint for ``spec_id``. Overwrites any existing.

    **Synchronous, in-memory only.** For the Postgres-backed
    store (item 6), use :func:`asave_checkpoint` instead —
    it's async and routes through whichever backend is
    active.

    The orchestrator uses :func:`asave_checkpoint` so the
    production path works with both backends. This sync
    function is the dev/test path and stays unchanged.
    """
    with _lock:
        pg = _pg_store
    if pg is not None:
        raise RuntimeError(
            "save_checkpoint is sync-only; the Postgres backend "
            "is active. Use `await asave_checkpoint(...)` instead."
        )
    # In-memory default.
    ckpt = JobCheckpoint(
        spec_id=spec_id,
        run_id=run_id,
        last_result=dict(last_result or {}),
        paused_at=_now_iso(),
        paused_by=paused_by,
        subagent_state=subagent_state,
    )
    _store[spec_id] = ckpt
    return ckpt


async def asave_checkpoint(
    spec_id: str,
    run_id: str,
    last_result: Dict[str, Any],
    paused_by: str,
    subagent_state: Optional[Dict[str, Any]] = None,
) -> JobCheckpoint:
    """Async variant of :func:`save_checkpoint`.

    Routes through the active backend. The Postgres path's
    methods are async; the in-memory path is wrapped in
    ``asyncio.shield``-style direct call (no event loop
    needed). Used by the orchestrator's ``pause_checkpoint``
    and ``_check_pause_for_spec`` helpers.
    """
    with _lock:
        pg = _pg_store
    if pg is not None:
        d = await pg.save_checkpoint(
            spec_id=spec_id, run_id=run_id,
            last_result=last_result, paused_by=paused_by,
            subagent_state=subagent_state,
        )
        return _hydrate_ckpt(d)
    # In-memory default — wrap in a coroutine for a unified API.
    return save_checkpoint(
        spec_id=spec_id, run_id=run_id,
        last_result=last_result, paused_by=paused_by,
        subagent_state=subagent_state,
    )


def get_checkpoint(spec_id: str) -> Optional[JobCheckpoint]:
    """Return the checkpoint for ``spec_id`` or None (sync)."""
    with _lock:
        pg = _pg_store
    if pg is not None:
        raise RuntimeError(
            "get_checkpoint is sync-only; the Postgres backend "
            "is active. Use `await aget_checkpoint(...)` instead."
        )
    return _store.get(spec_id)


async def aget_checkpoint(spec_id: str) -> Optional[JobCheckpoint]:
    """Async variant of :func:`get_checkpoint`."""
    with _lock:
        pg = _pg_store
    if pg is not None:
        d = await pg.get_checkpoint(spec_id)
        if d is None:
            return None
        return _hydrate_ckpt(d)
    return _store.get(spec_id)


def pop_checkpoint(spec_id: str) -> Optional[JobCheckpoint]:
    """Return and remove the checkpoint for ``spec_id`` (sync)."""
    with _lock:
        pg = _pg_store
    if pg is not None:
        raise RuntimeError(
            "pop_checkpoint is sync-only; the Postgres backend "
            "is active. Use `await apop_checkpoint(...)` instead."
        )
    return _store.pop(spec_id, None)


async def apop_checkpoint(spec_id: str) -> Optional[JobCheckpoint]:
    """Async variant of :func:`pop_checkpoint`."""
    with _lock:
        pg = _pg_store
    if pg is not None:
        d = await pg.pop_checkpoint(spec_id)
        if d is None:
            return None
        return _hydrate_ckpt(d)
    return _store.pop(spec_id, None)


def list_checkpoints() -> List[JobCheckpoint]:
    """Return all checkpoints (sync, for tests + debug)."""
    with _lock:
        pg = _pg_store
    if pg is not None:
        raise RuntimeError(
            "list_checkpoints is sync-only; the Postgres backend "
            "is active. Use `await alist_checkpoints(...)` instead."
        )
    return list(_store.values())


async def alist_checkpoints() -> List[JobCheckpoint]:
    """Async variant of :func:`list_checkpoints`."""
    with _lock:
        pg = _pg_store
    if pg is not None:
        rows = await pg.list_checkpoints()
        return [_hydrate_ckpt(d) for d in rows]
    return list(_store.values())


def _hydrate_ckpt(d: Dict[str, Any]) -> JobCheckpoint:
    """Convert a row dict (from the Postgres store) into a
    ``JobCheckpoint``. Centralizes the shape conversion so
    the async variants don't duplicate the logic.
    """
    return JobCheckpoint(
        spec_id=d["spec_id"], run_id=d["run_id"],
        last_result=d["last_result"],
        paused_at=d["paused_at"],
        paused_by=d["paused_by"],
        subagent_state=d.get("subagent_state"),
    )


def clear_checkpoints() -> None:
    """Clear in-memory checkpoints. Test-only.

    Does NOT clear the Postgres store — production code
    should never call this. Tests can call
    ``set_checkpoint_backend(None)`` to switch back to
    the in-memory backend, then ``clear_checkpoints()``.
    """
    _store.clear()


# ---------------------------------------------------------------------------
# Subagent tracker (item 5 — true replay)
# ---------------------------------------------------------------------------

# In-memory per-spec subagent state. The orchestrator's
# ``run_job_spec`` creates a tracker at entry; pause_checkpoint
# reads the state at pause time. The tracker subscribes to
# ``subagent.completed`` events on the EventSourceSink to
# accumulate completed subagent IDs.
#
# Tests can ``_reset_all_trackers()`` to clear between test
# cases.
_trackers: Dict[str, "_SubagentTracker"] = {}


class _SubagentTracker:
    """Per-spec tracker of completed/in-flight subagents.

    Tracks subagent completion two ways (belt + suspenders):
      1. Live: subscribes to ``subagent.completed`` events on the
         EventSourceSink during this run.
      2. Durable: on startup, queries the ``sessions`` DB table for
         child sessions whose ``parent_session_id`` matches and
         ``status = 'completed'``. This survives process restarts.

    The ``snapshot()`` is included in JobCheckpoint on pause so the
    orchestrator's resume path can skip re-doing completed work.
    """

    def __init__(self, spec_id: str, session_id: str) -> None:
        self.spec_id = spec_id
        self.session_id = session_id
        self.completed: set[str] = set()
        self.spawned: set[str] = set()
        self._task: Optional[asyncio.Task] = None
        self._stopped = False

    async def _seed_from_db(self) -> None:
        """Seed completed subagents from the sessions table.

        Queries child sessions whose ``parent_session_id`` matches
        this tracker's session and ``status = 'completed'``. Runs
        once on startup so completed work survives restart.
        """
        try:
            from harness.memory.db_context import get_db
            db = get_db()
            if db is None:
                return
            rows = await db.fetch(
                "SELECT id FROM sessions "
                "WHERE parent_session_id = $1 AND status = 'completed'",
                self.session_id,
            )
            for row in rows:
                # id is ``subagent-{subagent_id}`` — extract the id
                sid = row["id"]
                if sid and sid.startswith("subagent-"):
                    self.completed.add(sid[len("subagent-"):])
        except Exception as exc:
            logger.debug("tracker seed from DB failed: %s", exc)

    def start(self) -> None:
        """Start the event-listener task. Idempotent.
        
        Seeds completed set from DB on first start so completed
        work survives process restarts.
        """
        if self._task is not None and not self._task.done():
            return
        if not self.completed:
            # Fire-and-forget the DB seed — it's best-effort and
            # should not delay the event listener task.
            try:
                import asyncio
                asyncio.create_task(self._seed_from_db())
            except Exception:
                pass
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the event-listener task. Idempotent."""
        self._stopped = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self) -> None:
        try:
            from harness.events import EventSourceSink
            from harness.api.state import get_event_source_sink
        except ImportError:
            return
        try:
            sink = get_event_source_sink()
        except Exception:
            return
        if sink is None:
            return
        queue = sink.subscribe(self.session_id or "")
        try:
            while not self._stopped:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                # event is a tuple (event_name, payload_dict) or
                # a StreamEvent. We use ``type(event).__name__``
                # for the latter; the former is straightforward.
                if isinstance(event, tuple) and len(event) >= 2:
                    name, payload = event[0], event[1]
                else:
                    name = getattr(event, "type_name", None) or type(event).__name__
                    payload = getattr(event, "data", None) or {}
                if not isinstance(payload, dict):
                    payload = {}
                if name == "subagent.completed":
                    sa_id = payload.get("subagent_id")
                    if sa_id:
                        self.completed.add(str(sa_id))
                elif name == "subagent.spawned":
                    sa_id = payload.get("subagent_id")
                    if sa_id:
                        self.spawned.add(str(sa_id))
        finally:
            try:
                sink.unsubscribe(self.session_id or "", queue)
            except Exception:
                pass

    def snapshot(self) -> Dict[str, Any]:
        """Return the current state as a serializable dict.

        Shape matches the ``subagent_state`` field of
        :class:`JobCheckpoint`. The ``durable`` flag is ``True``
        when data was seeded from the DB (survives restart).
        """
        in_flight = self.spawned - self.completed
        return {
            "completed_subagents": sorted(self.completed),
            "in_flight_subagents": sorted(in_flight),
            "completed_count": len(self.completed),
            "in_flight_count": len(in_flight),
            "durable": True,
        }


def start_tracker(spec_id: str, session_id: str) -> _SubagentTracker:
    """Create + start a tracker for ``spec_id``. Idempotent."""
    existing = _trackers.get(spec_id)
    if existing is not None:
        return existing
    t = _SubagentTracker(spec_id, session_id)
    _trackers[spec_id] = t
    t.start()
    return t


def get_tracker(spec_id: str) -> Optional[_SubagentTracker]:
    return _trackers.get(spec_id)


def stop_and_remove_tracker(spec_id: str) -> Optional[Dict[str, Any]]:
    """Stop the tracker, return its final snapshot, and remove
    it from the registry. Returns None if no tracker exists.
    """
    t = _trackers.pop(spec_id, None)
    if t is None:
        return None
    # Note: we don't await stop() here (caller is sync).
    # The background task will exit on its own. Tests can
    # explicitly await ``await stop_tracker(...)`` if they
    # need to wait.
    return t.snapshot()


async def stop_tracker(spec_id: str) -> Optional[Dict[str, Any]]:
    """Async version: stop the tracker, return its final snapshot.
    """
    t = _trackers.pop(spec_id, None)
    if t is None:
        return None
    await t.stop()
    return t.snapshot()


def _reset_all_trackers() -> None:
    """Clear all trackers. Test-only."""
    _trackers.clear()


__all__ = [
    "JobCheckpoint",
    "save_checkpoint",
    "get_checkpoint",
    "pop_checkpoint",
    "list_checkpoints",
    "clear_checkpoints",
    "start_tracker",
    "get_tracker",
    "stop_and_remove_tracker",
    "stop_tracker",
    "_reset_all_trackers",
]
