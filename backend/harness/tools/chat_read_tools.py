"""Chat read tools — read-only queries over the chat surface.

The chat LLM needs to introspect its own conversation history:
"what did we say earlier?", "what's the thread for run X?",
"show me the last 10 messages". The four tools in this module
expose that history to the LLM via the existing tool registry.

The tools are registered in the `read` toolset, which the chat
Role's `CHAT_READONLY_TOOLSET` composes from. The tools read from
the same Postgres tables the API router reads, using the global
``db_context.get_db()`` — no separate store wiring is required
because the chat LLM only runs inside a request scope where the
db context is populated by the FastAPI lifespan.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from harness.chat.threads import (
    get_messages,
    get_thread,
    get_thread_by_run_id,
    list_threads,
)
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


_db_ref: dict[str, Any] = {}


def set_chat_db(db: Any) -> None:
    _db_ref["db"] = db


def _db_or_error() -> tuple[Any, ToolResult | None]:
    db = _db_ref.get("db")
    if db is None:
        return None, ToolResult(
            success=False,
            output="Chat DB not initialized (set_chat_db not called).",
            error="not_initialized",
        )
    return db, None


def _truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    return text if len(text) <= max_chars else text[:max_chars] + "..."


def _thread_to_dict(t) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "source": t.source,
        "run_id": t.run_id,
        "session_id": t.session_id,
        "is_archived": t.is_archived,
        "is_pinned": t.is_pinned,
        "message_count": t.message_count,
        "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
    }


def _message_to_dict(m) -> dict[str, Any]:
    return {
        "id": m.id,
        "thread_id": m.thread_id,
        "role": m.role,
        "content": m.content,
        "tool_call_id": m.tool_call_id,
        "tool_calls": m.tool_calls,
        "finish_reason": m.finish_reason,
        "is_error": m.is_error,
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "cost_usd": float(m.cost_usd) if m.cost_usd is not None else None,
        "created_at": m.created_at.isoformat() if m.created_at else "",
    }


class ListChatThreadsTool(BaseTool):
    name = "list_chat_threads"
    default_level = "allow"
    description = (
        "List chat threads, newest first. Each thread is a 1:1 "
        "conversation (either auto-created for a run, or ad-hoc). "
        "Use when the user asks 'what threads exist?', 'what's in my "
        "chat history?', or 'what did we say earlier?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Filter to threads for a specific run"},
                    "session_id": {"type": "string", "description": "Filter to threads for a specific chat session"},
                    "archived": {"type": "boolean", "default": False, "description": "Include archived threads"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        db, err = _db_or_error()
        if err is not None:
            return err
        run_id = (kwargs.get("run_id") or "").strip() or None
        session_id = (kwargs.get("session_id") or "").strip() or None
        archived = bool(kwargs.get("archived", False))
        try:
            limit = max(1, min(100, int(kwargs.get("limit", 20))))
        except (TypeError, ValueError):
            limit = 20
        try:
            threads = await list_threads(
                run_id=run_id, session_id=session_id,
                include_archived=archived, limit=limit, offset=0, db=db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_chat_threads: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if not threads:
            return ToolResult(
                success=True,
                output="No chat threads found.",
                data={"threads": []},
            )
        items = [_thread_to_dict(t) for t in threads]
        lines = [f"## {len(items)} chat thread(s)\n"]
        for t in items:
            marker = " (archived)" if t["is_archived"] else ""
            run_part = f" run={t['run_id'][:8]}" if t["run_id"] else " ad-hoc"
            lines.append(
                f"- `{t['id'][:12]}` {t['title'] or 'untitled'}{marker}"
                f"{run_part}  msgs={t['message_count']}"
            )
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"threads": items},
        )


class GetChatThreadTool(BaseTool):
    name = "get_chat_thread"
    default_level = "allow"
    description = (
        "Get a single chat thread by id (or by run_id). Returns "
        "thread metadata. Use when the user asks 'what's the thread "
        "for run X?' or 'show me thread Y'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread id (preferred)"},
                    "run_id": {"type": "string", "description": "Or look up by run_id"},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        db, err = _db_or_error()
        if err is not None:
            return err
        thread_id = (kwargs.get("thread_id") or "").strip() or None
        run_id = (kwargs.get("run_id") or "").strip() or None
        if not thread_id and not run_id:
            return ToolResult(
                success=False,
                output="Provide either `thread_id` or `run_id`.",
                error="missing_arg",
            )
        try:
            thread = None
            if thread_id:
                thread = await get_thread(thread_id, db=db)
            if thread is None and run_id:
                thread = await get_thread_by_run_id(run_id, db=db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_chat_thread: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if thread is None:
            return ToolResult(
                success=False,
                output="Thread not found.",
                error="not_found",
            )
        item = _thread_to_dict(thread)
        return ToolResult(
            success=True,
            output=(
                f"## Thread `{item['id']}`\n"
                f"- title: {item['title']}\n"
                f"- source: {item['source']}  run_id: {item['run_id']}\n"
                f"- messages: {item['message_count']}\n"
                f"- last activity: {item['last_message_at']}\n"
                f"- archived: {item['is_archived']}"
            ),
            data={"thread": item},
        )


class ListChatThreadMessagesTool(BaseTool):
    name = "list_chat_thread_messages"
    default_level = "allow"
    description = (
        "List messages in a chat thread, oldest first. Use when "
        "the user asks 'what did we say earlier?', 'show me the last "
        "N messages', or 'replay this thread'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread id"},
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
                    "include_tool_results": {"type": "boolean", "default": False},
                },
                "required": ["thread_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        db, err = _db_or_error()
        if err is not None:
            return err
        thread_id = (kwargs.get("thread_id") or "").strip()
        if not thread_id:
            return ToolResult(
                success=False,
                output="Provide `thread_id`.",
                error="missing_arg",
            )
        try:
            limit = max(1, min(500, int(kwargs.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50
        include_tool = bool(kwargs.get("include_tool_results", False))
        try:
            messages = await get_messages(
                thread_id,
                limit=limit, offset=0,
                include_tool_results=include_tool,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_chat_thread_messages: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if not messages:
            return ToolResult(
                success=True,
                output=f"No messages in thread `{thread_id[:12]}`.",
                data={"messages": []},
            )
        items = [_message_to_dict(m) for m in messages]
        lines = [f"## {len(items)} message(s) in `{thread_id[:12]}`\n"]
        for m in items:
            role = m["role"]
            content = _truncate(m["content"], 300)
            if role == "tool":
                lines.append(
                    f"- [{m['created_at']}] tool `{m['tool_call_id']}`: "
                    f"{content}  (error={m['is_error']})"
                )
            else:
                lines.append(f"- [{m['created_at']}] **{role}**: {content}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"messages": items},
        )


class GetChatThreadForRunTool(BaseTool):
    name = "get_chat_thread_for_run"
    default_level = "allow"
    description = (
        "Look up the chat thread auto-created for a run (1:1 with "
        "the run's session). Returns the thread id + title. Use "
        "when the user says 'show me the chat for run X' or you "
        "need to attach a message to an existing thread."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Run id"},
                },
                "required": ["run_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        db, err = _db_or_error()
        if err is not None:
            return err
        run_id = (kwargs.get("run_id") or "").strip()
        if not run_id:
            return ToolResult(
                success=False,
                output="Provide `run_id`.",
                error="missing_arg",
            )
        try:
            thread = await get_thread_by_run_id(run_id, db=db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_chat_thread_for_run: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if thread is None:
            return ToolResult(
                success=True,
                output=f"No chat thread exists for run `{run_id[:8]}` yet.",
                data={"thread": None, "run_id": run_id},
            )
        item = _thread_to_dict(thread)
        return ToolResult(
            success=True,
            output=(
                f"Thread `{item['id']}` for run `{run_id[:8]}`: "
                f"title={item['title']!r}, msgs={item['message_count']}"
            ),
            data={"thread": item, "run_id": run_id},
        )


registry.register(ListChatThreadsTool(), toolset="read")
registry.register(GetChatThreadTool(), toolset="read")
registry.register(ListChatThreadMessagesTool(), toolset="read")
registry.register(GetChatThreadForRunTool(), toolset="read")
