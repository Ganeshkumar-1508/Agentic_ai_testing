"""Chat service — business logic for the chat surface (Q3, Q5, Q6).

Three responsibilities, in three layers:

  1. **Auto-creation** — :func:`auto_create_thread_for_run` is
     called by the ``submit_job`` path (chat tool + ``/api/jobs``
     router) right after the :class:`JobSpec` is persisted. Creates
     a :class:`ChatThread` linked to the new ``run_id``, seeds the
     user's prompt as the first ``user`` message.

  2. **Persistence** — :func:`post_user_message`, :func:`post_assistant_message`,
     :func:`post_system_message` wrap :mod:`harness.chat.threads`
     with role-specific defaults. The chat LLM's output stream calls
     these before/after the LLM call so the thread is the durable
     record of the conversation.

  3. **Event hooks** — :class:`ChatEventSink` is a
     :class:`harness.events.EventSink` that subscribes to the
     orchestrator's high-signal events (``board.completed``,
     ``board.failed``, ``board.task.completed``, ``board.task.failed``,
     ``ErrorEvent``, ``BudgetThrottled``) and posts a short
     user-readable :class:`ChatMessage` (role ``system``) into the
     auto-created thread. Per-tool-call events are intentionally
     **not** mirrored — they'd flood the thread; the user sees
     those on the live activity feed instead.

The service layer is the only place that knows about both the chat
storage (:mod:`harness.chat.threads`) and the orchestrator's
event bus. Routes and tools depend on this module, not the other
way around.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from harness.chat.threads import (
    ChatMessage,
    ChatThread,
    DEFAULT_THREAD_TITLE,
    THREAD_SOURCES,
    append_message,
    create_thread,
    get_thread,
    get_thread_by_run_id,
    get_thread_by_session_id,
    new_message_id,
    new_thread_id,
)

if TYPE_CHECKING:
    from harness.events import EventBus
    from harness.memory.database import Database
    from harness.core.events import StreamEvent


logger = logging.getLogger(__name__)


# Maximum number of messages the chat LLM sees when the user sends
# a new message. The full thread history stays in Postgres; the LLM
# only needs the most recent context to stay within its context window.
# 50 messages × ~500 tokens each = ~25k tokens, well under the
# 200k context for deepseek-v4-flash.
DEFAULT_HISTORY_LIMIT = 50

# Maximum length of an event-derived system message. The event
# payload is truncated so a runaway payload doesn't blow the
# thread's message_count.
MAX_EVENT_MESSAGE_CHARS = 600


# ---------------------------------------------------------------------------
# Event filter — the high-signal events the chat cares about
# ---------------------------------------------------------------------------


# The set of GenericStreamEvent ``event_type`` strings we mirror into
# the chat thread. Per-tool-call events (tool.execution.*), per-round
# events (round.*), per-LLM-call events (llmcall.*) and per-token
# events (token.generated, reasoning.generated) are intentionally
# excluded — the user sees those on the live activity feed.
HIGH_SIGNAL_EVENT_TYPES: frozenset[str] = frozenset({
    # Lifecycle
    "agent.started",
    "agent.completed",
    # Kanban (board-level)
    "board.completed",
    "board.failed",
    # Kanban (task-level)
    "board.task.created",
    "board.task.completed",
    "board.task.failed",
    "board.task.blocked",
    # Subagent (high-level)
    "subagent.spawned",
    "subagent.completed",
    "subagent.heartbeat",
    # Errors / cost
    "error",
    "budget.throttled",
    # Approvals
    "approval.required",
})


# ---------------------------------------------------------------------------
# Auto-creation
# ---------------------------------------------------------------------------


async def auto_create_thread_for_run(
    *,
    run_id: str,
    session_id: str,
    prompt: str,
    repo_url: str = "",
    title: str | None = None,
    source: str = "run",
    db: "Database | None" = None,
) -> ChatThread:
    """Create a thread for a new run, seeded with the user's prompt.

    Idempotent: if a thread already exists for this ``run_id`` (or
    this ``session_id``), the existing thread is returned and the
    prompt is **not** appended a second time. The caller does not
    need to dedupe.

    Args:
      run_id: the ``job_specs.run_id`` (used as the 1:1 link).
      session_id: the orchestrator's session id (used for event
        routing in :class:`ChatEventSink`).
      prompt: the user's first message — seeded as ``role='user'``.
      repo_url: included in the auto-generated title if ``title``
        is not given.
      title: optional explicit title. ``None`` (the default) lets
        the seed-prompt auto-title fire.
      source: one of :data:`THREAD_SOURCES`. Defaults to ``"run"``.
      db: optional explicit ``Database``.

    Returns the persisted :class:`ChatThread`.
    """
    if source not in THREAD_SOURCES:
        raise ValueError(f"source must be one of {THREAD_SOURCES!r}, got {source!r}")

    # 1. Look up by run_id (primary, 1:1).
    existing = await get_thread_by_run_id(run_id, db=db)
    if existing is not None:
        return existing

    # 2. Look up by session_id (fallback: the chat surface reuses
    # threads per session even across runs; the new run is a
    # follow-up turn in the same conversation).
    if session_id:
        existing = await get_thread_by_session_id(session_id, db=db)
        if existing is not None:
            return existing

    # 3. Otherwise: create a fresh thread.
    seed_title = title or _build_seed_title(prompt, repo_url)
    thread = await create_thread(
        title=seed_title,
        run_id=run_id,
        session_id=session_id,
        source=source,
        db=db,
    )

    # 4. Seed the user's prompt as the first user message. We bypass
    # :func:`threads.append_message` here so we can set the message
    # id explicitly (so the seeded message is deterministic for
    # tests) and so the seed is recorded even if the auto-title
    # logic decides not to overwrite.
    if prompt and prompt.strip():
        await append_message(
            thread_id=thread.id,
            role="user",
            content=prompt.strip(),
            message_id=new_message_id(),
            db=db,
        )
        # Re-fetch the thread so message_count, last_message_at, and
        # updated_at reflect the seeded message.
        refetched = await get_thread(thread.id, db=db)
        if refetched is not None:
            return refetched
    return thread


def _build_seed_title(prompt: str, repo_url: str = "") -> str:
    """Build the initial title for a thread from the seed prompt.

    Used only when the user didn't provide an explicit title and
    the prompt is short enough to be the title itself; otherwise
    the auto-title-after-first-message logic in
    :mod:`harness.chat.threads` will overwrite the title once the
    LLM emits a real reply.
    """
    text = (prompt or "").strip().replace("\n", " ")
    if not text:
        return DEFAULT_THREAD_TITLE
    if len(text) <= 80:
        return text
    return text[:77].rsplit(" ", 1)[0] + "..."


# ---------------------------------------------------------------------------
# Persistence — role-specific message writers
# ---------------------------------------------------------------------------


async def post_user_message(
    thread_id: str,
    content: str,
    *,
    db: "Database | None" = None,
) -> ChatMessage:
    """Append a user message. The auto-title-after-first-message
    logic in :mod:`harness.chat.threads` fires here.
    """
    return await append_message(
        thread_id=thread_id, role="user", content=content, db=db,
    )


async def post_assistant_message(
    thread_id: str,
    *,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
    is_error: bool = False,
    db: "Database | None" = None,
) -> ChatMessage:
    """Append an assistant message.

    The chat LLM emits content + (optionally) tool_calls + (optionally)
    a finish_reason on every turn. Token + cost are filled in by the
    LLM client; the SSE handler passes them through.
    """
    return await append_message(
        thread_id=thread_id,
        role="assistant",
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        is_error=is_error,
        db=db,
    )


async def post_tool_result(
    thread_id: str,
    *,
    tool_call_id: str,
    tool_name: str,
    content: str | None = None,
    is_error: bool = False,
    db: "Database | None" = None,
) -> ChatMessage:
    """Append a ``role='tool'`` message. Joins to the assistant's
    ``tool_calls[].id`` via ``tool_call_id``.
    """
    return await append_message(
        thread_id=thread_id,
        role="tool",
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        content=content,
        is_error=is_error,
        db=db,
    )


async def post_system_message(
    thread_id: str,
    content: str,
    *,
    tool_name: str | None = None,
    db: "Database | None" = None,
) -> ChatMessage:
    """Append a ``role='system'`` message.

    Used for:
      * chat-side status (e.g. *"thinking…"*).
      * mirrored orchestrator events (e.g. *"Task 5/15 done: write tests
        for cache_version"*).
      * operator-injected context (e.g. *"Triage Officer persona preamble"*).
    """
    return await append_message(
        thread_id=thread_id, role="system", content=content, tool_name=tool_name, db=db,
    )


# ---------------------------------------------------------------------------
# Event hooks — ChatEventSink
# ---------------------------------------------------------------------------


class ChatEventSink:
    """An :class:`harness.events.EventSink` that mirrors high-signal
    orchestrator events into the auto-created chat thread.

    Filter rules (in order):
      1. If the event has no ``session_id``, skip (no thread to look up).
      2. If the event's wire name is not in
         :data:`HIGH_SIGNAL_EVENT_TYPES`, skip (per-tool-call events
         are noise).
      3. Look up the thread by ``session_id``. If no thread, skip
         (the event came from a non-chat run, e.g. a cron job).
      4. Format a short user-readable message via :func:`_format_event`.
      5. Truncate to :data:`MAX_EVENT_MESSAGE_CHARS` and post as
         a :class:`ChatMessage` (role ``system``).

    The sink is **best-effort**: any error in the DB write is
    logged and swallowed so a misbehaving chat thread can never
    stall the orchestrator's main loop.
    """
    name = "chat_event_sink"

    def __init__(self, db: "Database | None" = None) -> None:
        # If ``db`` is None, the sink reads it from the global on
        # each event (the standard pattern in this codebase).
        self._explicit_db = db

    def emit(self, event: "StreamEvent") -> Any:
        """Async dispatch (the bus awaits the returned coroutine)."""
        return self._emit(event)

    async def _emit(self, event: "StreamEvent") -> None:
        # 1. Pull the session id.
        sid = getattr(event, "session_id", None)
        if not sid:
            # GenericStreamEvent may have a different attribute.
            if hasattr(event, "data") and isinstance(getattr(event, "data"), dict):
                sid = getattr(event, "data", {}).get("session_id")
        if not sid:
            return

        # 2. Resolve the wire name. GenericStreamEvent carries its
        # own ``event_type``; typed events use :func:`wire_name`.
        from harness.events import wire_name
        wname = wire_name(event)
        if wname not in HIGH_SIGNAL_EVENT_TYPES:
            return

        # 3. Look up the thread.
        from harness.chat.threads import get_thread_by_session_id
        thread = await get_thread_by_session_id(sid, db=self._explicit_db)
        if thread is None:
            return

        # 4 + 5. Format and post.
        try:
            content = _format_event(event, wname)
            if not content:
                return
            if len(content) > MAX_EVENT_MESSAGE_CHARS:
                content = content[: MAX_EVENT_MESSAGE_CHARS - 1].rsplit(" ", 1)[0] + "..."
            await post_system_message(
                thread.id, content, tool_name=wname, db=self._explicit_db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chat_event_sink: post failed thread=%s event=%s err=%s",
                thread.id, wname, exc,
            )


def _format_event(event: "StreamEvent", wire_name_str: str) -> str:
    """Format a high-signal event into a short, user-readable line.

    Returns ``""`` if the event has no narrative content (e.g. a
    subagent.heartbeat that carries no payload).
    """
    # GenericStreamEvent carries the payload in ``data``; typed
    # events have the fields on the dataclass itself.
    payload: dict[str, Any] = {}
    if hasattr(event, "data") and isinstance(getattr(event, "data"), dict):
        payload = dict(getattr(event, "data") or {})
    # Pull the canonical fields off the typed event too (covers the
    # case where a typed event has both a ``data`` dict and a
    # dedicated field).
    for f in ("task_id", "summary", "status", "error", "agent_role",
              "agent_id", "subagent_id", "goal", "result_summary",
              "category", "message", "cancelled", "rounds",
              "depth", "current_tool", "elapsed_seconds"):
        if hasattr(event, f):
            v = getattr(event, f)
            if v is not None and f not in payload:
                payload[f] = v

    fmt = _FORMATTERS.get(wire_name_str)
    if fmt is None:
        # Unknown event type — fall back to a single line summary.
        if payload:
            return f"[{wire_name_str}] " + ", ".join(
                f"{k}={v}" for k, v in payload.items()
            )[:MAX_EVENT_MESSAGE_CHARS - len(wire_name_str) - 4]
        return ""
    try:
        return fmt(payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("chat_event_sink: format failed event=%s err=%s", wire_name_str, exc)
        return ""


def _f_agent_started(p: dict[str, Any]) -> str:
    mode = p.get("mode", "agent")
    return f"Agent started in {mode} mode."


def _f_agent_completed(p: dict[str, Any]) -> str:
    rounds = p.get("rounds", 0)
    cancelled = p.get("cancelled", False)
    if cancelled:
        return f"Agent stopped after {rounds} round(s) (cancelled)."
    return f"Agent completed after {rounds} round(s)."


def _f_board_completed(p: dict[str, Any]) -> str:
    done = p.get("done_count")
    total = p.get("total_count")
    if done is not None and total is not None:
        return f"Board completed: {done}/{total} tasks done."
    return "Board completed."


def _f_board_failed(p: dict[str, Any]) -> str:
    return f"Board failed: {p.get('error', 'unknown error')}"


def _f_board_task_created(p: dict[str, Any]) -> str:
    role = p.get("agent_role", "agent")
    return f"New task queued ({role})."


def _f_board_task_completed(p: dict[str, Any]) -> str:
    summary = p.get("summary") or p.get("result_summary") or "done"
    return f"Task done: {summary}"[:MAX_EVENT_MESSAGE_CHARS]


def _f_board_task_failed(p: dict[str, Any]) -> str:
    err = p.get("error", "unknown")
    return f"Task failed: {err}"[:MAX_EVENT_MESSAGE_CHARS]


def _f_board_task_blocked(p: dict[str, Any]) -> str:
    return f"Task blocked: {p.get('error', 'failure limit reached')}"[:MAX_EVENT_MESSAGE_CHARS]


def _f_subagent_spawned(p: dict[str, Any]) -> str:
    return f"Spawned subagent {p.get('subagent_id', '?')[:8]} ({p.get('agent_role', 'leaf')})."


def _f_subagent_completed(p: dict[str, Any]) -> str:
    sid = (p.get("subagent_id") or "?")[:8]
    if p.get("cancelled"):
        return f"Subagent {sid} cancelled."
    return f"Subagent {sid} completed."


def _f_subagent_heartbeat(p: dict[str, Any]) -> str:
    # Heartbeats are noisy — emit a very short "still working" line
    # at most once per ~30s by gating on the current_tool. The
    # caller is expected to throttle; we just format.
    tool = p.get("current_tool")
    if not tool:
        return ""
    return f"…still working ({tool})."


def _f_error(p: dict[str, Any]) -> str:
    cat = p.get("category", "error")
    msg = p.get("message", "error")
    return f"[{cat}] {msg}"[:MAX_EVENT_MESSAGE_CHARS]


def _f_budget_throttled(p: dict[str, Any]) -> str:
    return f"Budget throttle: {p.get('message', 'pausing…')}"[:MAX_EVENT_MESSAGE_CHARS]


def _f_approval_required(p: dict[str, Any]) -> str:
    return f"Approval needed: {p.get('message', 'a tool is waiting for review')}"[:MAX_EVENT_MESSAGE_CHARS]


_FORMATTERS: dict[str, Any] = {
    "agent.started": _f_agent_started,
    "agent.completed": _f_agent_completed,
    "board.completed": _f_board_completed,
    "board.failed": _f_board_failed,
    "board.task.created": _f_board_task_created,
    "board.task.completed": _f_board_task_completed,
    "board.task.failed": _f_board_task_failed,
    "board.task.blocked": _f_board_task_blocked,
    "subagent.spawned": _f_subagent_spawned,
    "subagent.completed": _f_subagent_completed,
    "subagent.heartbeat": _f_subagent_heartbeat,
    "error": _f_error,
    "budget.throttled": _f_budget_throttled,
    "approval.required": _f_approval_required,
}


# ---------------------------------------------------------------------------
# Bus wiring
# ---------------------------------------------------------------------------


def register_chat_event_sink(
    bus: "EventBus",
    *,
    db: "Database | None" = None,
) -> ChatEventSink:
    """Attach a :class:`ChatEventSink` to the global event bus.

    Idempotent: re-calling this with a different ``db`` swaps the
    sink's DB. Safe to call from ``api/main.py:lifespan``.

    Returns the sink instance (so callers can ``bus.remove_sink`` it
    in tests).
    """
    # Remove any pre-existing chat sink (idempotency + tests).
    for existing in list(bus.sinks()):
        if isinstance(existing, ChatEventSink):
            bus.remove_sink(existing)
    sink = ChatEventSink(db=db)
    bus.add_sink(sink)
    return sink


# ---------------------------------------------------------------------------
# Build LLM context
# ---------------------------------------------------------------------------


async def build_chat_context(
    thread_id: str,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
    db: "Database | None" = None,
) -> list[dict[str, Any]]:
    """Return the thread's recent messages formatted for the chat LLM.

    Output shape (OpenAI / Anthropic compatible):
        [
            {"role": "user",      "content": "..."},
            {"role": "assistant", "content": "...", "tool_calls": [...]},
            {"role": "tool",      "tool_call_id": "...", "content": "..."},
            {"role": "system",    "content": "..."},
            ...
        ]

    The list is ordered by ``created_at`` ASC, capped to the most
    recent ``limit`` messages. The chat LLM gets the freshest
    context without us having to compress manually.
    """
    from harness.chat.threads import get_messages

    msgs = await get_messages(thread_id, limit=limit, db=db)
    out: list[dict[str, Any]] = []
    for m in msgs:
        item: dict[str, Any] = {"role": m.role}
        if m.content is not None:
            item["content"] = m.content
        if m.tool_calls is not None:
            item["tool_calls"] = m.tool_calls
        if m.tool_call_id is not None:
            item["tool_call_id"] = m.tool_call_id
        if m.tool_name is not None and m.role == "tool":
            item["name"] = m.tool_name
        if m.is_error:
            item["is_error"] = True
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Stats / query helpers
# ---------------------------------------------------------------------------


async def get_thread_for_run(
    run_id: str,
    *,
    db: "Database | None" = None,
) -> ChatThread | None:
    """Convenience wrapper around :func:`get_thread_by_run_id`."""
    return await get_thread_by_run_id(run_id, db=db)


async def get_thread_for_session(
    session_id: str,
    *,
    db: "Database | None" = None,
) -> ChatThread | None:
    """Convenience wrapper around :func:`get_thread_by_session_id`."""
    from harness.chat.threads import get_thread_by_session_id
    return await get_thread_by_session_id(session_id, db=db)


async def touch_thread(
    thread_id: str,
    *,
    db: "Database | None" = None,
) -> None:
    """Bump the thread's ``updated_at`` without changing the message
    count. Used by the SSE handler when a token event arrives (to
    keep the sidebar sort fresh while a stream is in flight).
    """
    from harness.memory.db_context import get_db
    conn = db if db is not None else get_db()
    if conn is None:
        return
    try:
        await conn.execute(
            "UPDATE chat_threads SET updated_at = NOW() WHERE id = $1",
            thread_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("touch_thread: %s", exc)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "DEFAULT_HISTORY_LIMIT",
    "HIGH_SIGNAL_EVENT_TYPES",
    "MAX_EVENT_MESSAGE_CHARS",
    "ChatEventSink",
    "auto_create_thread_for_run",
    "build_chat_context",
    "get_thread_for_run",
    "get_thread_for_session",
    "post_assistant_message",
    "post_system_message",
    "post_tool_result",
    "post_user_message",
    "register_chat_event_sink",
    "touch_thread",
]
