"""Subagent public API &mdash; the unified module for the entire subagent system.

Before C02-collapse: callers had to import from 7 separate modules
(``subagent_types``, ``subagent_runtime``, ``subagent_runner``,
``subagent_persistence``, ``subagent_session``, ``subagent_prompt``,
plus the re-export shim). The leak was that
``from harness.tools.subagent import X`` worked, but it was a
re-export shim pointing at the 7 modules, with no single file that
documented the public surface.

After C02-collapse: **this module IS the subagent system.** The 6
implementation files (5 actually exist on disk; the report miscounted
and said ``subagent_persist`` but the real file is
``subagent_persistence``) are now thin re-export shims that just
re-import from here. New code should use this module directly.

The 5 sections inside this file (each prefixed with a section header
matching the old file name) are the only private seams:

| Section               | Old file                       | LOC |
|-----------------------|--------------------------------|-----|
| Constants + dataclasses | subagent_types.py            | 113 |
| Runtime state + circuit breaker | subagent_runtime.py | 161 |
| Session lifecycle     | subagent_session.py            | 109 |
| DB persistence + collection | subagent_persistence.py  | 167 |
| Retry + fan-out       | subagent_runner.py             | 131 |
| Prompt + toolset helpers | subagent_prompt.py          | 112 |
| Subagent class        | (new in Phase 1)               | 470 |

Pattern: Greptile's "agent-in-agent orchestration" converged on a
single ``spawn(goal, role) -> SubagentResult`` shape (per the
agent-in-agent breakdown). The :class:`Subagent` class mirrors that.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stdlib
# ---------------------------------------------------------------------------
import asyncio
import dataclasses
import datetime
import logging
import os
import random
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ===========================================================================
# SECTION 1: Constants + dataclasses (was subagent_types.py)
# ===========================================================================

# --- Retry defaults (configurable via env vars) ---
DEFAULT_RETRY_MAX_ATTEMPTS = int(os.environ.get("SUBAGENT_RETRY_MAX_ATTEMPTS", "3"))
DEFAULT_RETRY_BASE_DELAY = float(os.environ.get("SUBAGENT_RETRY_BASE_DELAY", "1.0"))
DEFAULT_RETRY_MAX_DELAY = float(os.environ.get("SUBAGENT_RETRY_MAX_DELAY", "16.0"))

# --- Constants shared externally ---
DEFAULT_MAX_CONCURRENT_CHILDREN = 10
CHILD_TIMEOUT_SECONDS = 1000

# --- Cancellation ---
CANCEL_GRACE_PERIOD_SECONDS = 5.0

# Toolset restrictions
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",
    "skill_manage",
])


@dataclasses.dataclass
class EvidenceClaim:
    """One verifiable claim about what a subagent did (F6 deepening).

    Pattern from Greptile TREX: a subagent's output is not a claim
    until it's backed by an artifact the reviewer can re-run.
    ``artifact_path`` is a filesystem path (or a URL) pointing at the
    evidence; ``verified`` is False until something downstream
    (typically a human reviewer or a re-run) has confirmed it.
    """
    claim: str
    artifact_path: str
    mime: str = "text/plain"
    verified: bool = False
    captured_at: float = 0.0


@dataclasses.dataclass
class SubagentResult:
    """Result of a single subagent invocation, with full observability metadata."""
    subagent_id: str
    status: str                                       # "ok" | "error" | "cancelled"
    output: Any = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_sec: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    retries: int = 0
    fallback_used: str | None = None
    # Wire of C02 (F6 deepening): per-finding evidence bundle the
    # parent agent or the dashboard can verify before acting on the
    # subagent's output. Empty list = subagent produced no
    # artifacts; downstream code can treat that as a silent-failure
    # signal.
    evidence: list[EvidenceClaim] = dataclasses.field(default_factory=list)
    # Wire of C02 (F12 deepening): the detector strategy that
    # flagged this result's success/failure. Empty when the
    # ``RunSuccessDetector`` was bypassed (e.g. depth error).
    detector_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subagent_id": self.subagent_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_sec": self.duration_sec,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "model": self.model,
            "retries": self.retries,
            "fallback_used": self.fallback_used,
            "evidence": [
                {
                    "claim": c.claim,
                    "artifact_path": c.artifact_path,
                    "mime": c.mime,
                    "verified": c.verified,
                    "captured_at": c.captured_at,
                } for c in self.evidence
            ],
            "detector_name": self.detector_name,
        }


@dataclasses.dataclass
class _AgentResult:
    """Internal: what the agent loop returned + token usage it observed."""
    output: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    tool_calls_count: int = 0


# ===========================================================================
# SECTION 2: Runtime state + circuit breaker (was subagent_runtime.py)
# ===========================================================================

_spawn_paused = False
_spawn_pause_lock = threading.Lock()

_active_subagents: dict[str, dict[str, Any]] = {}
_active_subagents_lock = threading.Lock()

_pending_results: dict[str, asyncio.Future] = {}
_pending_results_lock = threading.Lock()

# Spawn-rate circuit breaker. The deque holds timestamps of recent
# spawns; if more than ``_SPAWN_RATE_LIMIT`` happen within
# ``_SPAWN_RATE_WINDOW`` seconds, :func:`check_spawn_rate` returns
# ``(True, "...")`` and the Subagent.spawn() caller aborts.
_SPAWN_RATE_LIMIT = int(os.environ.get("TESTAI_SPAWN_RATE_LIMIT", "10"))
_SPAWN_RATE_WINDOW = float(os.environ.get("TESTAI_SPAWN_RATE_WINDOW", "30"))
_SPAWN_RATE_COOLDOWN = float(os.environ.get("TESTAI_SPAWN_RATE_COOLDOWN", "60"))
_spawn_timestamps: deque[float] = deque()
_spawn_timestamps_lock = threading.Lock()
_spawn_rate_tripped_at: float = 0.0


def check_spawn_rate() -> tuple[bool, str | None]:
    """Circuit breaker on the spawn rate.

    Returns ``(True, reason)`` when spawning is currently rate-limited
    and ``(False, None)`` when a new spawn is permitted. The check has
    two layers:

    1. **Sliding window**: if more than ``_SPAWN_RATE_LIMIT`` spawns
       happened in the last ``_SPAWN_RATE_WINDOW`` seconds, mark the
       breaker as tripped.
    2. **Cooldown**: once tripped, stay tripped for
       ``_SPAWN_RATE_COOLDOWN`` seconds (default 60s) so a runaway
       orchestrator can't instantly recover.

    Pattern from oh-my-opencode's circuit breaker. Catches the
    Claude Code #68110 failure mode (48+ background agents).
    """
    global _spawn_rate_tripped_at
    now = time.monotonic()
    # If we're in cooldown, refuse.
    if _spawn_rate_tripped_at and (now - _spawn_rate_tripped_at) < _SPAWN_RATE_COOLDOWN:
        remaining = int(_SPAWN_RATE_COOLDOWN - (now - _spawn_rate_tripped_at))
        return True, f"spawn_rate_cooldown_{remaining}s_remaining"
    with _spawn_timestamps_lock:
        # Drop timestamps outside the window.
        cutoff = now - _SPAWN_RATE_WINDOW
        while _spawn_timestamps and _spawn_timestamps[0] < cutoff:
            _spawn_timestamps.popleft()
        if len(_spawn_timestamps) >= _SPAWN_RATE_LIMIT:
            _spawn_rate_tripped_at = now
            logger.warning(
                "Spawn rate limit tripped: %d spawns in last %ss; cooling down for %ss",
                len(_spawn_timestamps), _SPAWN_RATE_WINDOW, _SPAWN_RATE_COOLDOWN,
            )
            return True, (
                f"spawn_rate_limit_{_SPAWN_RATE_LIMIT}_in_"
                f"{int(_SPAWN_RATE_WINDOW)}s"
            )
        # Allowed: record this spawn attempt (success path also
        # calls record_spawn() so a flurry of successful spawns
        # still trips the breaker).
        return False, None


def record_spawn() -> None:
    """Record a successful subagent spawn for the rate window."""
    now = time.monotonic()
    with _spawn_timestamps_lock:
        _spawn_timestamps.append(now)


def spawn_rate_status() -> dict[str, Any]:
    """Read-only snapshot of the rate window. Used by the dashboard."""
    now = time.monotonic()
    with _spawn_timestamps_lock:
        cutoff = now - _SPAWN_RATE_WINDOW
        active = sum(1 for t in _spawn_timestamps if t >= cutoff)
    return {
        "limit": _SPAWN_RATE_LIMIT,
        "window_seconds": _SPAWN_RATE_WINDOW,
        "cooldown_seconds": _SPAWN_RATE_COOLDOWN,
        "active_in_window": active,
        "cooldown_remaining": max(
            0, int(_SPAWN_RATE_COOLDOWN - (now - _spawn_rate_tripped_at))
        ) if _spawn_rate_tripped_at else 0,
    }


def set_spawn_paused(paused: bool) -> bool:
    global _spawn_paused
    with _spawn_pause_lock:
        _spawn_paused = paused
    return _spawn_paused


def is_spawn_paused() -> bool:
    with _spawn_pause_lock:
        return _spawn_paused


def active_subagents() -> list[dict[str, Any]]:
    with _active_subagents_lock:
        return list(_active_subagents.values())


def interrupt_subagent(subagent_id: str) -> bool:
    with _active_subagents_lock:
        record = _active_subagents.get(subagent_id)
        if record:
            record["interrupted"] = True
            asyncio.ensure_future(_fire_subagent_stop(subagent_id, record))
            return True
    return False


def drain_pending_results() -> dict[str, str]:
    results: dict[str, str] = {}
    with _pending_results_lock:
        for sid, future in list(_pending_results.items()):
            if future.done():
                try:
                    results[sid] = future.result()
                except Exception as e:
                    results[sid] = f"Error: {e}"
                del _pending_results[sid]
    return results


async def _fire_subagent_stop(subagent_id: str, record: dict[str, Any]) -> None:
    try:
        from harness.hooks import hooks as _hooks_fn
        await _hooks_fn().invoke("subagent_stop", subagent_id=subagent_id, goal=record.get("goal", ""))
    except Exception:
        pass


# ===========================================================================
# SECTION 3: Session lifecycle (was subagent_session.py)
# ===========================================================================

from harness.memory.db_context import get_db  # noqa: E402  (after section markers)


async def _update_child_session_status(session_id: str, status: str) -> None:
    """Update a subagent session's status after completion. Non-fatal on failure."""
    db = get_db()
    if not db or not getattr(db, "_pool", None):
        return
    try:
        import datetime
        await db.execute(
            "UPDATE sessions SET status = $1, ended_at = $2 WHERE id = $3",
            status, datetime.datetime.now(tz=datetime.timezone.utc), session_id,
        )
    except Exception as e:
        logger.debug("Failed to update session %s status to %s: %s", session_id, status, e)


async def sweep_orphan_sessions(max_age_seconds: int = 3600) -> int:
    """Mark subagent sessions stuck in 'running' for too long as 'failed'.

    Runs as a periodic sweep in the reaper loop. Only targets subagent
    sessions (parent_session_id IS NOT NULL) — root sessions are managed
    by the orchestrator's resume logic.

    Returns the number of sessions marked as failed.
    """
    db = get_db()
    if not db or not getattr(db, "_pool", None):
        return 0
    try:
        result = await db.execute(
            "UPDATE sessions SET status = 'failed', ended_at = NOW(), "
            "end_reason = 'orphan-sweep' "
            "WHERE status = 'running' "
            "AND parent_session_id IS NOT NULL "
            "AND started_at < NOW() - $1::interval",
            f"{max_age_seconds} seconds",
        )
        # Parse "UPDATE N" from result
        count = int(result.split()[-1]) if result and result.startswith("UPDATE") else 0
        if count > 0:
            logger.info("Session reaper: marked %d orphan sessions as failed", count)
        return count
    except Exception as e:
        logger.debug("Session reaper sweep failed: %s", e)
        return 0


async def create_child_session(
    child_session_id: str,
    child_depth: int,
    goal: str,
    model_override: str | None,
    parent_session_id: str | None,
    started_at: float,
) -> None:
    """Create a sessions row for the child agent BEFORE it starts.

    Uses ON CONFLICT so post-completion UPDATE also works.
    Failure is non-fatal &mdash; logged and swallowed.
    """
    db = get_db()
    if not db or not getattr(db, "_pool", None):
        logger.warning("Database not available for worker session creation")
        return
    try:
        now_dt = datetime.datetime.now(tz=datetime.timezone.utc)
        goal_str = str(goal)[:500] if goal else ""
        inherited_backend = "local"
        if parent_session_id:
            parent_row = await db.fetchrow(
                "SELECT backend_type FROM sessions WHERE id = $1",
                parent_session_id,
            )
            if parent_row and parent_row.get("backend_type"):
                inherited_backend = parent_row["backend_type"]
        await db.execute(
            "INSERT INTO sessions (id, source, status, depth, agent_role, goal, model, started_at, parent_session_id, backend_type) "
            "VALUES ($1, 'delegation', 'running', $2, 'subagent', $3, $4, $5, $6, $7) "
            "ON CONFLICT (id) DO NOTHING",
            child_session_id, child_depth, goal_str, model_override or "",
            now_dt, parent_session_id, inherited_backend,
        )
        logger.info("Worker session created: %s (parent: %s)", child_session_id, parent_session_id)
    except Exception as e:
        logger.error("Failed to create worker session %s: %s", child_session_id, e, exc_info=True)


async def persist_delegation(
    *,
    parent_session_id: str | None,
    subagent_id: str,
    goal: str,
    status: str,
    started_at: float,
    finished_at: float,
    output: str = "",
    error: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    model: str = "",
    depth: int = 0,
    parent_subagent_id: str = "",
    tool_calls_count: int = 0,
) -> None:
    """Persist delegation record to agent_delegations table."""
    db = get_db()
    if not db or not getattr(db, "_pool", None):
        return
    try:
        duration_ms = int((finished_at - started_at) * 1000)
        total_tokens = prompt_tokens + completion_tokens
        await db.execute(
            "INSERT INTO agent_delegations "
            "(session_id, parent_session_id, subagent_id, goal, status, started_at, finished_at, "
            "duration_ms, output, prompt_tokens, completion_tokens, total_tokens, "
            "cost_usd, model, depth, parent_subagent_id, tool_calls_count) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)",
            subagent_id, parent_session_id, subagent_id, goal[:500], status,
            datetime.datetime.fromtimestamp(started_at, tz=datetime.timezone.utc),
            datetime.datetime.fromtimestamp(finished_at, tz=datetime.timezone.utc),
            duration_ms, output[:2000], prompt_tokens, completion_tokens,
            total_tokens, cost_usd, model, depth, parent_subagent_id,
            tool_calls_count,
        )
    except Exception as e:
        logger.debug("Failed to persist delegation %s: %s", subagent_id, e)


def check_budget_pre(session_id: str) -> bool:
    """Pre-flight budget check. Returns True if OK to proceed, False if hard-stop."""
    from harness.tools.budget import BudgetEnforcer, get_budget_policy, get_token_ledger, BudgetAction
    enforcer = BudgetEnforcer(get_budget_policy(), get_token_ledger())
    action = enforcer.check_session(session_id or "global")
    return action != BudgetAction.HARD_STOP


def check_budget_post(subagent_id: str) -> tuple[bool, str]:
    """Post-execution budget check. Returns (ok, truncated_output_suffix)."""
    from harness.tools.budget import BudgetEnforcer, get_budget_policy, get_token_ledger, BudgetAction
    enforcer = BudgetEnforcer(get_budget_policy(), get_token_ledger())
    action = enforcer.check_subagent(subagent_id)
    if action == BudgetAction.HARD_STOP:
        return False, "\n[truncated: budget hard limit reached]"
    return True, ""


# ===========================================================================
# SECTION 4: DB persistence + result collection (was subagent_persistence.py)
# ===========================================================================

from harness.tools.cancellation import get_cancellation_tree  # noqa: E402


async def _persist_delegation(
    parent_session_id: str,
    subagent_id: str,
    goal: str,
    status: str,
    started_at: float,
    finished_at: float,
    output: str = "",
    error: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    model: str = "",
    depth: int = 0,
    parent_subagent_id: str | None = None,
    tool_calls_count: int = 0,
) -> None:
    try:
        db = get_db()
        if db is None or db._pool is None:
            return

        started_dt = datetime.datetime.fromtimestamp(started_at, tz=datetime.timezone.utc)
        finished_dt = datetime.datetime.fromtimestamp(finished_at, tz=datetime.timezone.utc)
        duration_ms = int((finished_at - started_at) * 1000)

        child_session_id = f"subagent-{subagent_id}"
        try:
            inherited_backend = "local"
            if parent_session_id:
                parent_row = await db.fetchrow(
                    "SELECT backend_type FROM sessions WHERE id = $1",
                    parent_session_id,
                )
                if parent_row and parent_row.get("backend_type"):
                    inherited_backend = parent_row["backend_type"]
            await db.execute(
                "INSERT INTO sessions (id, source, status, depth, agent_role, goal, model, started_at, ended_at, parent_session_id, backend_type) "
                "VALUES ($1, 'delegation', $2, $3, 'subagent', $4, $5, $6, $7, $8, $9) "
                "ON CONFLICT (id) DO UPDATE SET status = $2, ended_at = $7",
                child_session_id, status, depth, goal[:500], model,
                started_dt, finished_dt, parent_session_id or None, inherited_backend,
            )
            logger.info("Persisted session update: %s (status=%s, tokens=%d)", child_session_id, status, prompt_tokens + completion_tokens)
        except Exception as e:
            logger.error("Failed to persist session %s: %s", child_session_id, e, exc_info=True)

        try:
            await db.execute(
                "INSERT INTO agent_delegations "
                "(session_id, agent_role, goal, status, tool_calls_count, duration_ms, error, result_summary, started_at, completed_at) "
                "VALUES ($1, 'subagent', $2, $3, $4, $5, $6, $7, $8, $9) "
                "ON CONFLICT DO NOTHING",
                child_session_id, goal[:500], status, tool_calls_count, duration_ms,
                error or None, (output or "")[:500], started_dt, finished_dt,
            )
        except Exception as e:
            logger.error("Failed to persist agent_delegations for %s: %s", child_session_id, e, exc_info=True)

        if prompt_tokens > 0 or completion_tokens > 0:
            try:
                await db.execute(
                    "INSERT INTO token_usage "
                    "(session_id, model, provider, input_tokens, output_tokens, estimated_cost_usd) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    child_session_id, model, "llm",
                    prompt_tokens, completion_tokens, cost_usd,
                )
                logger.info("Persisted token usage for %s: %d input, %d output", child_session_id, prompt_tokens, completion_tokens)
            except Exception as e:
                logger.error("Failed to persist token_usage for %s: %s", child_session_id, e, exc_info=True)

        from harness.api.state import emit_stream_event
        # F25: emit a typed SubagentCompleted (wire name: subagent.completed)
        # so the frontend filter and structured fields align.  Falls back
        # to the legacy string-typed GenericStreamEvent on the rare
        # missing-import path so the wire shape is preserved.
        try:
            from harness.core.events import SubagentCompleted as _SubagentCompleted
            from harness.api.state import _shared_bus
            _ev = _SubagentCompleted(
                subagent_id=subagent_id,
                status=status,
                duration_sec=round((finished_at - started_at), 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round(cost_usd, 6),
                session_id=parent_session_id or "",
            )
            if _shared_bus is not None:
                await _shared_bus.emit(_ev)
            else:
                raise RuntimeError("no shared bus")
        except Exception:
            await emit_stream_event(parent_session_id, "subagent.completed", {
                "subagent_id": subagent_id,
                "child_session_id": child_session_id,
                "goal": goal[:200],
                "status": status,
                "duration_sec": round((finished_at - started_at), 2),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": round(cost_usd, 6),
                "model": model,
                "output_preview": (output or "")[:200],
                "tool_calls_count": tool_calls_count,
            })
    except Exception as e:
        logger.debug("Failed to persist delegation %s: %s", subagent_id, e)


async def collect_results(
    subagent_ids: list[str],
    timeout: float = CHILD_TIMEOUT_SECONDS,
) -> dict[str, SubagentResult | str]:
    results: dict[str, SubagentResult | str] = {}
    pending: list[asyncio.Future] = []

    with _pending_results_lock:
        for sid in subagent_ids:
            future = _pending_results.get(sid)
            if future is None:
                results[sid] = SubagentResult(
                    subagent_id=sid,
                    status="error",
                    error="unknown subagent_id",
                    finished_at=time.time(),
                )
            elif future.done():
                try:
                    val = future.result()
                    results[sid] = val if isinstance(val, SubagentResult) else str(val)
                except Exception as e:
                    results[sid] = SubagentResult(
                        subagent_id=sid,
                        status="error",
                        error=str(e),
                        finished_at=time.time(),
                    )
            else:
                pending.append(future)

    if not pending:
        return results

    done, _ = await asyncio.wait(pending, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
    for future in pending:
        sid_for_future = None
        with _pending_results_lock:
            for sid, f in list(_pending_results.items()):
                if f is future:
                    sid_for_future = sid
                    break
        if sid_for_future is None:
            continue
        if future in done:
            try:
                val = future.result()
                results[sid_for_future] = val if isinstance(val, SubagentResult) else str(val)
            except Exception as e:
                results[sid_for_future] = SubagentResult(
                    subagent_id=sid_for_future,
                    status="error",
                    error=str(e),
                    finished_at=time.time(),
                )
        else:
            results[sid_for_future] = SubagentResult(
                subagent_id=sid_for_future,
                status="error",
                error=f"timeout after {timeout}s",
                finished_at=time.time(),
            )

    return results


async def cancel_subagent(subagent_id: str, reason: str = "cancelled") -> list[str]:
    return await get_cancellation_tree().cancel(subagent_id, reason)


# ===========================================================================
# SECTION 5: Retry + fan-out (was subagent_runner.py)
# ===========================================================================

from harness.tools.budget import (  # noqa: E402
    BudgetAction,
    BudgetEnforcer,
    TokenUsage,
    get_budget_policy,
    get_token_ledger,
)
from harness.tools.circuit_breaker import CircuitBreaker, get_circuit_breakers  # noqa: E402
from harness.tools.error_classifier import classify_error  # noqa: E402


def _classify_exception(exc: BaseException) -> tuple[str, bool]:
    try:
        info = classify_error(str(exc) or type(exc).__name__)
        return info.get("category", "unknown"), bool(info.get("retryable", False))
    except Exception:
        return "unknown", False


async def _call_child_with_enhancements(
    coro_factory: Callable[[], Any],
    *,
    subagent_id: str,
    model: str | None,
    breaker: CircuitBreaker,
) -> _AgentResult:
    last_exc: BaseException | None = None
    for attempt in range(1, DEFAULT_RETRY_MAX_ATTEMPTS + 1):
        if not breaker.allow():
            raise RuntimeError(f"circuit_open:{breaker.name}: provider unavailable")
        try:
            result = await coro_factory()
            breaker.record_success()
            if not isinstance(result, _AgentResult):
                return _AgentResult(output=str(result), model=model or "")
            return result
        except asyncio.CancelledError:
            breaker.record_failure()
            raise
        except Exception as exc:
            category, retryable = _classify_exception(exc)
            last_exc = exc
            breaker.record_failure()
            if not retryable or attempt >= DEFAULT_RETRY_MAX_ATTEMPTS:
                logger.warning(
                    "subagent.retry giving_up subagent=%s attempt=%d category=%s",
                    subagent_id, attempt, category,
                )
                raise
            base = DEFAULT_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            delay = min(base, DEFAULT_RETRY_MAX_DELAY) * (0.5 + random.random())
            logger.info(
                "subagent.retry subagent=%s attempt=%d category=%s delay=%.2fs",
                subagent_id, attempt, category, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def stream_fan_out(
    coros: dict[str, asyncio.Future | asyncio.Task | Any],
    on_complete: Callable[[str, SubagentResult], None] | None = None,
) -> list[SubagentResult]:
    pending: dict[asyncio.Task, str] = {}
    for sub_id, coro in coros.items():
        if isinstance(coro, asyncio.Future):
            task = asyncio.ensure_future(coro)
        elif isinstance(coro, asyncio.Task):
            task = coro
        else:
            task = asyncio.create_task(coro)
        pending[task] = sub_id

    results: list[SubagentResult] = []
    while pending:
        done, _ = await asyncio.wait(
            pending.keys(), return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            sub_id = pending.pop(task)
            try:
                value = task.result()
                if not isinstance(value, SubagentResult):
                    value = SubagentResult(
                        subagent_id=sub_id,
                        status="ok",
                        output=value,
                        finished_at=time.time(),
                    )
                result = value
            except asyncio.CancelledError:
                result = SubagentResult(
                    subagent_id=sub_id,
                    status="cancelled",
                    error="asyncio.CancelledError",
                    finished_at=time.time(),
                )
            except Exception as exc:
                result = SubagentResult(
                    subagent_id=sub_id,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                    finished_at=time.time(),
                )
            if on_complete is not None:
                try:
                    on_complete(sub_id, result)
                except Exception:
                    logger.exception("stream_fan_out.on_complete raised for %s", sub_id)
            results.append(result)
    return results


# ===========================================================================
# SECTION 6: Prompt + toolset helpers (was subagent_prompt.py)
# ===========================================================================

# Wire of safety fix (Claude Code Issue #68110, June 13 2026).
# Was 5 &mdash; the worst case was a general-purpose coordinator at
# depth 5 with 10 children = up to 100,000 possible invocations.
# oh-my-opencode (the closest production reference) uses 3;
# Hermes Agent uses 2. testai was already at Greptile's
# "agent-in-agent" iteration (Attempt 3), where a depth of 2 is
# enough: orchestrator &rarr; coordinator &rarr; worker. Drop to 2.
# Override via the TESTAI_MAX_SPAWN_DEPTH env var for ops.
MAX_SPAWN_DEPTH_CAP = int(os.environ.get("TESTAI_MAX_SPAWN_DEPTH", "2"))
_BATCH_SIZE = 5


def _expand_parent_toolsets(parent_toolsets: set[str]) -> set[str]:
    from harness.tools.toolsets import TOOLSETS
    expanded = set(parent_toolsets)
    for ts_name, ts_def in TOOLSETS.items():
        if ts_name in expanded:
            continue
        ts_tools = set(ts_def.get("tools", []))
        parent_tool_names: set[str] = set()
        for p_ts in parent_toolsets:
            p_def = TOOLSETS.get(p_ts)
            if p_def:
                parent_tool_names.update(p_def.get("tools", []))
        if ts_tools and ts_tools.issubset(parent_tool_names):
            expanded.add(ts_name)
    return expanded


def _is_mcp_toolset_name(name: str) -> bool:
    return bool(name and (str(name).startswith("mcp-") or name == "mcp"))


def _preserve_parent_mcp_toolsets(
    child_toolsets: list[str], parent_toolsets: set[str]
) -> list[str]:
    preserved = list(child_toolsets)
    for ts_name in sorted(parent_toolsets):
        if _is_mcp_toolset_name(ts_name) and ts_name not in preserved:
            preserved.append(ts_name)
    return preserved


def _strip_blocked_tools(toolsets: list[str]) -> list[str]:
    blocked_ts = {"delegate", "clarify", "memory"}
    return [t for t in toolsets if t not in blocked_ts]


def _build_child_system_prompt(
    goal: str,
    context: str | None = None,
    *,
    role: str = "leaf",
    max_spawn_depth: int = MAX_SPAWN_DEPTH_CAP,
    child_depth: int = 1,
    agent_name: str | None = None,
) -> str:
    """Build subagent prompt from file-based agent definitions.

    When ``agent_name`` is provided, loads the agent definition from
    ``harness/agents/agent_name.md`` (or user/project override) via
    ``agent_discovery.get_subagent_prompt``.

    Falls back to role-based lookup of ``subagent-worker`` / ``subagent-delegator``
    from ``.testai/prompts/agents/``.
    """
    if agent_name:
        from harness.agent_discovery import get_subagent_prompt
        return get_subagent_prompt(
            agent_name=agent_name,
            goal=goal,
            context=context or "",
            allowed_tools=None,
        )

    from harness.prompt_builder import load_agent_prompt, render_prompt

    fallback_name = "subagent-delegator" if role == "orchestrator" else "subagent-worker"
    body = load_agent_prompt(fallback_name)
    if not body:
        return f"You are a worker fork. Execute ONE directive, then stop.\n\nDIRECTIVE: {goal}"

    vars_dict = {
        "goal": goal,
        "context": f"CONTEXT:\n{context}" if context and context.strip() else "",
        "role": role,
        "depth": str(child_depth),
        "max_depth": str(max_spawn_depth),
    }
    return render_prompt(body, vars_dict)


def _build_child_progress_callback(
    task_index: int,
    goal: str,
    parent_cb: Callable | None,
    task_count: int = 1,
    **kwargs: Any,
) -> Callable | None:
    return None


# ===========================================================================
# SECTION 7: Public class API
# ===========================================================================


class Subagent:
    """Unified subagent API.

    Recommended public entry point for new code. Wraps the module-level
    helpers in this file behind a single class.

    Lifecycle modes (mirrors the delegate_task tool's three modes):

    - :meth:`spawn` &mdash; single subagent, blocks until done.
    - :meth:`cancel` &mdash; cancel a running subagent.
    - :meth:`collect` &mdash; wait for background subagents and return results.

    State is process-global (the module-level state in this file).
    The class is a thin facade over those helpers; new code can use
    the class API without touching the underlying state management.
    """

    def __init__(
        self,
        *,
        agent_factory: Callable | None = None,
        session_id: str = "",
        max_children: int = DEFAULT_MAX_CONCURRENT_CHILDREN,
        max_spawn_depth: int = MAX_SPAWN_DEPTH_CAP,
    ) -> None:
        self._agent_factory = agent_factory
        self._session_id = session_id
        self._max_children = max_children
        self._max_spawn_depth = max_spawn_depth

    def with_session(self, session_id: str) -> "Subagent":
        """Return a new Subagent bound to a different session id.

        Pattern: the delegate_task tool creates one Subagent per
        parent session; sub-calls share state but have different
        session_id for persistence. Mirrors the
        ``DelegateTaskTool(self._session_id=...)`` shape.
        """
        clone = Subagent(
            agent_factory=self._agent_factory,
            session_id=session_id,
            max_children=self._max_children,
            max_spawn_depth=self._max_spawn_depth,
        )
        return clone

    def agent_factory(self, factory: Callable) -> "Subagent":
        """Bind an agent factory (used to spawn the actual child agent).

        Mirrors ``DelegateTaskTool._get_agent_factory``; the factory
        is the hook that knows how to construct a child ``Agent``
        from harness ``AgentDeps`` + a goal.
        """
        self._agent_factory = factory
        return self

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def max_children(self) -> int:
        return self._max_children

    @property
    def max_spawn_depth(self) -> int:
        return self._max_spawn_depth

    # ------------------------------------------------------------------
    # Lifecycle &mdash; thin facade over the module-level helpers.
    # ------------------------------------------------------------------

    def is_paused(self) -> bool:
        """True when subagent spawning is globally paused."""
        return is_spawn_paused()

    def set_paused(self, paused: bool) -> bool:
        """Pause/resume subagent spawning globally. Returns the new state."""
        return set_spawn_paused(paused)

    def list_active(self) -> list[dict[str, Any]]:
        """Snapshot of currently-running subagents (read-only)."""
        return active_subagents()

    def pending_subagent_ids(self) -> list[str]:
        """Public read-only list of background-spawn subagent ids awaiting collection.

        Replaces the deferred ``from harness.tools.subagent import
        _pending_results`` import that callers used to do; the
        leading-underscore name was a leak of internal state.
        """
        return list(_pending_results.keys())

    def active_subagent_ids(self) -> list[str]:
        """Public read-only list of currently-running subagent ids.

        Same leak fix as :meth:`pending_subagent_ids`.
        """
        return list(_active_subagents.keys())

    async def cancel(
        self, subagent_id: str, reason: str = "cancelled",
    ) -> list[str]:
        """Cancel a running subagent and its children.

        Returns the list of cancellation-tree subagent ids that were
        cancelled.
        """
        return await cancel_subagent(subagent_id, reason)

    async def collect(
        self,
        subagent_ids: list[str],
        timeout: float = CHILD_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Wait for background subagents and return their results."""
        return await collect_results(subagent_ids, timeout=timeout)

    # ------------------------------------------------------------------
    # spawn_many() &mdash; fan-out, N parallel.
    # ------------------------------------------------------------------

    async def spawn_many(
        self,
        goals: list[str],
        *,
        role: str = "leaf",
        context: str = "",
        toolsets: list[str] | None = None,
        model_override: str | None = None,
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
        parent_session_id: str | None = None,
        on_complete: Callable[[str, "SubagentResult"], None] | None = None,
    ) -> list["SubagentResult"]:
        """Fan-out: spawn N subagents in parallel, return all results.

        Each goal is wrapped in a :meth:`spawn` coroutine and the
        coroutines are gathered via :func:`stream_fan_out`. The
        ``on_complete`` callback (if provided) is invoked per
        result as soon as it lands, in the order the coroutines
        complete (not the order they were submitted). The
        callback runs in the asyncio event loop, so it should
        not block.

        Failure modes:
        - If any single subagent fails (status="error"), the
          other subagents still complete; the failed one is in
          the returned list with ``status="error"`` and
          ``error="..."``. The caller decides whether to retry
          or fail the parent run.
        - If a subagent hits the depth cap or the rate
          circuit breaker, it returns immediately with
          ``status="error"``; the other subagents are
          unaffected.

        Returns the list of :class:`SubagentResult` in the
        order the coroutines completed (not the input order).
        Use :attr:`SubagentResult.subagent_id` to correlate
        with the goal if needed.
        """
        # Build the per-goal coroutine map. Each goal gets a
        # pre-allocated uuid so the result is correlatable even
        # if the goal is empty/short.
        coros: dict[str, Any] = {}
        for goal in goals:
            sid = f"sa-{uuid.uuid4().hex[:8]}"
            coros[sid] = self.spawn(
                goal,
                role=role,
                context=context,
                toolsets=toolsets,
                model_override=model_override,
                agent_name=agent_name,
                max_tool_rounds=max_tool_rounds,
                parent_session_id=parent_session_id,
            )
        return await stream_fan_out(coros, on_complete=on_complete)

    # ------------------------------------------------------------------
    # spawn() &mdash; the new public method.
    # ------------------------------------------------------------------

    async def spawn(
        self,
        goal: str,
        *,
        role: str = "leaf",
        context: str = "",
        toolsets: list[str] | None = None,
        model_override: str | None = None,
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
        parent_session_id: str | None = None,
        factory_wrapper: Callable[[Callable], Callable] | None = None,
        timeout: float | None = None,
        filesystem: Any | None = None,
        repo_path: str = "",
        parent_branch: str = "",
    ) -> SubagentResult:
        """Spawn a single subagent and wait for the result.

        Returns a :class:`SubagentResult` with the new F6 (evidence)
        and F12 (detector_name) fields populated. This is the new
        recommended single-call API for spawning a subagent; the
        older ``DelegateTaskTool._run_single_enhanced`` does the
        same thing with more knobs (run_in_background, mcp_servers,
        etc.) and is still used by the tool registry.
        """
        # Resolve agent factory. Same fallback chain as
        # ``DelegateTaskTool._get_agent_factory``: explicit
        # constructor, harness.api.state, then app.state.
        factory = self._agent_factory
        if factory is None:
            try:
                from harness.api.state import get_agent_factory
                factory = get_agent_factory()
            except Exception:
                factory = None
        if factory is None:
            try:
                from api.main import app
                factory = getattr(app.state, "agent_factory", None)
            except Exception:
                factory = None
        if factory is None:
            return SubagentResult(
                subagent_id=f"sa-no-factory-{uuid.uuid4().hex[:8]}",
                status="error",
                error="agent_factory_not_configured",
                started_at=time.time(),
                finished_at=time.time(),
                duration_sec=0.0,
                detector_name="",
            )

        started_at = time.time()
        if is_spawn_paused():
            return SubagentResult(
                subagent_id=f"sa-paused-{uuid.uuid4().hex[:8]}",
                status="error",
                error="spawn_paused",
                started_at=started_at,
                finished_at=time.time(),
                duration_sec=0.0,
            )

        # Wire of safety fix: per-run subagent budget check.
        # Claude Code #68619's "out-of-control recursive subagents
        # also trigger rate limits" is the failure mode this
        # prevents. The BudgetTracker is set per Run by the
        # orchestrator; if the parent's remaining budget is too
        # low, refuse to spawn. The check is best-effort (failure
        # to read the tracker is treated as "budget OK") so a
        # broken budget pipeline never blocks a real run.
        try:
            from harness.budget_tracker import get_current_tracker
            tracker = get_current_tracker()
        except Exception:
            tracker = None
        if tracker is not None:
            try:
                snap = tracker.snapshot()
                if getattr(snap, "hard_cap_usd", 0) > 0 and getattr(snap, "spent_usd", 0) > 0:
                    ratio = snap.spent_usd / snap.hard_cap_usd
                    if ratio >= 0.95:
                        return SubagentResult(
                            subagent_id=f"sa-budget-{uuid.uuid4().hex[:8]}",
                            status="error",
                            error=f"parent_budget_95pct_consumed",
                            started_at=started_at,
                            finished_at=time.time(),
                            duration_sec=0.0,
                        )
            except Exception as exc:
                logger.debug("budget pre-check failed: %s", exc)

        # Wire of safety fix: spawn rate detector.
        # If more than SPAWN_RATE_LIMIT subagents spawn in the
        # SPAWN_RATE_WINDOW, auto-pause for SPAWN_RATE_COOLDOWN
        # seconds. Catches the Claude Code #68110 pattern where
        # 48+ agents spawn in seconds. Defaults: 10 in 30s,
        # 60s cooldown. Override via env vars.
        rate_paused, rate_error = check_spawn_rate()
        if rate_paused:
            return SubagentResult(
                subagent_id=f"sa-rate-{uuid.uuid4().hex[:8]}",
                status="error",
                error=rate_error or "spawn_rate_limit",
                started_at=started_at,
                finished_at=time.time(),
                duration_sec=0.0,
            )

        # Depth check.
        try:
            from harness.context import manager as scope_manager
            current_depth = 0
            try:
                scope = scope_manager.get_current_scope() if hasattr(scope_manager, "get_current_scope") else None
                if scope is not None:
                    current_depth = getattr(scope, "depth", 0)
            except Exception:
                current_depth = 0
            child_depth = current_depth + 1
            if child_depth > self._max_spawn_depth:
                return SubagentResult(
                    subagent_id=f"sa-depth-{uuid.uuid4().hex[:8]}",
                    status="error",
                    error=f"max_spawn_depth_exceeded_at_{child_depth}",
                    started_at=started_at,
                    finished_at=time.time(),
                    duration_sec=0.0,
                )
        except Exception:
            child_depth = 1

        subagent_id = f"sa-{uuid.uuid4().hex[:8]}"
        child_session_id = f"subagent-{subagent_id}"

        # C6: set up per-subagent filesystem isolation.
        _fs_worktree_path: str = ""
        if filesystem is not None:
            try:
                from pathlib import Path
                _fs_worktree_path = str(
                    await filesystem.setup(
                        subagent_id, Path(repo_path) if repo_path else Path("/workspace/repo"),
                        parent_branch or "HEAD",
                    )
                )
            except Exception as exc:
                logger.debug("Subagent.spawn: filesystem setup failed: %s", exc)

        # Create the child session row.
        try:
            await create_child_session(
                child_session_id=child_session_id,
                child_depth=child_depth,
                goal=goal,
                model_override=model_override,
                parent_session_id=parent_session_id or self._session_id or None,
                started_at=started_at,
            )
        except Exception as exc:
            logger.debug("Subagent.spawn: create_child_session failed: %s", exc)

        # Build the child system prompt and toolsets.
        try:
            system_prompt = await _build_child_system_prompt(
                goal=goal,
                context=context,
                role=role,
                max_spawn_depth=self._max_spawn_depth,
                child_depth=child_depth,
                agent_name=agent_name,
            )
        except Exception as exc:
            logger.debug("Subagent.spawn: build_child_system_prompt failed: %s", exc)
            system_prompt = f"You are a worker fork. Execute ONE directive, then stop.\n\nDIRECTIVE: {goal}"

        # Spawn the child via the agent factory.
        try:
            breaker = get_circuit_breakers().for_provider(model_override or "default", role=role)
            # If the caller passed a factory_wrapper, it's a callable
            # that takes the agent factory and returns a wrapped
            # factory. The wrapper is the seam for tool-specific
            # customization (DelegationContext, volume key, shield
            # mode, etc.) without making Subagent know about them.
            effective_factory = factory_wrapper(factory) if factory_wrapper else factory
            child = effective_factory(
                system_prompt=system_prompt,
                toolsets=toolsets or ["read", "intelligence"],
                session_id=child_session_id,
                max_tool_rounds=max_tool_rounds or 50,
                model=model_override,
            )

            # C6: if we have a filesystem worktree, set the child's
            # working directory so all file operations stay inside it.
            if _fs_worktree_path and hasattr(child, "sandbox") and child.sandbox is not None:
                try:
                    # The sandbox has a working directory concept.
                    # Set it to the worktree path so bash/write_file
                    # operate inside the isolated worktree.
                    sb = child.sandbox
                    if hasattr(sb, "_sandbox_root"):
                        sb._sandbox_root = _fs_worktree_path
                    if hasattr(sb, "cwd"):
                        await sb.run(f"cd {_fs_worktree_path}", timeout=10)
                except Exception as exc:
                    logger.debug("Subagent.spawn: set workdir failed: %s", exc)

            async def _run_child() -> _AgentResult:
                async with _safe_scope():
                    raw = await child.run(goal, model=model_override or None)
                model = getattr(child, "_last_model", "") or model_override or ""
                usage = getattr(child, "_last_usage", {}) or {}
                tool_count = 0
                try:
                    for msg in getattr(child, "_messages", []) or []:
                        if getattr(msg, "tool_calls", None):
                            tool_count += len(msg.tool_calls)
                except Exception:
                    pass
                if isinstance(raw, _AgentResult):
                    raw.model = raw.model or model
                    raw.prompt_tokens = raw.prompt_tokens or usage.get("prompt_tokens", 0)
                    raw.completion_tokens = raw.completion_tokens or usage.get("completion_tokens", 0)
                    raw.tool_calls_count = tool_count
                    return raw
                return _AgentResult(
                    output=str(raw),
                    model=model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    tool_calls_count=tool_count,
                )

            effective_timeout = timeout if timeout is not None else CHILD_TIMEOUT_SECONDS
            result_inner = await asyncio.wait_for(
                _call_child_with_enhancements(
                    _run_child,
                    subagent_id=subagent_id,
                    model=model_override,
                    breaker=breaker,
                ),
                timeout=effective_timeout,
            )
            # Wire of safety fix: record this successful spawn
            # so the rate window sees it. A successful spawn still
            # counts toward the budget &mdash; the runaway in #68110
            # was 48+ successful spawns.
            try:
                record_spawn()
            except Exception:
                pass
            # C6: merge subagent's worktree back to parent.
            if filesystem is not None and _fs_worktree_path:
                try:
                    from pathlib import Path
                    await filesystem.merge_back(
                        subagent_id, Path(repo_path) if repo_path else Path("/workspace/repo"),
                        session_id=child_session_id,
                    )
                except Exception as exc:
                    logger.debug("Subagent.spawn: filesystem merge_back failed: %s", exc)
            try:
                await _update_child_session_status(child_session_id, "completed")
            except Exception:
                pass
        except Exception as exc:
            finished_at = time.time()
            # C6: merge what we can, even on failure.
            if filesystem is not None and _fs_worktree_path:
                try:
                    from pathlib import Path
                    await filesystem.merge_back(
                        subagent_id, Path(repo_path) if repo_path else Path("/workspace/repo"),
                        session_id=child_session_id,
                    )
                except Exception:
                    pass
            try:
                await _update_child_session_status(child_session_id, "failed")
            except Exception:
                pass
            return SubagentResult(
                subagent_id=subagent_id,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                started_at=started_at,
                finished_at=finished_at,
                duration_sec=finished_at - started_at,
            )
        finally:
            # C6: always cleanup the worktree.
            if filesystem is not None and _fs_worktree_path:
                try:
                    from pathlib import Path
                    await filesystem.cleanup(
                        subagent_id, Path(repo_path) if repo_path else Path("/workspace/repo"),
                    )
                except Exception:
                    pass

        finished_at = time.time()
        return SubagentResult(
            subagent_id=subagent_id,
            status="ok",
            output=result_inner.output or "",
            started_at=started_at,
            finished_at=finished_at,
            duration_sec=finished_at - started_at,
            prompt_tokens=result_inner.prompt_tokens,
            completion_tokens=result_inner.completion_tokens,
            total_tokens=result_inner.prompt_tokens + result_inner.completion_tokens,
            cost_usd=result_inner.cost_usd,
            model=result_inner.model or model_override or "",
        )


# ===========================================================================
# SECTION 8: Scope helper
# ===========================================================================


from contextlib import asynccontextmanager

@asynccontextmanager
async def _safe_scope():
    """Context manager stub for Subagent.spawn().

    Wraps the real ``harness.context.manager.scope()`` so the
    ``async with`` always works whether the context module is
    importable or not.
    """
    try:
        from harness.context import manager as scope_manager
        async with scope_manager.scope() as s:
            yield s
            return
    except Exception:
        yield None


# ===========================================================================
# Public surface
# ===========================================================================

__all__ = [
    # Data types
    "SubagentResult",
    "_AgentResult",
    "EvidenceClaim",
    # Constants
    "DEFAULT_MAX_CONCURRENT_CHILDREN",
    "CHILD_TIMEOUT_SECONDS",
    "CANCEL_GRACE_PERIOD_SECONDS",
    "DEFAULT_RETRY_MAX_ATTEMPTS",
    "DEFAULT_RETRY_BASE_DELAY",
    "DEFAULT_RETRY_MAX_DELAY",
    "DELEGATE_BLOCKED_TOOLS",
    "MAX_SPAWN_DEPTH_CAP",
    # Functions (backward compat for callers using old import paths)
    "set_spawn_paused",
    "is_spawn_paused",
    "active_subagents",
    "interrupt_subagent",
    "drain_pending_results",
    "check_spawn_rate",
    "record_spawn",
    "spawn_rate_status",
    "_call_child_with_enhancements",
    "stream_fan_out",
    "_classify_exception",
    "_persist_delegation",
    "cancel_subagent",
    "collect_results",
    "create_child_session",
    "persist_delegation",
    "check_budget_pre",
    "check_budget_post",
    "_build_child_system_prompt",
    "_build_child_progress_callback",
    "_expand_parent_toolsets",
    "_preserve_parent_mcp_toolsets",
    "_strip_blocked_tools",
    "_is_mcp_toolset_name",
    # Private state (delegate_task.py internals)
    "_active_subagents",
    "_active_subagents_lock",
    "_pending_results",
    "_pending_results_lock",
    # Public class
    "Subagent",
]
