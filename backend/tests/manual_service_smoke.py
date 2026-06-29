"""Smoke test for harness.chat.service.

Run via:
    docker exec testai-backend bash -c "cd /app && PYTHONPATH=/app python /tmp/manual_service_smoke.py"
"""
from __future__ import annotations

import asyncio
import sys
import uuid


def main() -> int:
    from harness.memory.database import Database
    from harness.memory.db_context import set_db
    from harness.chat.threads import (
        append_message,
        create_thread,
        get_messages,
        get_thread,
        get_thread_by_run_id,
        get_thread_by_session_id,
    )
    from harness.chat.service import (
        ChatEventSink,
        DEFAULT_HISTORY_LIMIT,
        HIGH_SIGNAL_EVENT_TYPES,
        MAX_EVENT_MESSAGE_CHARS,
        auto_create_thread_for_run,
        build_chat_context,
        get_thread_for_session,
        post_assistant_message,
        post_system_message,
        post_tool_result,
        post_user_message,
        register_chat_event_sink,
        _format_event,
    )
    from harness.core.events import (
        ErrorEvent,
        ToolExecutionCompleted,
    )
    from harness.api.state import GenericStreamEvent
    from harness.events import EventBus

    async def run() -> None:
        db = Database()
        await db.connect()
        set_db(db)
        try:
            run_id = f"svc-smoke-{uuid.uuid4().hex[:8]}"
            session_id = f"chat-sess-{uuid.uuid4().hex[:8]}"

            # 1. auto_create_thread_for_run — fresh thread, seeds prompt.
            t = await auto_create_thread_for_run(
                run_id=run_id,
                session_id=session_id,
                prompt="Fix the slice bug in ActiveSupport cache_version",
                repo_url="https://github.com/rails/rails",
            )
            assert t.id and t.run_id == run_id
            assert t.session_id == session_id
            assert t.source == "run"
            assert t.message_count == 1
            msgs = await get_messages(t.id)
            assert len(msgs) == 1
            assert msgs[0].role == "user"
            assert "slice" in (msgs[0].content or "")
            assert t.title.startswith("Fix the slice")
            print(f"  1) auto_create_thread_for_run: id={t.id} title={t.title!r} count={t.message_count}")

            # 2. Idempotency: calling again with the same run_id is a no-op.
            t2 = await auto_create_thread_for_run(
                run_id=run_id,
                session_id=session_id,
                prompt="Different prompt that should NOT be seeded",
            )
            assert t2.id == t.id
            msgs2 = await get_messages(t.id)
            assert len(msgs2) == 1, f"idempotent: {len(msgs2)} messages (expected 1)"
            print("  2) idempotent re-call: same thread, no extra seed")

            # 3. Look up by run_id and session_id.
            t_by_run = await get_thread_by_run_id(run_id)
            t_by_sess = await get_thread_by_session_id(session_id)
            assert t_by_run is not None and t_by_run.id == t.id
            assert t_by_sess is not None and t_by_sess.id == t.id
            print(f"  3) lookups: by_run={t_by_run.id} by_sess={t_by_sess.id}")

            # 4. Post user → assistant → tool result → system.
            await post_user_message(t.id, "Also fix the auth bug.")
            await post_assistant_message(
                t.id, content="Let me look that up.",
                tool_calls=[{"id": "tc_a", "name": "list_recent_sessions", "args": {}}],
                finish_reason="tool_calls",
            )
            await post_tool_result(
                t.id, tool_call_id="tc_a", tool_name="list_recent_sessions", content="2 runs",
            )
            await post_assistant_message(
                t.id, content="You have 2 active runs.", finish_reason="stop",
            )
            t_check = await get_thread(t.id)
            assert t_check.message_count == 5
            print(f"  4) message flow: count={t_check.message_count} (1 seed + 1 user + 1 assist + 1 tool + 1 assist)")

            # 5. System message.
            sys_msg = await post_system_message(
                t.id, "Orchestrator started.", tool_name="agent.started",
            )
            assert sys_msg.role == "system"
            assert sys_msg.tool_name == "agent.started"
            print(f"  5) system msg: id={sys_msg.id} tool_name={sys_msg.tool_name}")

            # 6. build_chat_context — OpenAI-style messages.
            ctx = await build_chat_context(t.id, limit=10)
            assert len(ctx) == 6
            assert ctx[0]["role"] == "user"
            assert ctx[1]["role"] == "user"
            assert ctx[2]["role"] == "assistant" and "tool_calls" in ctx[2]
            assert ctx[3]["role"] == "tool" and ctx[3]["tool_call_id"] == "tc_a"
            assert ctx[4]["role"] == "assistant"
            assert ctx[5]["role"] == "system"
            print(f"  6) build_chat_context: {len(ctx)} messages in OpenAI order")

            # 7. ChatEventSink — high-signal events are mirrored.
            bus = EventBus()
            sink = register_chat_event_sink(bus, db=db)
            # Verify the sink is wired.
            sinks = bus.sinks()
            assert any(isinstance(s, ChatEventSink) for s in sinks)

            # 7a. GenericStreamEvent with board.completed (must be mirrored).
            ev_done = GenericStreamEvent(
                session_id=session_id,
                event_type="board.completed",
                data={"done_count": 5, "total_count": 7},
            )
            await sink._emit(ev_done)
            msgs_after = await get_messages(t.id)
            sys_msgs = [m for m in msgs_after if m.role == "system"]
            assert any("Board completed: 5/7" in (m.content or "") for m in sys_msgs)
            print(f"  7a) sink mirrored board.completed: {[m.content for m in sys_msgs]}")

            # 7b. Per-tool-call event is NOT mirrored.
            before = len(await get_messages(t.id))
            ev_tool = ToolExecutionCompleted(
                tool_name="read_file", output_preview="...", success=True,
                trace_id="t1", agent_id="a1", session_id=session_id,
            )
            await sink._emit(ev_tool)
            after = len(await get_messages(t.id))
            assert before == after, f"tool event should be ignored (was {before}, now {after})"
            print(f"  7b) sink ignored tool.execution.completed (correct)")

            # 7c. GenericStreamEvent with agent.started (high-signal) IS mirrored.
            #    (Note: typed AgentStarted has no session_id field — those
            #     per-LLM-call events are filtered out by the sink's
            #     session_id check, which is the right behavior.)
            ev_start = GenericStreamEvent(
                session_id=session_id,
                event_type="agent.started",
                data={"mode": "chat"},
            )
            await sink._emit(ev_start)
            msgs_after2 = await get_messages(t.id)
            sys_msgs2 = [m for m in msgs_after2 if m.role == "system"]
            assert any("Agent started in chat mode" in (m.content or "") for m in sys_msgs2)
            print(f"  7c) sink mirrored agent.started: {[m.content for m in sys_msgs2[-1:]]}")

            # 7d. ErrorEvent (high-signal) IS mirrored, with category prefix.
            ev_err = ErrorEvent(
                message="rate limit hit", category="rate_limit",
                session_id=session_id, recoverable=True,
            )
            await sink._emit(ev_err)
            msgs_after3 = await get_messages(t.id)
            last_sys = [m for m in msgs_after3 if m.role == "system"][-1]
            assert "[rate_limit]" in (last_sys.content or ""), last_sys.content
            print(f"  7d) sink mirrored error with category: {last_sys.content!r}")

            # 7e. Unknown session_id is a no-op.
            ev_other = GenericStreamEvent(
                session_id="unknown-sess",
                event_type="board.completed",
                data={"done_count": 1, "total_count": 1},
            )
            before = len(await get_messages(t.id))
            await sink._emit(ev_other)
            after = len(await get_messages(t.id))
            assert before == after
            print("  7e) sink ignores unknown session_id (correct)")

            # 7f. _format_event returns "" for unknown wire name with no payload.
            assert _format_event(GenericStreamEvent(), "totally.unknown") == ""
            print("  7f) _format_event: empty string for unknown")

            # 7g. Long payload is truncated to MAX_EVENT_MESSAGE_CHARS.
            long_payload = "x" * (MAX_EVENT_MESSAGE_CHARS + 200)
            ev_long = GenericStreamEvent(
                session_id=session_id,
                event_type="board.task.completed",
                data={"summary": long_payload},
            )
            before_count = len(await get_messages(t.id))
            await sink._emit(ev_long)
            new_msgs = (await get_messages(t.id))[before_count:]
            assert len(new_msgs) == 1
            assert len(new_msgs[0].content or "") <= MAX_EVENT_MESSAGE_CHARS
            print(f"  7g) long payload truncated to {len(new_msgs[0].content or '')} chars (max {MAX_EVENT_MESSAGE_CHARS})")

            # 7h. Idempotency: register again with same db replaces the old sink.
            sink2 = register_chat_event_sink(bus, db=db)
            sinks_after = [s for s in bus.sinks() if isinstance(s, ChatEventSink)]
            assert len(sinks_after) == 1
            assert sinks_after[0] is sink2
            print("  7h) register_chat_event_sink is idempotent")

            # 7i. HIGH_SIGNAL_EVENT_TYPES is the documented whitelist.
            assert "board.completed" in HIGH_SIGNAL_EVENT_TYPES
            assert "tool.execution.completed" not in HIGH_SIGNAL_EVENT_TYPES
            assert "token.generated" not in HIGH_SIGNAL_EVENT_TYPES
            print(f"  7i) HIGH_SIGNAL_EVENT_TYPES: {len(HIGH_SIGNAL_EVENT_TYPES)} entries, tool events excluded")

            # 8. Cleanup.
            await db.execute("DELETE FROM chat_threads WHERE id = $1", t.id)
            print("  8) cleanup OK")

            print("\nALL SERVICE SMOKE TESTS PASSED")
        finally:
            await db.disconnect()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
