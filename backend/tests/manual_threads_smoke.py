"""Smoke test for harness.chat.threads against the live testai-db.

Run via:
    docker exec testai-backend python -c "import sys; sys.path.insert(0, '/tmp'); import test_threads_smoke; import asyncio; asyncio.run(test_threads_smoke.main())"

Or pipe via stdin:
    cat backend/tests/manual_threads_smoke.py | docker exec -i testai-backend python
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
        archive_thread,
        count_messages,
        count_threads,
        create_thread,
        get_message,
        get_messages,
        get_thread,
        get_thread_by_run_id,
        list_threads,
        new_thread_id,
        set_thread_pinned,
        unarchive_thread,
        update_thread_title,
        _truncate_title,
    )

    async def run() -> None:
        db = Database()
        await db.connect()
        set_db(db)
        try:
            # 1. Create ad-hoc thread with DEFAULT title (so auto-title can fire).
            ad_hoc_id = new_thread_id()
            t1 = await create_thread(
                source="user",  # default title "New conversation"
                thread_id=ad_hoc_id,
            )
            assert t1.id == ad_hoc_id, (t1.id, ad_hoc_id)
            assert t1.title == "New conversation"
            assert t1.source == "user"
            assert t1.run_id is None
            assert t1.message_count == 0
            assert t1.is_pinned is False
            assert t1.is_archived is False
            print(f"  1) create ad-hoc (default title): id={t1.id} title={t1.title!r} count={t1.message_count}")

            # 2. Create run-scoped thread.
            run_id = f"smoke-test-{uuid.uuid4().hex[:8]}"
            t2 = await create_thread(
                title="Run-scoped test thread",
                run_id=run_id,
                source="run",
            )
            assert t2.run_id == run_id
            assert t2.source == "run"
            print(f"  2) create run-scoped: id={t2.id} run_id={t2.run_id}")

            # 3. Append user message → auto-title fires (default title).
            m1 = await append_message(
                thread_id=t1.id,
                role="user",
                content="Fix the slice bug in ActiveSupport cache_version",
            )
            assert m1.role == "user"
            assert m1.content and "slice" in m1.content
            t1_after = await get_thread(t1.id)
            assert t1_after.message_count == 1
            assert t1_after.title.startswith("Fix the slice bug"), t1_after.title
            assert t1_after.last_message_at is not None
            print(f"  3) user msg + auto-title: count={t1_after.message_count} title={t1_after.title!r}")

            # 3b. Custom title is RESPECTED (no auto-title overwrite).
            custom_id = new_thread_id()
            t_custom = await create_thread(
                title="My pinned thread",
                source="user",
                thread_id=custom_id,
            )
            await append_message(
                thread_id=t_custom.id, role="user",
                content="This is a follow-up about the cookie banner.",
            )
            t_custom_after = await get_thread(t_custom.id)
            assert t_custom_after.title == "My pinned thread", t_custom_after.title
            print(f"  3b) custom title preserved: {t_custom_after.title!r}")

            # 4. Append assistant + tool_calls.
            m2 = await append_message(
                thread_id=t1.id,
                role="assistant",
                content="Let me look that up.",
                tool_calls=[{"id": "tc_001", "name": "list_recent_sessions", "args": {"limit": 5}}],
                finish_reason="tool_calls",
                prompt_tokens=12,
                completion_tokens=4,
                cost_usd=0.0001,
            )
            assert m2.role == "assistant"
            assert m2.tool_calls and m2.tool_calls[0]["name"] == "list_recent_sessions"
            assert m2.finish_reason == "tool_calls"
            print(f"  4) assistant msg w/ tool_calls: tool_name={m2.tool_calls[0]['name']}")

            # 5. Append tool result.
            m3 = await append_message(
                thread_id=t1.id,
                role="tool",
                tool_call_id="tc_001",
                tool_name="list_recent_sessions",
                content="5 sessions found",
            )
            assert m3.role == "tool"
            assert m3.tool_call_id == "tc_001"
            print(f"  5) tool result: tool_call_id={m3.tool_call_id}")

            t1_after = await get_thread(t1.id)
            assert t1_after.message_count == 3
            print(f"  6) thread counters after 3 appends: count={t1_after.message_count}")

            # 7. get_messages returns in order.
            msgs = await get_messages(t1.id)
            assert len(msgs) == 3
            assert msgs[0].role == "user"
            assert msgs[1].role == "assistant"
            assert msgs[2].role == "tool"
            print(f"  7) get_messages: 3 in order, last={msgs[-1].role}")

            # 8. get_messages with after_id (replay).
            msgs_after = await get_messages(t1.id, after_id=m1.id)
            assert len(msgs_after) == 2
            assert msgs_after[0].role == "assistant"
            print(f"  8) get_messages(after_id): 2 returned")

            # 9. update_thread_title — manual rename is respected.
            await update_thread_title(t1.id, "My custom title")
            # 10. Append another user msg — should NOT overwrite the custom title.
            m4 = await append_message(
                thread_id=t1.id, role="user", content="This is a follow-up.",
            )
            t1_after = await get_thread(t1.id)
            assert t1_after.title == "My custom title", t1_after.title
            print(f" 10) custom title preserved: {t1_after.title!r}")

            # 11. set_thread_pinned + list_threads sorts pinned first.
            await set_thread_pinned(t2.id, True)
            all_t = await list_threads(limit=50, include_archived=True, only_pinned=False)
            pinned = [t for t in all_t if t.is_pinned]
            assert t2.id in {t.id for t in pinned}
            print(f" 11) pinned: {len(pinned)} threads, t2 included")

            # 12. archive_thread + list_threads(include_archived=False) excludes it.
            await archive_thread(t2.id)
            all_visible = await list_threads(limit=200, include_archived=False)
            all_with_archived = await list_threads(limit=200, include_archived=True)
            assert t2.id not in {t.id for t in all_visible}
            assert t2.id in {t.id for t in all_with_archived}
            print(f" 12) archive hides from default list: visible={len(all_visible)} total={len(all_with_archived)}")

            # 13. unarchive_thread restores.
            await unarchive_thread(t2.id)
            t2_after = await get_thread(t2.id)
            assert t2_after is not None and t2_after.is_archived is False
            print(" 13) unarchive restores")

            # 14. get_thread_by_run_id.
            found = await get_thread_by_run_id(run_id)
            assert found is not None and found.id == t2.id
            print(f" 14) get_thread_by_run_id: found {found.id}")

            # 15. count_threads.
            n = await count_threads(include_archived=True)
            assert n >= 2
            print(f" 15) count_threads(include_archived): {n}")

            # 16. count_messages.
            n_msg = await count_messages(t1.id)
            assert n_msg == 4
            print(f" 16) count_messages: {n_msg}")

            # 17. get_message by id.
            m = await get_message(m2.id)
            assert m is not None and m.id == m2.id
            print(f" 17) get_message: {m.id}")

            # 18. _truncate_title edge cases.
            assert _truncate_title("") == "New conversation"
            assert _truncate_title("short") == "short"
            assert _truncate_title("a" * 80) == "a" * 80
            assert _truncate_title("a" * 200).endswith("...")
            assert _truncate_title("hello\nworld") == "hello world"
            print(" 18) _truncate_title: all edge cases pass")

            # 19. Validation: bad source / bad role / bad finish_reason.
            try:
                await create_thread(source="invalid", thread_id=new_thread_id())
            except ValueError as e:
                print(f" 19a) bad source rejected: {e!r}")
            try:
                await append_message(thread_id=t1.id, role="invalid", content="x")
            except ValueError as e:
                print(f" 19b) bad role rejected: {e!r}")
            try:
                await append_message(thread_id=t1.id, role="assistant", finish_reason="invalid")
            except ValueError as e:
                print(f" 19c) bad finish_reason rejected: {e!r}")

            # 20. Cleanup: delete all 3 threads.
            await db.execute(
                "DELETE FROM chat_threads WHERE id = ANY($1)",
                [t1.id, t2.id, t_custom.id],
            )
            print(" 20) cleanup OK")

            print("\nALL SMOKE TESTS PASSED")
        finally:
            await db.disconnect()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
