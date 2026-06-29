"""Smoke test: GET /api/chat/threads/{id}/stream SSE bridge.

Verifies that the GET SSE endpoint subscribes to the EventSourceSink
via the thread's run_id, translates orchestrator events to chat.*
frames, and yields a clean stream.

Tests:
  1. Empty queue (no events) — connect → chat.error("not_found")
  2. Missing run_id — 409
  3. Live events: agent.started → token.generated → tool.* → agent.completed
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from harness.events import EventSourceSink
from harness.api.state import GenericStreamEvent


def parse_sse_payload(data_str: str) -> dict:
    import json
    return json.loads(data_str)


async def _setup():
    from harness.memory.database import Database
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    db = Database(url)
    await db.connect()
    from harness.memory.db_context import set_db
    set_db(db)
    from harness.tools.chat_read_tools import set_chat_db
    set_chat_db(db)
    return db


async def _make_thread(db, run_id: str | None = None) -> str:
    from harness.chat.threads import create_thread
    kwargs: dict = {"source": "user", "title": "smoke stream"}
    if run_id:
        kwargs["run_id"] = run_id
    thread = await create_thread(db=db, **kwargs)
    return thread.id


async def _consume(generator, n: int, timeout: float = 2.0) -> list:
    out = []
    try:
        while len(out) < n:
            ev = await asyncio.wait_for(generator.__anext__(), timeout=timeout)
            out.append(ev)
    except (asyncio.TimeoutError, StopAsyncIteration):
        pass
    return out


async def run() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    from harness.chat.sse import stream_thread_events, _translate_orchestrator_event

    db = await _setup()

    print("[1] translator: agent.started → chat.run.started")
    ev = GenericStreamEvent(event_type="agent.started", session_id="r1", data={"input": "hi"})
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("1 frame", len(frames) == 1, f"n={len(frames)}")
    if frames:
        check("event=chat.run.started", frames[0]["event"] == "chat.run.started")
        payload = parse_sse_payload(frames[0]["data"])
        check("thread_id=thread-1", payload["thread_id"] == "thread-1")
        check("input=hi", payload.get("input") == "hi")

    print("[2] translator: token.generated → chat.message.start + chat.token")
    current_mid: str | None = None
    ev = GenericStreamEvent(event_type="token.generated", session_id="r1", data={"content": "hello"})
    frames = _translate_orchestrator_event(ev, "thread-1", current_mid)
    check("2 frames (start + token)", len(frames) == 2, f"n={len(frames)}")
    if len(frames) == 2:
        check("first=chat.message.start", frames[0]["event"] == "chat.message.start")
        check("second=chat.token", frames[1]["event"] == "chat.token")
        token_payload = parse_sse_payload(frames[1]["data"])
        check("delta=hello", token_payload.get("delta") == "hello")
        check("message_id is set", bool(token_payload.get("message_id")))

    print("[3] translator: token.generated with current_message_id → only token")
    from harness.chat.threads import new_message_id
    existing_mid = new_message_id()
    ev = GenericStreamEvent(event_type="token.generated", session_id="r1", data={"content": " world"})
    frames = _translate_orchestrator_event(ev, "thread-1", existing_mid)
    check("1 frame (token only)", len(frames) == 1, f"n={len(frames)}")
    if frames:
        check("event=chat.token", frames[0]["event"] == "chat.token")
        payload = parse_sse_payload(frames[0]["data"])
        check("delta=' world'", payload.get("delta") == " world")
        check("uses existing message_id", payload.get("message_id") == existing_mid)

    print("[4] translator: tool.started → chat.tool.started")
    ev = GenericStreamEvent(
        event_type="tool.started",
        session_id="r1",
        data={"tool_name": "bash", "tool_input": "ls", "trace_id": "tc-1"},
    )
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("1 frame", len(frames) == 1)
    if frames:
        check("event=chat.tool.started", frames[0]["event"] == "chat.tool.started")
        payload = parse_sse_payload(frames[0]["data"])
        check("tool_name=bash", payload.get("tool_name") == "bash")
        check("trace_id=tc-1", payload.get("tool_call_id") == "tc-1")

    print("[5] translator: tool.completed → chat.tool.completed")
    ev = GenericStreamEvent(
        event_type="tool.completed",
        session_id="r1",
        data={"tool_name": "bash", "is_error": False, "output_preview": "ok", "trace_id": "tc-1"},
    )
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("1 frame", len(frames) == 1)
    if frames:
        check("event=chat.tool.completed", frames[0]["event"] == "chat.tool.completed")
        payload = parse_sse_payload(frames[0]["data"])
        check("output_preview=ok", payload.get("output_preview") == "ok")

    print("[6] translator: llm.call.completed → chat.message.end")
    ev = GenericStreamEvent(
        event_type="llm.call.completed",
        session_id="r1",
        data={"prompt_tokens": 100, "completion_tokens": 50, "model": "test", "round": 1, "total_tokens": 150, "call_id": "c1"},
    )
    frames = _translate_orchestrator_event(ev, "thread-1", new_message_id())
    check("1 frame", len(frames) == 1)
    if frames:
        check("event=chat.message.end", frames[0]["event"] == "chat.message.end")
        payload = parse_sse_payload(frames[0]["data"])
        check("prompt_tokens=100", payload.get("prompt_tokens") == 100)
        check("completion_tokens=50", payload.get("completion_tokens") == 50)

    print("[7] translator: agent.completed → chat.run.completed")
    ev = GenericStreamEvent(event_type="agent.completed", session_id="r1", data={"rounds": 3})
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("1 frame", len(frames) == 1)
    if frames:
        check("event=chat.run.completed", frames[0]["event"] == "chat.run.completed")

    print("[8] translator: error → chat.error")
    ev = GenericStreamEvent(event_type="error", session_id="r1", data={"category": "rate_limit", "message": "429"})
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("1 frame", len(frames) == 1)
    if frames:
        check("event=chat.error", frames[0]["event"] == "chat.error")
        payload = parse_sse_payload(frames[0]["data"])
        check("category=rate_limit", payload.get("category") == "rate_limit")

    print("[9] translator: round.* (orchestrator internal) → no frame")
    ev = GenericStreamEvent(event_type="round.started", session_id="r1", data={"round": 0})
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("0 frames", len(frames) == 0, f"n={len(frames)}")

    print("[10] translator: empty token → no frame")
    ev = GenericStreamEvent(event_type="token.generated", session_id="r1", data={"content": ""})
    frames = _translate_orchestrator_event(ev, "thread-1", None)
    check("0 frames", len(frames) == 0)

    print("[11] stream_thread_events: thread not found → chat.error and exit")
    sink = EventSourceSink()
    gen = stream_thread_events(thread_id="nope", event_sink=sink, db=db)
    frames = await _consume(gen, n=5, timeout=1.0)
    check("1 frame", len(frames) == 1, f"n={len(frames)}")
    if frames:
        check("event=chat.error", frames[0]["event"] == "chat.error")
        payload = parse_sse_payload(frames[0]["data"])
        check("category=not_found", payload.get("category") == "not_found")

    print("[12] stream_thread_events: thread with no run_id → chat.error")
    thread_id_no_run = await _make_thread(db, run_id=None)
    gen = stream_thread_events(thread_id=thread_id_no_run, event_sink=sink, db=db)
    frames = await _consume(gen, n=5, timeout=1.0)
    check("1 frame", len(frames) == 1)
    if frames:
        check("event=chat.error", frames[0]["event"] == "chat.error")
        payload = parse_sse_payload(frames[0]["data"])
        check("category=no_run", payload.get("category") == "no_run")

    print("[13] stream_thread_events: live events with run_id → chat.* frames")
    run_id_live = f"smoke-stream-{uuid.uuid4().hex[:8]}"
    thread_id_live = await _make_thread(db, run_id=run_id_live)
    sink2 = EventSourceSink()
    gen = stream_thread_events(thread_id=thread_id_live, event_sink=sink2, db=db)
    connected = await gen.__anext__()
    check("first=connected", connected["event"] == "connected")
    check("thread_id in payload", parse_sse_payload(connected["data"]).get("thread_id") == thread_id_live)
    sink2.emit(GenericStreamEvent(event_type="agent.started", session_id=run_id_live, data={"input": "hi"}))
    started = await gen.__anext__()
    check("second=chat.run.started", started["event"] == "chat.run.started")
    sink2.emit(GenericStreamEvent(event_type="token.generated", session_id=run_id_live, data={"content": "hello"}))
    msg_start = await gen.__anext__()
    check("third=chat.message.start", msg_start["event"] == "chat.message.start")
    token = await gen.__anext__()
    check("fourth=chat.token", token["event"] == "chat.token")
    check("delta=hello", parse_sse_payload(token["data"]).get("delta") == "hello")
    sink2.emit(GenericStreamEvent(event_type="agent.completed", session_id=run_id_live, data={"rounds": 1}))
    completed = await gen.__anext__()
    check("fifth=chat.run.completed", completed["event"] == "chat.run.completed")
    try:
        extra = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
        check("stream ends after run.completed", False, f"got extra={extra!r}")
    except (StopAsyncIteration, asyncio.TimeoutError):
        check("stream ends after run.completed", True)

    await db.disconnect()
    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL STREAM THREAD EVENTS SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
