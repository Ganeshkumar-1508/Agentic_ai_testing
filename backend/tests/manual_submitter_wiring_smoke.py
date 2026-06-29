"""Smoke test: submit_job_to_orchestrator auto-creates chat thread 1:1 with run.

Verifies the wiring point: when a JobSpec is submitted, a
``chat_threads`` row is created with the spec's ``run_id`` and
seeded with the user prompt. Idempotent: a second submission
with the same run_id returns the existing thread without
duplicating the user message.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from harness.jobs.spec import JobSpec
from harness.jobs.submitter import _auto_create_thread_for_spec


async def _setup_db():
    from harness.memory.database import Database
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    db = Database(url)
    await db.connect()
    return db


async def run() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    db = await _setup_db()
    from harness.memory.db_context import set_db
    set_db(db)

    from harness.chat.threads import get_messages, get_thread_by_run_id

    print("[1] fresh spec — auto-create thread")
    run_id_1 = f"submit-smoke-{uuid.uuid4().hex[:8]}"
    spec_1 = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id=run_id_1,
        source="chat-submission",
        prompt="please write tests for the login flow",
        repo_url="https://github.com/example/app",
        branch="main",
    )
    await _auto_create_thread_for_spec(spec_1)
    thread_1 = await get_thread_by_run_id(run_id_1, db=db)
    check("thread exists", thread_1 is not None)
    if thread_1:
        check("title auto-built", "login flow" in (thread_1.title or "").lower() or "tests" in (thread_1.title or "").lower(),
              f"title={thread_1.title!r}")
        check("source=run", thread_1.source == "run", f"source={thread_1.source!r}")
        check("run_id matches", thread_1.run_id == run_id_1)
        msgs = await get_messages(thread_1.id, db=db)
        check("1 user message seeded", len(msgs) == 1, f"n={len(msgs)}")
        if msgs:
            check("role=user", msgs[0].role == "user")
            check("content matches prompt", "login flow" in (msgs[0].content or ""))

    print("[2] idempotent — same run_id returns existing thread")
    before_id = thread_1.id if thread_1 else None
    await _auto_create_thread_for_spec(spec_1)
    thread_1_again = await get_thread_by_run_id(run_id_1, db=db)
    check("same thread", thread_1_again is not None and thread_1_again.id == before_id)
    msgs_again = await get_messages(before_id, db=db)
    check("still 1 user message (no duplicate)", len(msgs_again) == 1, f"n={len(msgs_again)}")

    print("[3] second spec — different run_id creates new thread")
    run_id_2 = f"submit-smoke-{uuid.uuid4().hex[:8]}"
    spec_2 = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id=run_id_2,
        source="chat-submission",
        prompt="summarize the repo",
        repo_url="https://github.com/example/repo",
    )
    await _auto_create_thread_for_spec(spec_2)
    thread_2 = await get_thread_by_run_id(run_id_2, db=db)
    check("thread 2 exists", thread_2 is not None)
    if thread_1 and thread_2:
        check("different threads", thread_1.id != thread_2.id)
    msgs_2 = await get_messages(thread_2.id, db=db) if thread_2 else []
    check("thread 2 has 1 msg", len(msgs_2) == 1)

    print("[4] session_id from typed JobContext is wired through")
    from harness.jobs.spec import _build_context
    run_id_3 = f"submit-smoke-{uuid.uuid4().hex[:8]}"
    spec_3 = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id=run_id_3,
        source="chat-submission",
        prompt="test 3",
        context=_build_context(session_id="sess-abc-123"),
    )
    await _auto_create_thread_for_spec(spec_3)
    thread_3 = await get_thread_by_run_id(run_id_3, db=db)
    check("thread 3 exists", thread_3 is not None)
    if thread_3:
        check("session_id wired", thread_3.session_id == "sess-abc-123", f"actual={thread_3.session_id!r}")

    print("[5] session_id from dict context is wired through")
    run_id_4 = f"submit-smoke-{uuid.uuid4().hex[:8]}"
    spec_4 = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id=run_id_4,
        source="chat-submission",
        prompt="test 4",
        context={"session_id": "sess-dict-456"},
    )
    await _auto_create_thread_for_spec(spec_4)
    thread_4 = await get_thread_by_run_id(run_id_4, db=db)
    check("thread 4 exists", thread_4 is not None)
    if thread_4:
        check("session_id from dict", thread_4.session_id == "sess-dict-456")

    print("[6] no run_id — silently skipped (no thread, no error)")
    spec_5 = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id="",
        source="chat-submission",
        prompt="ignored",
    )
    await _auto_create_thread_for_spec(spec_5)
    check("no exception raised", True)

    print("[7] empty prompt — thread created, no user message seeded")
    run_id_6 = f"submit-smoke-{uuid.uuid4().hex[:8]}"
    spec_6 = JobSpec(
        spec_id=str(uuid.uuid4()),
        run_id=run_id_6,
        source="chat-submission",
        prompt="",
    )
    await _auto_create_thread_for_spec(spec_6)
    thread_6 = await get_thread_by_run_id(run_id_6, db=db)
    check("thread 6 exists", thread_6 is not None)
    msgs_6 = await get_messages(thread_6.id, db=db) if thread_6 else []
    check("0 messages (empty prompt)", len(msgs_6) == 0, f"n={len(msgs_6)}")

    await db.disconnect()
    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL SUBMITTER WIRING SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
