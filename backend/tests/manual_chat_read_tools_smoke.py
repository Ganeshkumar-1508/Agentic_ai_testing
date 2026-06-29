"""Smoke test for the 4 chat-read tools."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from harness.chat.threads import append_message, create_thread
from harness.tools.chat_read_tools import (
    GetChatThreadForRunTool,
    GetChatThreadTool,
    ListChatThreadMessagesTool,
    ListChatThreadsTool,
)
from harness.tools.base import ToolResult


async def _setup() -> tuple[str, str, str]:
    from harness.memory.database import Database
    import os
    from harness.tools.chat_read_tools import set_chat_db
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    db = Database(url)
    await db.connect()
    set_chat_db(db)
    run_id = f"smoke-{uuid.uuid4().hex[:8]}"
    other_run_id = f"smoke-{uuid.uuid4().hex[:8]}"
    t = await create_thread(source="user", run_id=run_id, title="smoke thread", db=db)
    await append_message(thread_id=t.id, role="user", content="hi there", db=db)
    await append_message(thread_id=t.id, role="assistant", content="hello!", db=db)
    return run_id, other_run_id, t.id


async def run() -> int:
    run_id, other_run_id, thread_id = await _setup()
    failures = 0

    async def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    async def run_tool(tool, **kw) -> ToolResult:
        return await tool.run(**kw)

    list_t = ListChatThreadsTool()
    get_t = GetChatThreadTool()
    list_m = ListChatThreadMessagesTool()
    get_run = GetChatThreadForRunTool()

    print("[1] list_chat_threads — unfiltered")
    r = await run_tool(list_t, limit=5)
    await check("success", r.success, f"out[:80]={r.output[:80]!r}")
    await check("has data", r.data is not None and "threads" in (r.data or {}))
    await check("data type", isinstance(r.data.get("threads"), list))

    print("[2] list_chat_threads — filter by run_id")
    r = await run_tool(list_t, run_id=run_id)
    await check("found 1", r.success and r.data.get("threads") and len(r.data["threads"]) == 1,
                f"n={len(r.data.get('threads', []))}")

    print("[3] list_chat_threads — filter by unknown run_id")
    r = await run_tool(list_t, run_id="does-not-exist")
    await check("empty", r.success and r.data.get("threads") == [])

    print("[4] get_chat_thread — by thread_id")
    r = await run_tool(get_t, thread_id=thread_id)
    await check("success", r.success, f"out[:80]={r.output[:80]!r}")
    await check("has thread", r.data and r.data.get("thread") and r.data["thread"]["id"] == thread_id)

    print("[5] get_chat_thread — by run_id")
    r = await run_tool(get_t, run_id=run_id)
    await check("success", r.success)
    await check("right thread", r.data.get("thread", {}).get("id") == thread_id)

    print("[6] get_chat_thread — missing arg")
    r = await run_tool(get_t)
    await check("error", not r.success and r.error == "missing_arg")

    print("[7] get_chat_thread — not found")
    r = await run_tool(get_t, thread_id="nonexistent")
    await check("error", not r.success and r.error == "not_found")

    print("[8] list_chat_thread_messages")
    r = await run_tool(list_m, thread_id=thread_id)
    await check("success", r.success, f"out[:120]={r.output[:120]!r}")
    await check("has 2 messages", r.data and len(r.data.get("messages", [])) == 2)
    await check("first is user", r.data["messages"][0]["role"] == "user")
    await check("second is assistant", r.data["messages"][1]["role"] == "assistant")

    print("[9] list_chat_thread_messages — no tool results")
    r = await run_tool(list_m, thread_id=thread_id, include_tool_results=False)
    await check("still 2 messages", len(r.data["messages"]) == 2)

    print("[10] list_chat_thread_messages — unknown thread")
    r = await run_tool(list_m, thread_id="nope")
    await check("empty success", r.success and r.data.get("messages") == [])

    print("[11] get_chat_thread_for_run — known run")
    r = await run_tool(get_run, run_id=run_id)
    await check("success", r.success, f"out[:120]={r.output[:120]!r}")
    await check("right thread", r.data.get("thread", {}).get("id") == thread_id)

    print("[12] get_chat_thread_for_run — unknown run")
    r = await run_tool(get_run, run_id=other_run_id)
    await check("success with null thread", r.success and r.data.get("thread") is None)

    print("[13] get_chat_thread_for_run — missing arg")
    r = await run_tool(get_run)
    await check("error", not r.success and r.error == "missing_arg")

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL CHAT READ TOOL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
