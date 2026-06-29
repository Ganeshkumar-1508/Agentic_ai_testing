"""End-to-end smoke: chat SSE chat.run.* events when the orchestrator runs.

This test does NOT exercise the LLM. It exercises the GET SSE
bridge: creates a chat thread 1:1 with a run, emits synthetic
orchestrator events via the EventSourceSink, and verifies the
chat stream yields the right chat.* frames.

Verifies the 4 chat write tools (submit_job, cancel_job, pause_job,
resume_job) are wired and the chat thread infrastructure
round-trips with the orchestrator's events.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from harness.events import EventSourceSink
from harness.api.state import GenericStreamEvent


async def run() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    from harness.memory.database import Database
    from harness.memory.db_context import set_db
    from harness.tools.chat_read_tools import set_chat_db
    from harness.chat.threads import (
        create_thread, get_thread_by_run_id, get_messages, append_message,
    )
    from harness.chat.sse import stream_thread_events

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    db = Database(url)
    await db.connect()
    set_db(db)
    set_chat_db(db)

    print("[1] create thread 1:1 with a run")
    run_id = f"e2e-{uuid.uuid4().hex[:8]}"
    thread = await create_thread(source="run", run_id=run_id, title="e2e test", db=db)
    check("thread created", thread is not None)
    check("thread.run_id matches", thread.run_id == run_id)
    await append_message(thread_id=thread.id, role="user", content="start e2e", db=db)
    fetched = await get_thread_by_run_id(run_id, db=db)
    check("lookup by run_id", fetched is not None and fetched.id == thread.id)
    msgs = await get_messages(thread.id, db=db)
    check("seed message", len(msgs) == 1 and msgs[0].role == "user")

    print("[2] GET SSE bridge — agent.started → token.generated → tool.completed → agent.completed")
    sink = EventSourceSink()
    gen = stream_thread_events(thread_id=thread.id, event_sink=sink, db=db)
    connected = await gen.__anext__()
    check("first=connected", connected["event"] == "connected")
    sink.emit(GenericStreamEvent(event_type="agent.started", session_id=run_id, data={"input": "hi"}))
    started = await gen.__anext__()
    check("chat.run.started", started["event"] == "chat.run.started")
    sink.emit(GenericStreamEvent(event_type="token.generated", session_id=run_id, data={"content": "Hi "}))
    msg_start = await gen.__anext__()
    check("chat.message.start", msg_start["event"] == "chat.message.start")
    token1 = await gen.__anext__()
    check("chat.token (1)", token1["event"] == "chat.token")
    check("delta=Hi ", '"Hi "' in token1["data"])
    sink.emit(GenericStreamEvent(event_type="token.generated", session_id=run_id, data={"content": "there!"}))
    token2 = await gen.__anext__()
    check("chat.token (2)", token2["event"] == "chat.token")
    sink.emit(GenericStreamEvent(
        event_type="tool.started", session_id=run_id,
        data={"tool_name": "list_runs", "tool_input": "{}", "trace_id": "tc-1"},
    ))
    tool_start = await gen.__anext__()
    check("chat.tool.started", tool_start["event"] == "chat.tool.started")
    sink.emit(GenericStreamEvent(
        event_type="tool.completed", session_id=run_id,
        data={"tool_name": "list_runs", "is_error": False, "output_preview": "[]", "trace_id": "tc-1"},
    ))
    tool_done = await gen.__anext__()
    check("chat.tool.completed", tool_done["event"] == "chat.tool.completed")
    sink.emit(GenericStreamEvent(event_type="agent.completed", session_id=run_id, data={"rounds": 1}))
    done = await gen.__anext__()
    check("chat.run.completed", done["event"] == "chat.run.completed")
    try:
        extra = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
        check("stream ends after run.completed", False, f"got extra={extra!r}")
    except (StopAsyncIteration, asyncio.TimeoutError):
        check("stream ends after run.completed", True)

    print("[3] verify chat_thread_messages GET (used by /api/chat/threads/{id}/messages)")
    msgs_after = await get_messages(thread.id, db=db)
    check("messages persisted", len(msgs_after) == 1, f"n={len(msgs_after)}")

    print("[4] create_thread always inserts — idempotency lives in submitter")
    from harness.jobs.spec import JobSpec
    from harness.jobs.submitter import _auto_create_thread_for_spec
    spec = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id=run_id,
        source="chat-submission",
        prompt="retry the same run",
    )
    await _auto_create_thread_for_spec(spec)
    # The submitter's _auto_create_thread_for_spec should detect the
    # existing thread and not create a new one.
    all_threads_for_run = await get_thread_by_run_id(run_id, db=db)
    check("submitter no-op on existing", all_threads_for_run.id == thread.id,
          f"got {all_threads_for_run.id!r} != {thread.id!r}")

    print("[5] write tools availability — submit/cancel/pause/resume in toolset")
    from harness.tools.toolsets import CHAT_READONLY_TOOLSET
    for name in ("submit_job", "cancel_job", "pause_job", "resume_job"):
        check(f"{name} in toolset", name in CHAT_READONLY_TOOLSET)
    from harness.agent.tool_dispatch import _JOB_CONTROL_ACTION_BY_NAME
    for name in ("submit_job", "cancel_job", "pause_job", "resume_job"):
        check(f"{name} in dispatch table", name in _JOB_CONTROL_ACTION_BY_NAME)

    await db.disconnect()
    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL CHAT WRITE TOOLS SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
