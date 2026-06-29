"""Smoke test for harness.chat.sse — synthetic agent, no LLM.

The real `agent.run_stream` is async + LLM-bound. For unit
testing the SSE wire shape, we build a synthetic agent that
yields a known sequence of StreamEvent instances. This
validates the translation layer + persistence side-effects
without paying the LLM cost.

Run via:
    docker exec testai-backend bash -c "cd /app && PYTHONPATH=/app python /tmp/manual_sse_smoke.py"
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from typing import Any, AsyncIterator


def _synth_agent(events: list[Any]) -> Any:
    """Build a fake Agent whose ``run_stream`` yields the given events.

    Only the methods called by :class:`StreamChatResponse` are
    stubbed: ``run_stream`` (the generator) and ``model_override`` /
    ``mode`` attribute reads.
    """

    class _SynthAgent:
        model_override = "test-model"
        mode = "chat"
        max_tool_rounds = 5

        async def run_stream(self, user_input: str) -> AsyncIterator[Any]:
            for ev in events:
                yield ev

    return _SynthAgent()


def main() -> int:
    from harness.chat.threads import (
        ChatMessage,
        get_messages,
        get_thread,
    )
    from harness.chat.sse import (
        EVENT_CONNECTED,
        EVENT_ERROR,
        EVENT_MESSAGE_END,
        EVENT_MESSAGE_START,
        EVENT_RUN_CANCELLED,
        EVENT_RUN_COMPLETED,
        EVENT_RUN_STARTED,
        EVENT_TOKEN,
        EVENT_TOOL_COMPLETED,
        EVENT_TOOL_STARTED,
        StreamChatResponse,
        stream_chat_response,
        replay_thread_messages,
        _frame,
    )
    from harness.memory.database import Database
    from harness.memory.db_context import set_db
    from harness.core.events import (
        AgentCompleted,
        AgentStarted,
        ErrorEvent,
        LLMCallCompleted,
        TokenGenerated,
        ToolExecutionCompleted,
        ToolExecutionStarted,
    )
    from harness.api.state import GenericStreamEvent

    async def collect(sse: StreamChatResponse) -> list[dict[str, str]]:
        frames: list[dict[str, str]] = []
        async for f in sse.stream():
            frames.append(f)
        return frames

    async def collect_gen(gen) -> list[dict[str, str]]:
        frames: list[dict[str, str]] = []
        async for f in gen:
            frames.append(f)
        return frames

    async def run() -> None:
        db = Database()
        await db.connect()
        set_db(db)
        try:
            thread_id = f"sse-smoke-{uuid.uuid4().hex[:8]}"
            from harness.chat.threads import create_thread
            t = await create_thread(source="user", thread_id=thread_id)
            assert t.id == thread_id

            # ============================================================
            # Test 1: happy path — AgentStarted + 3 tokens + AgentCompleted.
            # ============================================================
            happy_events: list[Any] = [
                AgentStarted(agent_id="a1", input="hi", model="test", mode="chat"),
                TokenGenerated(agent_id="a1", content="Hello, ", session_id=""),
                TokenGenerated(agent_id="a1", content="how are ", session_id=""),
                TokenGenerated(agent_id="a1", content="you?", session_id=""),
                AgentCompleted(agent_id="a1", output_preview="done", rounds=0),
            ]
            agent = _synth_agent(happy_events)
            sse = StreamChatResponse(
                thread_id=thread_id, user_content="hi",
                agent=agent, db=db,
            )
            frames = await collect(sse)
            events_seen = [f["event"] for f in frames]
            assert events_seen[0] == EVENT_CONNECTED, events_seen
            assert EVENT_RUN_STARTED in events_seen
            # 3 chat.token frames
            token_count = events_seen.count(EVENT_TOKEN)
            assert token_count == 3, f"expected 3 tokens, got {token_count}: {events_seen}"
            # chat.message.start and chat.message.end (one each)
            assert events_seen.count(EVENT_MESSAGE_START) == 1
            assert events_seen.count(EVENT_MESSAGE_END) == 1
            # terminal
            assert events_seen[-1] == EVENT_RUN_COMPLETED
            print(f"  1) happy path: {len(frames)} frames, events: {events_seen}")

            # Verify persistence: 1 user (from the stream) + 1 assistant.
            t_after = await get_thread(thread_id, db=db)
            assert t_after.message_count == 2, t_after.message_count
            msgs = await get_messages(thread_id, db=db)
            assert msgs[0].role == "user" and msgs[0].content == "hi"
            assert msgs[1].role == "assistant" and msgs[1].content == "Hello, how are you?"
            assert msgs[1].finish_reason == "stop"
            print(f"  2) persistence: 2 messages, assistant='{msgs[1].content}'")

            # ============================================================
            # Test 2: tool call path — AgentStarted + tool + tool result + AgentCompleted.
            # ============================================================
            thread_id_2 = f"sse-smoke-{uuid.uuid4().hex[:8]}"
            t2 = await create_thread(source="user", thread_id=thread_id_2)
            tool_events: list[Any] = [
                AgentStarted(agent_id="a2", input="do thing", model="t", mode="chat"),
                ToolExecutionStarted(
                    tool_name="list_recent_sessions",
                    tool_input='{"limit": 5}', trace_id="tc1",
                    agent_id="a2", session_id="",
                ),
                ToolExecutionCompleted(
                    tool_name="list_recent_sessions",
                    output_preview="3 sessions found", success=True,
                    trace_id="tc1", agent_id="a2", session_id="",
                ),
                LLMCallCompleted(call_id="llm1", model="t", round=0,
                                 prompt_tokens=10, completion_tokens=4,
                                 total_tokens=14, session_id=""),
                AgentCompleted(agent_id="a2", output_preview="done", rounds=1),
            ]
            agent2 = _synth_agent(tool_events)
            sse2 = StreamChatResponse(
                thread_id=thread_id_2, user_content="do thing",
                agent=agent2, db=db,
            )
            frames2 = await collect(sse2)
            events2 = [f["event"] for f in frames2]
            assert EVENT_TOOL_STARTED in events2
            assert EVENT_TOOL_COMPLETED in events2
            assert events2[-1] == EVENT_RUN_COMPLETED
            # finish_reason should be tool_calls (because tool calls happened)
            msg_end = [f for f in frames2 if f["event"] == EVENT_MESSAGE_END][0]
            data = json.loads(msg_end["data"])
            assert data["finish_reason"] == "tool_calls", data
            assert data["prompt_tokens"] == 10
            assert data["completion_tokens"] == 4
            print(f"  3) tool path: tool_started + tool_completed; finish_reason={data['finish_reason']}, tokens=({data['prompt_tokens']},{data['completion_tokens']})")

            # Verify tool_call was accumulated into the assistant message.
            msgs2 = await get_messages(thread_id_2, db=db)
            assistant = [m for m in msgs2 if m.role == "assistant"][0]
            assert assistant.tool_calls and len(assistant.tool_calls) == 1
            assert assistant.tool_calls[0]["name"] == "list_recent_sessions"
            # Tool result row persisted.
            tool_msgs = [m for m in msgs2 if m.role == "tool"]
            assert len(tool_msgs) == 1
            assert tool_msgs[0].tool_call_id == "tc1"
            assert "3 sessions" in (tool_msgs[0].content or "")
            print(f"  4) tool persistence: assistant.tool_calls={len(assistant.tool_calls)}, tool_msgs={len(tool_msgs)}")

            # ============================================================
            # Test 3: error path — AgentStarted + ErrorEvent.
            # ============================================================
            thread_id_3 = f"sse-smoke-{uuid.uuid4().hex[:8]}"
            t3 = await create_thread(source="user", thread_id=thread_id_3)
            error_events: list[Any] = [
                AgentStarted(agent_id="a3", input="x", model="t", mode="chat"),
                ErrorEvent(message="rate limit hit", category="rate_limit",
                           session_id="", recoverable=True),
            ]
            agent3 = _synth_agent(error_events)
            sse3 = StreamChatResponse(
                thread_id=thread_id_3, user_content="x",
                agent=agent3, db=db,
            )
            frames3 = await collect(sse3)
            events3 = [f["event"] for f in frames3]
            assert EVENT_ERROR in events3
            assert events3[-1] == EVENT_RUN_COMPLETED
            err_frame = [f for f in frames3 if f["event"] == EVENT_ERROR][0]
            err_data = json.loads(err_frame["data"])
            assert err_data["category"] == "rate_limit", err_data
            assert "rate limit" in err_data["message"]
            print(f"  5) error path: chat.error category={err_data['category']!r}")

            # Partial text persistence: the assistant message should be
            # posted even on error (we want the user to see what was
            # emitted before the failure).
            msgs3 = await get_messages(thread_id_3, db=db)
            assistant_msgs = [m for m in msgs3 if m.role == "assistant"]
            assert len(assistant_msgs) == 1
            assert assistant_msgs[0].is_error
            print(f"  6) error persistence: 1 assistant msg (is_error=True)")

            # ============================================================
            # Test 4: cancellation — disconnect predicate fires mid-stream.
            # ============================================================
            thread_id_4 = f"sse-smoke-{uuid.uuid4().hex[:8]}"
            t4 = await create_thread(source="user", thread_id=thread_id_4)
            cancel_events: list[Any] = [
                AgentStarted(agent_id="a4", input="x", model="t", mode="chat"),
                TokenGenerated(agent_id="a4", content="part one ", session_id=""),
                TokenGenerated(agent_id="a4", content="part two ", session_id=""),
            ]
            agent4 = _synth_agent(cancel_events)
            disconnect_state = {"disconnected": False}
            async def is_disc() -> bool:
                return disconnect_state["disconnected"]
            sse4 = StreamChatResponse(
                thread_id=thread_id_4, user_content="x",
                agent=agent4, is_disconnected=is_disc, db=db,
            )
            # Hook the cancel after the first frame so we hit the
            # disconnect check between events.
            disconnect_state["disconnected"] = True
            frames4 = await collect(sse4)
            events4 = [f["event"] for f in frames4]
            assert EVENT_RUN_CANCELLED in events4, f"expected EVENT_RUN_CANCELLED, got: {events4}"
            print(f"  7) cancellation: chat.run.cancelled yielded (events: {events4})")

            # ============================================================
            # Test 5: timeout — max_run_seconds fires.
            # ============================================================
            thread_id_5 = f"sse-smoke-{uuid.uuid4().hex[:8]}"
            t5 = await create_thread(source="user", thread_id=thread_id_5)

            async def slow_events() -> AsyncIterator[Any]:
                yield AgentStarted(agent_id="a5", input="x", model="t", mode="chat")
                while True:
                    await asyncio.sleep(0.5)
                    yield TokenGenerated(agent_id="a5", content=".", session_id="")

            class _SlowAgent:
                model_override = "t"
                mode = "chat"
                max_tool_rounds = 5
                async def run_stream(self, user_input: str) -> AsyncIterator[Any]:
                    async for ev in slow_events():
                        yield ev

            sse5 = StreamChatResponse(
                thread_id=thread_id_5, user_content="x",
                agent=_SlowAgent(), db=db, max_run_seconds=1.0,
            )
            frames5 = await collect(sse5)
            events5 = [f["event"] for f in frames5]
            # Should have an error frame for max_tokens.
            err_frames = [f for f in frames5 if f["event"] == EVENT_ERROR]
            assert len(err_frames) >= 1, events5
            err_data = json.loads(err_frames[0]["data"])
            assert err_data["category"] == "max_tokens", err_data
            print(f"  8) timeout: chat.error category={err_data['category']!r}, ran in ~1s")

            # ============================================================
            # Test 6: replay_thread_messages — reconstruct SSE from
            # persisted chat_messages.
            # ============================================================
            # Use the thread from test 1 (has 1 user + 1 assistant).
            replay_frames = await collect_gen(replay_thread_messages(
                thread_id=thread_id, db=db,
            ))
            replay_events = [f["event"] for f in replay_frames]
            assert replay_events[0] == EVENT_CONNECTED
            # The happy path thread has 1 user + 1 assistant; the
            # replay should emit 1 chat.message.start, 1 chat.token,
            # 1 chat.message.end, 1 chat.run.completed.
            assert replay_events.count(EVENT_MESSAGE_START) == 1
            assert replay_events.count(EVENT_TOKEN) == 1
            assert replay_events.count(EVENT_MESSAGE_END) == 1
            assert replay_events[-1] == EVENT_RUN_COMPLETED
            print(f"  9) replay: {len(replay_frames)} frames, events: {replay_events}")

            # ============================================================
            # Test 7: replay with after_message_id — partial replay.
            # ============================================================
            all_msgs = await get_messages(thread_id, db=db)
            assistant_id = [m for m in all_msgs if m.role == "assistant"][0].id
            # The user msg has the earlier created_at; asking for
            # ``after_message_id=<user_id>`` should replay just the
            # assistant.
            partial = await collect_gen(replay_thread_messages(
                thread_id=thread_id, after_message_id=all_msgs[0].id, db=db,
            ))
            partial_events = [f["event"] for f in partial]
            # The user message is excluded; only the assistant plays.
            assert partial_events.count(EVENT_MESSAGE_START) == 1
            print(f" 10) partial replay (after user msg): {partial_events}")

            # ============================================================
            # Test 8: stream_chat_response — the convenience generator.
            # ============================================================
            agent_conv = _synth_agent([
                AgentStarted(agent_id="a6", input="hi", model="t", mode="chat"),
                TokenGenerated(agent_id="a6", content="world", session_id=""),
                AgentCompleted(agent_id="a6", output_preview="done", rounds=0),
            ])
            thread_id_6 = f"sse-smoke-{uuid.uuid4().hex[:8]}"
            t6 = await create_thread(source="user", thread_id=thread_id_6)
            conv_frames = await collect_gen(stream_chat_response(
                thread_id=thread_id_6, user_content="hi",
                agent=agent_conv, db=db,
            ))
            assert [f["event"] for f in conv_frames][0] == EVENT_CONNECTED
            assert [f["event"] for f in conv_frames][-1] == EVENT_RUN_COMPLETED
            print(f" 11) stream_chat_response convenience wrapper: {len(conv_frames)} frames")

            # ============================================================
            # Test 9: frame encoding.
            # ============================================================
            f = _frame("test.event", {"k": 1, "msg": "hi"})
            assert f["event"] == "test.event"
            assert json.loads(f["data"]) == {"k": 1, "msg": "hi"}
            print(" 12) _frame: encodes to {event, data}")

            # ============================================================
            # Cleanup.
            # ============================================================
            for tid in (thread_id, thread_id_2, thread_id_3,
                        thread_id_4, thread_id_5, thread_id_6):
                await db.execute("DELETE FROM chat_threads WHERE id = $1", tid)
            print(" 13) cleanup OK")

            print("\nALL SSE SMOKE TESTS PASSED")
        finally:
            await db.disconnect()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
