"""SSE generator for the chat surface."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Awaitable, Callable, TYPE_CHECKING

from harness.chat.threads import (
    FINISH_REASONS,
    new_message_id,
)
from harness.chat.service import (
    post_assistant_message,
    post_tool_result,
    post_user_message,
)

if TYPE_CHECKING:
    from harness.agent.agent import Agent
    from harness.core.events import StreamEvent
    from harness.memory.database import Database


logger = logging.getLogger(__name__)


EVENT_CONNECTED = "connected"
EVENT_RUN_STARTED = "chat.run.started"
EVENT_MESSAGE_START = "chat.message.start"
EVENT_TOKEN = "chat.token"
EVENT_TOOL_STARTED = "chat.tool.started"
EVENT_TOOL_COMPLETED = "chat.tool.completed"
EVENT_MESSAGE_END = "chat.message.end"
EVENT_RUN_COMPLETED = "chat.run.completed"
EVENT_RUN_CANCELLED = "chat.run.cancelled"
EVENT_ERROR = "chat.error"
EVENT_PING = "ping"

KEEPALIVE_INTERVAL_SECONDS = 25.0
GET_TIMEOUT_SECONDS = 1.0
DEFAULT_MAX_RUN_SECONDS = 300.0


def _frame(event: str, data: dict[str, Any] | None = None) -> dict[str, str]:
    payload = {} if data is None else data
    return {"event": event, "data": json.dumps(payload, default=str)}


class StreamChatResponse:

    def __init__(
        self,
        *,
        thread_id: str,
        user_content: str,
        agent: "Agent",
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
        db: "Database | None" = None,
        max_run_seconds: float = DEFAULT_MAX_RUN_SECONDS,
        history_limit: int = 50,
    ) -> None:
        self.thread_id = thread_id
        self.user_content = user_content
        self.agent = agent
        self.is_disconnected = is_disconnected
        self._explicit_db = db
        self.max_run_seconds = max_run_seconds
        self.history_limit = history_limit
        self._cancelled = False
        self._current_message_id: str | None = None
        self._accum_text: str = ""
        self._accum_tool_calls: list[dict[str, Any]] = []
        self._accum_prompt_tokens: int = 0
        self._accum_completion_tokens: int = 0
        self._active_tools: dict[str, dict[str, Any]] = {}
        self._pending_tool_results: list[dict[str, Any]] = []

    def cancel(self) -> None:
        self._cancelled = True

    async def stream(self) -> AsyncIterator[dict[str, str]]:
        yield _frame(EVENT_CONNECTED, {"thread_id": self.thread_id})

        try:
            await post_user_message(self.thread_id, self.user_content, db=self._explicit_db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("stream_chat: post_user_message failed: %s", exc)

        started_at = time.monotonic()
        yield _frame(EVENT_RUN_STARTED, {
            "thread_id": self.thread_id,
            "run_id": self.thread_id,
            "input": self.user_content[:200],
            "model": getattr(self.agent, "model_override", None) or "default",
            "mode": getattr(self.agent, "mode", "chat"),
        })

        self._current_message_id = new_message_id()

        rounds = 0
        finish_reason: str = "stop"
        error_event: dict[str, Any] | None = None
        cancelled = False
        try:
            async with asyncio.timeout(self.max_run_seconds):
                async for ev in self.agent.run_stream(self.user_content):
                    if self._cancelled or await self._is_disconnected():
                        cancelled = True
                        break
                    for frame in self._translate_event(ev):
                        if frame is not None:
                            yield frame
                    if ev.__class__.__name__ == "RoundCompleted":
                        rounds += 1
                    if ev.__class__.__name__ == "ErrorEvent":
                        error_event = self._event_payload(ev)
                        break
        except asyncio.TimeoutError:
            error_event = {
                "category": "max_tokens",
                "message": f"chat run exceeded {self.max_run_seconds:.0f}s",
            }
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("stream_chat: agent.run_stream raised: %s", exc)
            error_event = {"category": "error", "message": str(exc)}
        finally:
            for kwargs in self._pending_tool_results:
                try:
                    await post_tool_result(**kwargs)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "stream_chat: post_tool_result failed: %s", exc,
                    )
            err_msg = (error_event or {}).get("message") if error_event else None
            await self._persist_assistant_message(
                finish_reason,
                is_error=bool(error_event),
                error_message=err_msg,
            )

        if error_event is not None:
            yield _frame(EVENT_ERROR, {
                "thread_id": self.thread_id,
                "category": error_event.get("category", "error"),
                "message": error_event.get("message", ""),
            })
            yield _frame(EVENT_RUN_COMPLETED, {
                "thread_id": self.thread_id,
                "outcome": {"type": "error"},
                "rounds": rounds,
                "duration_s": round(time.monotonic() - started_at, 3),
                "error": error_event,
            })
        elif cancelled:
            yield _frame(EVENT_RUN_CANCELLED, {
                "thread_id": self.thread_id,
                "outcome": {"type": "cancelled"},
                "rounds": rounds,
                "duration_s": round(time.monotonic() - started_at, 3),
            })
        else:
            yield _frame(EVENT_RUN_COMPLETED, {
                "thread_id": self.thread_id,
                "outcome": {"type": "success"},
                "rounds": rounds,
                "duration_s": round(time.monotonic() - started_at, 3),
            })

    def _translate_event(self, ev: "StreamEvent") -> list[dict[str, str] | None]:
        cls = ev.__class__.__name__
        out: list[dict[str, str] | None] = []

        if cls == "TokenGenerated":
            content = getattr(ev, "content", "") or ""
            if not content:
                return out
            if not self._accum_text:
                out.append(_frame(EVENT_MESSAGE_START, {
                    "thread_id": self.thread_id,
                    "message_id": self._current_message_id,
                    "role": "assistant",
                }))
            self._accum_text += content
            out.append(_frame(EVENT_TOKEN, {
                "thread_id": self.thread_id,
                "message_id": self._current_message_id,
                "delta": content,
            }))
            return out

        if cls == "ReasoningGenerated":
            return out

        if cls == "LLMCallCompleted":
            inp = getattr(ev, "prompt_tokens", 0) or 0
            out_ = getattr(ev, "completion_tokens", 0) or 0
            self._accum_prompt_tokens += int(inp)
            self._accum_completion_tokens += int(out_)
            return out

        if cls == "ToolExecutionStarted":
            tc_id = getattr(ev, "trace_id", None) or new_message_id()
            tool_name = getattr(ev, "tool_name", "")
            tool_input = getattr(ev, "tool_input", "")
            if not self._accum_text and not self._accum_tool_calls:
                out.append(_frame(EVENT_MESSAGE_START, {
                    "thread_id": self.thread_id,
                    "message_id": self._current_message_id,
                    "role": "assistant",
                }))
            self._active_tools[tc_id] = {
                "name": tool_name,
                "input": tool_input,
                "is_error": False,
                "output": None,
            }
            self._accum_tool_calls.append({
                "id": tc_id,
                "name": tool_name,
                "args": tool_input,
            })
            out.append(_frame(EVENT_TOOL_STARTED, {
                "thread_id": self.thread_id,
                "message_id": self._current_message_id,
                "tool_call_id": tc_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
            }))
            return out

        if cls == "ToolExecutionCompleted":
            tc_id = getattr(ev, "trace_id", None) or ""
            is_error = getattr(ev, "is_error", False) or False
            output = getattr(ev, "output_preview", "")
            entry = self._active_tools.get(tc_id)
            if entry is not None:
                entry["is_error"] = is_error
                entry["output"] = output
            out.append(_frame(EVENT_TOOL_COMPLETED, {
                "thread_id": self.thread_id,
                "message_id": self._current_message_id,
                "tool_call_id": tc_id,
                "tool_name": (entry or {}).get("name", ""),
                "is_error": is_error,
                "output_preview": (output or "")[:600],
            }))
            self._pending_tool_results.append({
                "thread_id": self.thread_id,
                "tool_call_id": tc_id,
                "tool_name": (entry or {}).get("name", ""),
                "content": (output or "")[:2000],
                "is_error": is_error,
                "db": self._explicit_db,
            })
            return out

        if cls == "AgentCompleted":
            finish_reason = (
                "tool_calls" if self._accum_tool_calls else "stop"
            )
            out.append(self._build_message_end(finish_reason))
            return out

        if cls == "RoundCompleted":
            return out

        if cls == "AgentStarted":
            return out

        if cls == "RoundStarted":
            return out

        if cls == "LLMCallStarted":
            return out

        if cls == "SubagentSpawned":
            return out

        if cls == "SubagentCompleted":
            return out

        if cls == "SubagentHeartbeat":
            return out

        if cls == "ApprovalRequired":
            return out

        if cls == "ReflexionInjected":
            return out

        if cls == "BudgetThrottled":
            return out

        if cls == "StatusEvent":
            return out

        return out

    def _build_message_end(self, finish_reason: str) -> dict[str, str]:
        return _frame(EVENT_MESSAGE_END, {
            "thread_id": self.thread_id,
            "message_id": self._current_message_id,
            "finish_reason": finish_reason
                if finish_reason in FINISH_REASONS else "stop",
            "prompt_tokens": self._accum_prompt_tokens,
            "completion_tokens": self._accum_completion_tokens,
            "cost_usd": 0.0,
        })

    def _event_payload(self, ev: "StreamEvent") -> dict[str, Any]:
        return {
            "category": getattr(ev, "category", "error"),
            "message": getattr(ev, "message", str(ev)),
            "recoverable": getattr(ev, "recoverable", False),
        }

    async def _persist_assistant_message(
        self, finish_reason: str, *, is_error: bool, error_message: str | None = None,
    ) -> None:
        if not self._accum_text and not self._accum_tool_calls and not is_error:
            return
        try:
            await post_assistant_message(
                self.thread_id,
                content=self._accum_text or (error_message or None),
                tool_calls=self._accum_tool_calls or None,
                finish_reason=finish_reason
                    if finish_reason in FINISH_REASONS else "stop",
                prompt_tokens=self._accum_prompt_tokens or None,
                completion_tokens=self._accum_completion_tokens or None,
                cost_usd=None,
                is_error=is_error,
                db=self._explicit_db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "stream_chat: post_assistant_message failed: %s", exc,
            )

    async def _is_disconnected(self) -> bool:
        if self._cancelled:
            return True
        if self.is_disconnected is None:
            return False
        try:
            return bool(await self.is_disconnected())
        except Exception:  # noqa: BLE001
            return False


async def stream_chat_response(
    *,
    thread_id: str,
    user_content: str,
    agent: "Agent",
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    db: "Database | None" = None,
    max_run_seconds: float = DEFAULT_MAX_RUN_SECONDS,
    history_limit: int = 50,
) -> AsyncIterator[dict[str, str]]:
    sse = StreamChatResponse(
        thread_id=thread_id,
        user_content=user_content,
        agent=agent,
        is_disconnected=is_disconnected,
        db=db,
        max_run_seconds=max_run_seconds,
        history_limit=history_limit,
    )
    async for frame in sse.stream():
        yield frame


async def replay_thread_messages(
    *,
    thread_id: str,
    after_message_id: str | None = None,
    db: "Database | None" = None,
) -> AsyncIterator[dict[str, str]]:
    from harness.chat.threads import get_message, get_messages

    yield _frame(EVENT_CONNECTED, {"thread_id": thread_id})

    if after_message_id is not None:
        anchor = await get_message(after_message_id, db=db)
        if anchor is None:
            messages = await get_messages(thread_id, db=db)
        else:
            all_msgs = await get_messages(thread_id, db=db)
            anchor_dt = anchor.created_at
            messages = [m for m in all_msgs if m.created_at > anchor_dt]
    else:
        messages = await get_messages(thread_id, db=db)

    for m in messages:
        if m.role != "assistant":
            continue
        yield _frame(EVENT_MESSAGE_START, {
            "thread_id": thread_id,
            "message_id": m.id,
            "role": "assistant",
        })
        if m.content:
            yield _frame(EVENT_TOKEN, {
                "thread_id": thread_id,
                "message_id": m.id,
                "delta": m.content,
            })
        if m.tool_calls:
            for tc in m.tool_calls:
                yield _frame(EVENT_TOOL_STARTED, {
                    "thread_id": thread_id,
                    "message_id": m.id,
                    "tool_call_id": tc.get("id", ""),
                    "tool_name": tc.get("name", ""),
                    "tool_input": tc.get("args", ""),
                })
                tc_id = tc.get("id", "")
                if tc_id:
                    from harness.chat.threads import get_messages as _gm
                    all_msgs = await _gm(thread_id, db=db)
                    for tm in all_msgs:
                        if tm.role == "tool" and tm.tool_call_id == tc_id:
                            yield _frame(EVENT_TOOL_COMPLETED, {
                                "thread_id": thread_id,
                                "message_id": m.id,
                                "tool_call_id": tc_id,
                                "tool_name": tc.get("name", ""),
                                "is_error": tm.is_error,
                                "output_preview": (tm.content or "")[:600],
                            })
                            break
        yield _frame(EVENT_MESSAGE_END, {
            "thread_id": thread_id,
            "message_id": m.id,
            "finish_reason": m.finish_reason or "stop",
            "prompt_tokens": m.prompt_tokens or 0,
            "completion_tokens": m.completion_tokens or 0,
            "cost_usd": m.cost_usd or 0.0,
        })
    yield _frame(EVENT_RUN_COMPLETED, {
        "thread_id": thread_id,
        "outcome": {"type": "replay"},
        "rounds": 0,
        "duration_s": 0.0,
    })


__all__ = [
    "DEFAULT_MAX_RUN_SECONDS",
    "EVENT_CONNECTED",
    "EVENT_ERROR",
    "EVENT_MESSAGE_END",
    "EVENT_MESSAGE_START",
    "EVENT_PING",
    "EVENT_RUN_CANCELLED",
    "EVENT_RUN_COMPLETED",
    "EVENT_RUN_STARTED",
    "EVENT_TOKEN",
    "EVENT_TOOL_COMPLETED",
    "EVENT_TOOL_STARTED",
    "GET_TIMEOUT_SECONDS",
    "KEEPALIVE_INTERVAL_SECONDS",
    "StreamChatResponse",
    "replay_thread_messages",
    "stream_chat_response",
    "stream_thread_events",
]


async def stream_thread_events(
    *,
    thread_id: str,
    event_sink: Any,
    is_disconnected: Any | None = None,
    db: "Database | None" = None,
    max_idle_seconds: float = KEEPALIVE_INTERVAL_SECONDS,
) -> AsyncIterator[dict[str, str]]:
    """Stream chat.* frames for events arriving on the thread's run.

    Looks up the thread, derives the run_id (= orchestrator's
    session_id), subscribes to ``event_sink`` for that session, and
    translates each event to a chat.* SSE frame. The frontend can
    open this stream immediately after the orchestrator dispatches;
    no user message is required.

    This is the GET-friendly counterpart to
    :func:`stream_chat_response` (which is POST-only). It powers
    the dashboard's live event stream after ``submit_job`` returns
    a thread_id.

    The generator never raises; it yields a final ``chat.run.completed``
    on disconnect and exits cleanly.
    """
    from harness.chat.threads import get_thread

    thread = await get_thread(thread_id, db=db)
    if thread is None:
        yield _frame(EVENT_ERROR, {
            "thread_id": thread_id,
            "category": "not_found",
            "message": f"thread {thread_id} not found",
        })
        return

    run_id = thread.run_id
    if not run_id:
        yield _frame(EVENT_ERROR, {
            "thread_id": thread_id,
            "category": "no_run",
            "message": "thread has no run_id; orchestrator not started",
        })
        return

    queue = event_sink.subscribe(run_id)
    yield _frame(EVENT_CONNECTED, {"thread_id": thread_id})

    started_at = time.monotonic()
    current_message_id: str | None = None
    finished = False

    try:
        while not finished:
            if is_disconnected is not None:
                try:
                    if await is_disconnected():
                        break
                except Exception:  # noqa: BLE001
                    pass

            try:
                ev = await asyncio.wait_for(queue.get(), timeout=GET_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                if time.monotonic() - started_at > 0 and (time.monotonic() - started_at) % max_idle_seconds < GET_TIMEOUT_SECONDS:
                    yield _frame(EVENT_PING, {})
                continue

            for frame in _translate_orchestrator_event(ev, thread_id, current_message_id):
                if frame is not None:
                    yield frame
                ev_name = frame["event"]
                if ev_name == EVENT_TOKEN and current_message_id is None:
                    current_message_id = new_message_id()
                if ev_name == EVENT_MESSAGE_END:
                    current_message_id = None
                if ev_name in (EVENT_RUN_COMPLETED, EVENT_RUN_CANCELLED, EVENT_ERROR):
                    finished = True
                    break
    finally:
        try:
            event_sink.unsubscribe(run_id, queue)
        except Exception:  # noqa: BLE001
            pass


def _field(ev: Any, name: str, default: Any = None) -> Any:
    """Read a field from a typed StreamEvent or its ``.data`` dict.

    ``GenericStreamEvent`` (the orchestrator's high-signal event
    envelope) carries its payload in ``ev.data``; typed events
    expose fields as attributes. This helper unifies the lookup.
    """
    v = getattr(ev, name, None)
    if v is not None:
        return v
    data = getattr(ev, "data", None)
    if isinstance(data, dict):
        return data.get(name, default)
    return default


def _translate_orchestrator_event(
    ev: Any,
    thread_id: str,
    current_message_id: str | None,
) -> list[dict[str, str] | None]:
    """Translate a single orchestrator StreamEvent into 0+ chat.* SSE frames.

    Mirrors the dispatch table in :meth:`StreamChatResponse._translate_event`
    but as a stateless function: it only reads the event's attributes, no
    accumulator state. The frontend accumulates the deltas itself.
    """
    from harness.events import wire_name

    wname = wire_name(ev)
    out: list[dict[str, str] | None] = []

    if wname == "agent.started":
        out.append(_frame(EVENT_RUN_STARTED, {
            "thread_id": thread_id,
            "run_id": getattr(ev, "session_id", "") or "",
            "input": (str(_field(ev, "input", "") or ""))[:200],
        }))
        return out

    if wname == "agent.completed":
        out.append(_frame(EVENT_RUN_COMPLETED, {
            "thread_id": thread_id,
            "outcome": {"type": "success"},
            "rounds": int(_field(ev, "rounds", 0) or 0),
            "duration_s": 0.0,
        }))
        return out

    if wname == "agent.cancelled":
        out.append(_frame(EVENT_RUN_CANCELLED, {
            "thread_id": thread_id,
            "outcome": {"type": "cancelled"},
        }))
        return out

    if wname == "token.generated":
        content = str(_field(ev, "content", "") or "")
        if not content:
            return out
        mid = current_message_id or ""
        if not mid:
            mid = new_message_id()
            out.append(_frame(EVENT_MESSAGE_START, {
                "thread_id": thread_id,
                "message_id": mid,
                "role": "assistant",
            }))
        out.append(_frame(EVENT_TOKEN, {
            "thread_id": thread_id,
            "message_id": mid,
            "delta": content,
        }))
        return out

    if wname == "reasoning.generated":
        return out

    if wname == "tool.started":
        tc_id = str(_field(ev, "trace_id", "") or "") or new_message_id()
        mid = current_message_id or ""
        out.append(_frame(EVENT_TOOL_STARTED, {
            "thread_id": thread_id,
            "message_id": mid,
            "tool_call_id": tc_id,
            "tool_name": str(_field(ev, "tool_name", "") or ""),
            "tool_input": str(_field(ev, "tool_input", "") or ""),
        }))
        return out

    if wname == "tool.completed":
        tc_id = str(_field(ev, "trace_id", "") or "")
        mid = current_message_id or ""
        out.append(_frame(EVENT_TOOL_COMPLETED, {
            "thread_id": thread_id,
            "message_id": mid,
            "tool_call_id": tc_id,
            "tool_name": str(_field(ev, "tool_name", "") or ""),
            "is_error": bool(_field(ev, "is_error", False)),
            "output_preview": (str(_field(ev, "output_preview", "") or ""))[:600],
        }))
        return out

    if wname == "llm.call.completed":
        prompt = int(_field(ev, "prompt_tokens", 0) or 0)
        completion = int(_field(ev, "completion_tokens", 0) or 0)
        mid = current_message_id or ""
        out.append(_frame(EVENT_MESSAGE_END, {
            "thread_id": thread_id,
            "message_id": mid,
            "finish_reason": "stop",
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cost_usd": 0.0,
        }))
        return out

    if wname == "error":
        out.append(_frame(EVENT_ERROR, {
            "thread_id": thread_id,
            "category": str(_field(ev, "category", "error") or "error"),
            "message": str(_field(ev, "message", str(ev)) or str(ev)),
        }))
        return out

    if wname == "approval.required":
        out.append(_frame(EVENT_ERROR, {
            "thread_id": thread_id,
            "category": "approval_required",
            "message": str(_field(ev, "command", "") or "approval required"),
        }))
        return out

    return out
