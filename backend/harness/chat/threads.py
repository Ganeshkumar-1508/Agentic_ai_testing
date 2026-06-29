"""Chat threads + messages — the user-facing chat surface.

A :class:`ChatThread` is one conversation between the user and the chat
LLM. Threads come in two flavours (Q3, decision B):

  * **run-scoped** — auto-created 1:1 with a `job_specs.run_id` when
    ``submit_job`` fires. The chat for "the agent working on run
    4fed4879" is the single thread for that run.
  * **ad-hoc** — created directly by the user from the dashboard
    ``+ New chat`` button (⌘ N). ``run_id IS NULL``.

A :class:`ChatMessage` is one turn in a thread. The role is one of
``user``, ``assistant``, ``system``, or ``tool``. The streaming
shape is at the assistant-message level: the SSE handler emits
``chat.token`` events (Q6, decision A — TestAI wire names with a
``chat.`` prefix) and the backend appends the assembled message on
completion.

Schema (see ``backend/harness/memory/schema/schema.sql``):

  * ``chat_threads`` — one row per conversation; PK ``id`` (UUID v4).
    Counters (``message_count``, ``last_message_at``) are
    denormalised for the sidebar sort.
  * ``chat_messages`` — one row per turn; FK ``thread_id`` to
    ``chat_threads.id`` with ``ON DELETE CASCADE``.

The CRUD functions in this module are async and use
``harness.memory.db_context.get_db()`` for the global ``Database``
instance. Tools and routes that receive the ``Database`` via
dependency injection can call the ``*_with_db`` variants below to
use their own instance.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from harness.memory.db_context import get_db

if TYPE_CHECKING:
    from harness.memory.database import Database


logger = logging.getLogger(__name__)


# Default title for a freshly created thread. The first user message
# auto-overwrites this (see ``_auto_title_if_first_message``).
DEFAULT_THREAD_TITLE = "New conversation"

# Auto-title truncation length. Anthropic's "Effective harnesses for
# long-running agents" guidance: short titles, 5-10 words, < 80 chars.
AUTO_TITLE_MAX_CHARS = 80

# How the thread was created. Mirrors the ``source`` enum on
# ``job_specs`` so the dashboard can group threads by origin.
THREAD_SOURCES: tuple[str, ...] = ("user", "run", "github", "cron", "auto")

# Message role enum. The chat LLM emits 'user' and 'assistant' (with
# embedded 'tool_calls' JSONB). The system can inject 'system' for
# the Triage Officer persona, and the tool results land as 'tool'
# rows joined to the assistant's 'tool_calls' by ``tool_call_id``.
MESSAGE_ROLES: tuple[str, ...] = ("user", "assistant", "system", "tool")

# Finish reasons from the LLM (OpenAI-compatible). Mapped from the
# provider's native values.
FINISH_REASONS: tuple[str, ...] = ("stop", "tool_calls", "max_tokens", "error")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChatThread(BaseModel):
    """A single conversation thread.

    ``id`` is a UUID v4 string. ``title`` is auto-set from the first
    user message (truncated to ``AUTO_TITLE_MAX_CHARS`` chars on a
    word boundary) unless the user has manually set a different
    title. ``run_id`` is the 1:1 link to a ``job_specs.run_id`` when
    the thread was auto-created; ``ad-hoc`` threads have ``run_id IS
    NULL``.
    """
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str = DEFAULT_THREAD_TITLE
    run_id: str | None = None
    session_id: str | None = None
    source: str = "user"
    is_pinned: bool = False
    is_archived: bool = False
    message_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    """A single message in a thread.

    Roles:
      * ``user`` — the user typed it (also used for the orchestrator's
        seed prompt when a thread is auto-created 1:1 with a run).
      * ``assistant`` — the chat LLM's reply. ``tool_calls`` is the
        JSONB list of ``{id, name, args}`` for any tool calls the
        LLM emitted; the corresponding ``tool`` rows join on
        ``tool_call_id``.
      * ``system`` — operator-injected (e.g. the Triage Officer
        persona preamble).
      * ``tool`` — a tool result. ``tool_call_id`` joins back to the
        ``tool_calls[].id`` on the assistant's message; ``content``
        is the stringified result.

    ``finish_reason`` is one of :data:`FINISH_REASONS`. ``is_error``
    is set when the tool returned an error or the LLM produced an
    invalid output. The token + cost fields are filled in on
    assistant messages only.
    """
    model_config = ConfigDict(extra="ignore")

    id: str
    thread_id: str
    role: str
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_name: str | None = None
    is_error: bool = False
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Row converters
# ---------------------------------------------------------------------------


def _thread_from_row(row: Any) -> ChatThread:
    """Convert an ``asyncpg.Record`` from ``chat_threads`` to :class:`ChatThread`."""
    return ChatThread(
        id=row["id"],
        title=row["title"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        source=row["source"] or "user",
        is_pinned=row["is_pinned"],
        is_archived=row["is_archived"],
        message_count=row["message_count"] or 0,
        last_message_at=row["last_message_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _message_from_row(row: Any) -> ChatMessage:
    """Convert an ``asyncpg.Record`` from ``chat_messages`` to :class:`ChatMessage`.

    The ``tool_calls`` column is ``JSONB``; asyncpg returns it as a
    Python list or dict. Older DBs may return it as a JSON-encoded
    string — we parse defensively.
    """
    tool_calls = row["tool_calls"]
    if isinstance(tool_calls, str):
        try:
            tool_calls = json.loads(tool_calls) if tool_calls else None
        except json.JSONDecodeError:
            logger.debug("tool_calls parse failed for message %s", row.get("id"))
            tool_calls = None
    return ChatMessage(
        id=row["id"],
        thread_id=row["thread_id"],
        role=row["role"],
        content=row["content"],
        tool_call_id=row["tool_call_id"],
        tool_calls=tool_calls,
        tool_name=row["tool_name"],
        is_error=row["is_error"] or False,
        finish_reason=row["finish_reason"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        cost_usd=float(row["cost_usd"]) if row["cost_usd"] is not None else None,
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def new_thread_id() -> str:
    """Return a fresh UUID v4 string. Use this when you want the ID
    *before* the INSERT (e.g. for logging). ``create_thread`` calls
    this internally if you don't pass one.
    """
    return str(uuid.uuid4())


def new_message_id() -> str:
    """Return a fresh UUID v4 string for a message."""
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_title(text: str, max_chars: int = AUTO_TITLE_MAX_CHARS) -> str:
    """Truncate ``text`` to ``max_chars`` on a word boundary.

    Strips whitespace, replaces newlines with spaces, and adds an
    ellipsis if truncated. Returns :data:`DEFAULT_THREAD_TITLE` for
    empty input.
    """
    text = (text or "").replace("\n", " ").strip()
    if not text:
        return DEFAULT_THREAD_TITLE
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 1]
    # Prefer breaking on a space, but fall back to a hard cut if the
    # first max_chars-1 chars contain no space at all.
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip() + "..."


def _resolve_db(db: "Database | None") -> "Database":
    """Return the explicit ``db`` or fall back to the global instance.

    Raises :class:`RuntimeError` if neither is set — every CRUD call
    in this module needs a connected Database.
    """
    if db is not None:
        return db
    resolved = get_db()
    if resolved is None:
        raise RuntimeError(
            "Database not connected. Call Database.connect() at startup "
            "(api/main.py:lifespan) or pass an explicit Database."
        )
    return resolved


# ---------------------------------------------------------------------------
# CRUD — chat_threads
# ---------------------------------------------------------------------------


async def create_thread(
    *,
    title: str = DEFAULT_THREAD_TITLE,
    run_id: str | None = None,
    session_id: str | None = None,
    source: str = "user",
    thread_id: str | None = None,
    db: "Database | None" = None,
) -> ChatThread:
    """Create a new thread. Returns the persisted row.

    Args:
      title: initial title (defaults to :data:`DEFAULT_THREAD_TITLE`;
        auto-overwritten by the first user message if still default).
      run_id: 1:1 link to a ``job_specs.run_id`` (auto-created threads
        only; ``None`` for ad-hoc).
      session_id: the orchestrator's session id (auto-created threads
        only; ``None`` for ad-hoc).
      source: one of :data:`THREAD_SOURCES`. ``"user"`` for ad-hoc,
        ``"run"`` for auto-created on ``submit_job``, ``"auto"`` for
        system-created (e.g. an L2-reflection thread).
      thread_id: optional explicit id. If ``None``, a fresh UUID v4 is
        generated.
      db: optional explicit ``Database`` (skips the global lookup).
    """
    if source not in THREAD_SOURCES:
        raise ValueError(
            f"source must be one of {THREAD_SOURCES!r}, got {source!r}"
        )
    conn = _resolve_db(db)
    tid = thread_id or new_thread_id()
    now = _now_utc()
    await conn.execute(
        """
        INSERT INTO chat_threads
            (id, title, run_id, session_id, source, is_pinned, is_archived,
             message_count, last_message_at, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, false, false, 0, NULL, $6, $6)
        """,
        tid, title, run_id, session_id, source, now,
    )
    row = await conn.fetchrow(
        "SELECT * FROM chat_threads WHERE id = $1", tid,
    )
    return _thread_from_row(row)


async def get_thread(
    thread_id: str,
    *,
    db: "Database | None" = None,
) -> ChatThread | None:
    """Fetch a single thread by id. Returns ``None`` if not found."""
    conn = _resolve_db(db)
    row = await conn.fetchrow(
        "SELECT * FROM chat_threads WHERE id = $1", thread_id,
    )
    return _thread_from_row(row) if row else None


async def get_thread_by_run_id(
    run_id: str,
    *,
    db: "Database | None" = None,
) -> ChatThread | None:
    """Look up the auto-created thread for a run (1:1 with ``run_id``).

    The schema has a partial unique index on ``run_id WHERE run_id
    IS NOT NULL`` so this returns at most one row.
    """
    conn = _resolve_db(db)
    row = await conn.fetchrow(
        "SELECT * FROM chat_threads WHERE run_id = $1 LIMIT 1", run_id,
    )
    return _thread_from_row(row) if row else None


async def get_thread_by_session_id(
    session_id: str,
    *,
    db: "Database | None" = None,
) -> ChatThread | None:
    """Look up the thread bound to an orchestrator session id.

    The orchestrator's events carry ``session_id`` (which is the
    chat surface's session id, not the run_id). The chat event sink
    uses this to route orchestrator events into the right thread.

    If multiple threads share a ``session_id`` (the chat reuses a
    session across multiple runs), the most recently updated is
    returned. The schema does not enforce uniqueness on
    ``session_id`` because the user can create ad-hoc threads on
    the same session.
    """
    if not session_id:
        return None
    conn = _resolve_db(db)
    row = await conn.fetchrow(
        "SELECT * FROM chat_threads WHERE session_id = $1 "
        "ORDER BY updated_at DESC LIMIT 1",
        session_id,
    )
    return _thread_from_row(row) if row else None


async def list_threads(
    *,
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
    only_pinned: bool = False,
    source: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    db: "Database | None" = None,
) -> list[ChatThread]:
    """List threads ordered by pinned-first, then ``updated_at DESC``.

    Defaults: exclude archived; no source filter. Returns at most
    ``limit`` rows (default 50, max 200).
    """
    if limit < 1 or limit > 200:
        raise ValueError(f"limit must be 1..200, got {limit}")
    if source is not None and source not in THREAD_SOURCES:
        raise ValueError(f"source must be one of {THREAD_SOURCES!r}, got {source!r}")
    conn = _resolve_db(db)
    clauses: list[str] = []
    params: list[Any] = []
    if not include_archived:
        clauses.append("is_archived = false")
    if only_pinned:
        clauses.append("is_pinned = true")
    if source is not None:
        params.append(source)
        clauses.append(f"source = ${len(params)}")
    if run_id is not None:
        params.append(run_id)
        clauses.append(f"run_id = ${len(params)}")
    if session_id is not None:
        params.append(session_id)
        clauses.append(f"session_id = ${len(params)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    params.append(offset)
    rows = await conn.fetch(
        f"""
        SELECT * FROM chat_threads {where}
        ORDER BY is_pinned DESC, updated_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )
    return [_thread_from_row(r) for r in rows]


async def count_threads(
    *,
    include_archived: bool = False,
    source: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    db: "Database | None" = None,
) -> int:
    """Count threads matching the same filters as ``list_threads``.

    Used by the dashboard's "X conversations" badge and the
    chat list endpoint's ``total`` field.
    """
    conn = _resolve_db(db)
    clauses: list[str] = []
    params: list[Any] = []
    if not include_archived:
        clauses.append("is_archived = false")
    if source is not None:
        params.append(source)
        clauses.append(f"source = ${len(params)}")
    if run_id is not None:
        params.append(run_id)
        clauses.append(f"run_id = ${len(params)}")
    if session_id is not None:
        params.append(session_id)
        clauses.append(f"session_id = ${len(params)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return await conn.fetchval(
        f"SELECT COUNT(*) FROM chat_threads {where}", *params,
    )


async def update_thread_title(
    thread_id: str,
    title: str,
    *,
    db: "Database | None" = None,
) -> None:
    """Update the title; bumps ``updated_at`` so the sidebar re-sorts."""
    conn = _resolve_db(db)
    await conn.execute(
        "UPDATE chat_threads SET title = $1, updated_at = NOW() WHERE id = $2",
        title, thread_id,
    )


async def set_thread_pinned(
    thread_id: str,
    is_pinned: bool,
    *,
    db: "Database | None" = None,
) -> None:
    """Pin or unpin a thread. Pinned threads sort to the top of the list."""
    conn = _resolve_db(db)
    await conn.execute(
        "UPDATE chat_threads SET is_pinned = $1, updated_at = NOW() WHERE id = $2",
        is_pinned, thread_id,
    )


async def archive_thread(
    thread_id: str,
    *,
    db: "Database | None" = None,
) -> None:
    """Soft-delete: set ``is_archived = true``. The row stays in the
    table for audit / restore; excluded from :func:`list_threads` by
    default.
    """
    conn = _resolve_db(db)
    await conn.execute(
        "UPDATE chat_threads SET is_archived = true, updated_at = NOW() "
        "WHERE id = $1",
        thread_id,
    )


async def unarchive_thread(
    thread_id: str,
    *,
    db: "Database | None" = None,
) -> None:
    """Restore an archived thread."""
    conn = _resolve_db(db)
    await conn.execute(
        "UPDATE chat_threads SET is_archived = false, updated_at = NOW() "
        "WHERE id = $1",
        thread_id,
    )


# ---------------------------------------------------------------------------
# CRUD — chat_messages
# ---------------------------------------------------------------------------


async def append_message(
    *,
    thread_id: str,
    role: str,
    content: str | None = None,
    tool_call_id: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_name: str | None = None,
    is_error: bool = False,
    finish_reason: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
    message_id: str | None = None,
    db: "Database | None" = None,
) -> ChatMessage:
    """Append a message to a thread.

    Side effects:
      * bumps ``message_count`` and ``last_message_at`` on the thread.
      * if this is the **first** user message and the thread still
        has the default title, the title is auto-set to a truncated
        version of the content (see :func:`_auto_title_if_first_message`).

    Args:
      thread_id: the parent thread (must exist; FK enforces).
      role: one of :data:`MESSAGE_ROLES`.
      content: the message text. ``None`` is allowed for assistant
        messages that only contain ``tool_calls`` (the LLM emitted a
        tool call without prose).
      tool_call_id: present for ``role='tool'`` rows; joins to the
        ``tool_calls[].id`` on the assistant's message.
      tool_calls: present for ``role='assistant'`` rows that called
        tools; a list of ``{id, name, args}`` dicts.
      tool_name: present for ``role='tool'`` and (for the UI) the
        last ``tool_calls[].name`` of an assistant message.
      is_error: ``True`` for tool results that returned an error.
      finish_reason: one of :data:`FINISH_REASONS` (assistant only).
      prompt_tokens / completion_tokens / cost_usd: assistant only.
      message_id: optional explicit id. If ``None``, a fresh UUID v4.
      db: optional explicit ``Database``.

    Returns the persisted :class:`ChatMessage`.
    """
    if role not in MESSAGE_ROLES:
        raise ValueError(f"role must be one of {MESSAGE_ROLES!r}, got {role!r}")
    if finish_reason is not None and finish_reason not in FINISH_REASONS:
        raise ValueError(
            f"finish_reason must be one of {FINISH_REASONS!r}, got {finish_reason!r}"
        )
    conn = _resolve_db(db)
    mid = message_id or new_message_id()
    tool_calls_json = json.dumps(tool_calls) if tool_calls is not None else None
    async with conn._pool.acquire() as _conn:  # type: ignore[attr-defined]
        async with _conn.transaction():
            await _conn.execute(
                """
                INSERT INTO chat_messages
                    (id, thread_id, role, content, tool_call_id, tool_calls,
                     tool_name, is_error, finish_reason, prompt_tokens,
                     completion_tokens, cost_usd, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                """,
                mid, thread_id, role, content, tool_call_id, tool_calls_json,
                tool_name, is_error, finish_reason, prompt_tokens,
                completion_tokens, cost_usd,
            )
            # Bump thread counters atomically with the insert. Use the
            # post-increment value to decide if this is the first
            # message.
            new_count = await _conn.fetchval(
                """
                UPDATE chat_threads
                SET message_count = message_count + 1,
                    last_message_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING message_count
                """,
                thread_id,
            )
    # Auto-title: only on the first user message, only if the title
    # is still the default. Done outside the transaction so the read
    # is consistent.
    if (
        role == "user"
        and content
        and new_count == 1
    ):
        await _auto_title_if_first_message(thread_id, content, db=conn)
    row = await conn.fetchrow(
        "SELECT * FROM chat_messages WHERE id = $1", mid,
    )
    return _message_from_row(row)


async def _auto_title_if_first_message(
    thread_id: str,
    first_content: str,
    *,
    db: "Database | None" = None,
) -> None:
    """If the thread still has the default title, set it to a
    truncated version of ``first_content``.

    Respects manually-set titles: if the user created the thread
    with a custom title, we don't overwrite it.
    """
    conn = _resolve_db(db)
    thread = await get_thread(thread_id, db=conn)
    if thread is None:
        return
    if thread.title != DEFAULT_THREAD_TITLE:
        return
    new_title = _truncate_title(first_content)
    if new_title == thread.title:
        return
    await update_thread_title(thread_id, new_title, db=conn)


async def get_messages(
    thread_id: str,
    *,
    limit: int = 200,
    offset: int = 0,
    after_id: str | None = None,
    include_tool_results: bool = True,
    db: "Database | None" = None,
) -> list[ChatMessage]:
    """List messages in a thread, ordered by ``created_at`` ASC.

    Args:
      thread_id: the parent thread.
      limit: max rows (default 200, max 1000).
      offset: skip this many rows (paging).
      after_id: return only messages strictly after this id (for
        SSE replay — if a connection drops, the client resumes from
        the last id it received).
      include_tool_results: when False, omit role='tool' rows.
      db: optional explicit ``Database``.

    Returns the list of :class:`ChatMessage`.
    """
    if limit < 1 or limit > 1000:
        raise ValueError(f"limit must be 1..1000, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    conn = _resolve_db(db)
    if after_id is not None:
        rows = await conn.fetch(
            """
            SELECT m.* FROM chat_messages m
            WHERE m.thread_id = $1
              AND m.created_at > COALESCE(
                  (SELECT created_at FROM chat_messages WHERE id = $2),
                  '-infinity'::timestamptz
              )
            ORDER BY m.created_at ASC
            LIMIT $3 OFFSET $4
            """,
            thread_id, after_id, limit, offset,
        )
    else:
        role_clause = "" if include_tool_results else " AND role <> 'tool'"
        rows = await conn.fetch(
            f"SELECT * FROM chat_messages WHERE thread_id = $1{role_clause} "
            f"ORDER BY created_at ASC LIMIT $2 OFFSET $3",
            thread_id, limit, offset,
        )
    return [_message_from_row(r) for r in rows]


async def get_message(
    message_id: str,
    *,
    db: "Database | None" = None,
) -> ChatMessage | None:
    """Fetch a single message by id. Returns ``None`` if not found."""
    conn = _resolve_db(db)
    row = await conn.fetchrow(
        "SELECT * FROM chat_messages WHERE id = $1", message_id,
    )
    return _message_from_row(row) if row else None


async def count_messages(
    thread_id: str,
    *,
    db: "Database | None" = None,
) -> int:
    """Count messages in a thread. Cheap; used by the sidebar badge."""
    conn = _resolve_db(db)
    return await conn.fetchval(
        "SELECT COUNT(*) FROM chat_messages WHERE thread_id = $1",
        thread_id,
    )


async def delete_thread(
    thread_id: str,
    *,
    db: "Database | None" = None,
) -> None:
    """Hard-delete a thread. The FK ``ON DELETE CASCADE`` removes
    its messages. Use :func:`archive_thread` for the soft-delete
    case (default for the user "delete" action).
    """
    conn = _resolve_db(db)
    await conn.execute(
        "DELETE FROM chat_threads WHERE id = $1", thread_id,
    )


__all__ = [
    "AUTO_TITLE_MAX_CHARS",
    "DEFAULT_THREAD_TITLE",
    "FINISH_REASONS",
    "MESSAGE_ROLES",
    "THREAD_SOURCES",
    "ChatMessage",
    "ChatThread",
    "append_message",
    "archive_thread",
    "count_messages",
    "count_threads",
    "create_thread",
    "delete_thread",
    "get_message",
    "get_messages",
    "get_thread",
    "get_thread_by_run_id",
    "get_thread_by_session_id",
    "list_threads",
    "new_message_id",
    "new_thread_id",
    "set_thread_pinned",
    "unarchive_thread",
    "update_thread_title",
]
