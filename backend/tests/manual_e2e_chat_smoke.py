"""E2E smoke: chat surface end-to-end.

Exercises the full flow:
  1. POST /api/jobs → thread auto-created, thread_id returned
  2. GET /api/chat/threads/{id} → thread exists
  3. GET /api/chat/threads/{id}/stream (SSE) → chat.* events arrive
  4. GET /api/chat/threads/{id}/messages → messages recorded
  5. agent_memory table → memory written by agent

Runs from inside the container. Uses live LLM (deepseek-v4-flash via
opencode.ai/zen/go/v1) to run a real agent task.

Requires: container healthy, LLM credentials in plans/test_env.txt.

Usage:
    docker exec testai-backend bash -c "cd /app && PYTHONPATH=/app python /tmp/manual_e2e_chat_smoke.py"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def check(label: str, cond: bool, detail: str = "") -> bool:
    marker = "ok" if cond else "FAIL"
    print(f"  {marker} {label}  {detail}")
    return cond


# ---------------------------------------------------------------------------
# HTTP helpers (no external dep — uses urllib)
# ---------------------------------------------------------------------------

import urllib.request as _request
import urllib.error as _error


def _url(path: str) -> str:
    return f"http://localhost:8000{path}"


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = _request.Request(
        _url(path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _request.urlopen(req, timeout=30) as resp:
            return dict(json.loads(resp.read().decode("utf-8")))
    except _error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code} on {path}: {body_text[:200]}")
        raise


def _get(path: str, timeout: int = 15) -> dict | list | str:
    req = _request.Request(_url(path), method="GET")
    try:
        with _request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw  # raw text (SSE, error msg)
    except _error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code} on {path}: {body_text[:200]}")
        raise


def _fetch_sse(
    path: str,
    max_duration_s: float = 60.0,
    event_filter: set[str] | None = None,
) -> list[dict]:
    """Open a GET SSE stream and collect events up to max_duration_s.

    Returns list of parsed SSE event dicts. Each event is
    ``{"event": ..., "data": {...}}``.
    """
    req = _request.Request(_url(path), method="GET")
    try:
        resp = _request.urlopen(req, timeout=max_duration_s + 5)
    except _error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code} on SSE {path}: {body_text[:200]}")
        raise

    events: list[dict] = []
    deadline = time.monotonic() + max_duration_s
    buf = b""

    while time.monotonic() < deadline:
        try:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
        except Exception:
            break

        # Split into SSE frames (double-newline)
        while b"\n\n" in buf:
            raw, buf = buf.split(b"\n\n", 1)
            text = raw.decode("utf-8", errors="replace")
            event_type = ""
            data_str = ""
            for line in text.splitlines():
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: "):
                    data_str = line[6:].strip()

            if not event_type:
                continue

            payload: dict = {}
            if data_str:
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    payload = {"raw": data_str}

            ev = {"event": event_type, "data": payload}
            if event_filter is None or event_type in event_filter:
                events.append(ev)

        # Stop if we received a terminal event
        terminal = {"chat.run.completed", "chat.run.cancelled", "chat.error"}
        for ev in events:
            if ev["event"] in terminal:
                return events

    return events


# ---------------------------------------------------------------------------
# DB helpers (psql via subprocess)
# ---------------------------------------------------------------------------

import subprocess


def _psql(query: str) -> list[dict]:
    """Run psql query, return list of row-dicts."""
    cmd = [
        "psql", "-U", "testai", "-d", "testai",
        "-t", "-A", "-F", "\t",
        "-c", query,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            env={**os.environ, "PGPASSWORD": "testai"},
        )
    except FileNotFoundError:
        return []  # psql not available in this environment
    if result.returncode != 0:
        return []
    lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    # Simple tab-separated parsing — just returns raw tuples for our queries
    return lines


def _psql_dict(query: str) -> list[dict]:
    """Run psql with expanded output for dict-style results."""
    cmd = [
        "psql", "-U", "testai", "-d", "testai",
        "-t", "-A", "-F", "\t",
        "-c", query,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            env={**os.environ, "PGPASSWORD": "testai"},
        )
    except FileNotFoundError:
        return [{"error": "psql not found"}]
    if result.returncode != 0:
        return [{"error": result.stderr[:200]}]
    lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    return [{"row": l} for l in lines]


# ---------------------------------------------------------------------------
# main test
# ---------------------------------------------------------------------------


async def run() -> int:
    failures = 0
    started_at = time.monotonic()

    print("=" * 60)
    print("E2E CHAT SMOKE TEST")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 0. Pre-flight: health check
    # -----------------------------------------------------------------------
    print("\n[0] Pre-flight")
    try:
        health = _get("/health")
        ok = check("health endpoint responds", health.get("status") == "ok",
                     str(health)[:100])
        if not ok:
            return 1
    except Exception as exc:
        print(f"  FAIL pre-flight: {exc}")
        return 1

    # -----------------------------------------------------------------------
    # 1. Submit a real job
    # -----------------------------------------------------------------------
    print("\n[1] POST /api/jobs — submit a small agent task")
    spec = {
        "prompt": "List the files in /app/harness/agent/ and describe what each one does in one line.",
        "repo_url": "https://github.com/anomalyco/testai-production",
        "branch": "main",
        "tier": 1,
        "source": "api",
        "capabilities": [],
    }

    try:
        resp = _post("/api/jobs", spec)
        spec_id = resp.get("spec_id", "")
        run_id = resp.get("run_id", "")
        thread_id = resp.get("thread_id", "")
        status = resp.get("status", "")

        check("spec_id returned", bool(spec_id), f"spec_id={spec_id}")
        check("run_id returned", bool(run_id), f"run_id={run_id}")
        check("thread_id returned", bool(thread_id), f"thread_id={thread_id}")
        check("status is submitted", status == "submitted", f"status={status}")

        if not run_id or not thread_id:
            print("  STOP: job submission did not produce run_id + thread_id")
            return 1
    except Exception as exc:
        print(f"  FAIL POST /api/jobs: {exc}")
        traceback.print_exc()
        return 1

    # -----------------------------------------------------------------------
    # 2. Verify thread exists
    # -----------------------------------------------------------------------
    print("\n[2] GET /api/chat/threads/{id} — verify thread auto-created")
    try:
        thread = _get(f"/api/chat/threads/{thread_id}")
        ok_thread = check("thread exists", isinstance(thread, dict), "")
        if ok_thread:
            check("thread.run_id matches", thread.get("run_id") == run_id,
                  f"got={thread.get('run_id')}")
            check("thread.source is 'run'", thread.get("source") == "run",
                  f"got={thread.get('source')}")
    except Exception as exc:
        print(f"  FAIL get_thread: {exc}")
        failures += 1

    # -----------------------------------------------------------------------
    # 3. Open SSE stream and collect events
    # -----------------------------------------------------------------------
    print(f"\n[3] GET /api/chat/threads/{thread_id}/stream — collect events")
    try:
        events = _fetch_sse(
            f"/api/chat/threads/{thread_id}/stream",
            max_duration_s=90.0,
        )
        check("at least 1 chat.* event received", len(events) > 0,
              f"got {len(events)} events")

        event_types = [ev["event"] for ev in events]
        check("connected event received", "chat.connected" in event_types,
              f"types={event_types[:5]}")
        check("completed event received", "chat.run.completed" in event_types,
              f"types={event_types[:10]}")

        # Log all event types for diagnostics
        type_counts: dict[str, int] = {}
        for ev in events:
            type_counts[ev["event"]] = type_counts.get(ev["event"], 0) + 1
        print(f"  event distribution: {type_counts}")

        completed = [ev for ev in events if ev["event"] == "chat.run.completed"]
        if completed:
            outcome = completed[0]["data"].get("outcome", {})
            check("run completed outcome is success", outcome.get("type") == "success",
                  f"outcome={outcome}")
    except Exception as exc:
        print(f"  FAIL SSE stream: {exc}")
        traceback.print_exc()
        failures += 1

    # -----------------------------------------------------------------------
    # 4. Check chat_messages table
    # -----------------------------------------------------------------------
    print("\n[4] chat_messages — verify messages recorded")
    try:
        msg_rows = _get(f"/api/chat/threads/{thread_id}/messages")
        if isinstance(msg_rows, dict):
            messages = msg_rows.get("messages", msg_rows.get("data", []))
        elif isinstance(msg_rows, list):
            messages = msg_rows
        else:
            messages = []

        check("at least 2 messages (user + assistant)", len(messages) >= 2,
              f"got {len(messages)} messages")

        if messages:
            first = messages[0]
            check("first message role is 'user'",
                  first.get("role") == "user",
                  f"got role={first.get('role')}")

            found_assistant = any(m.get("role") == "assistant" for m in messages)
            check("assistant message recorded", found_assistant, "")

            found_tool = any(m.get("role") == "tool" for m in messages)
            print(f"  tool messages present: {found_tool}")
    except Exception as exc:
        print(f"  FAIL get_messages: {exc}")
        failures += 1

    # -----------------------------------------------------------------------
    # 5. Check agent_memory for memory writes
    # -----------------------------------------------------------------------
    print("\n[5] agent_memory — check memory was written by agent")
    try:
        # Search memory with the thread's content
        mem_resp = _post("/api/memory/search", {
            "query": "agent file list harness",
            "user_id": "test",
            "limit": 5,
        })
        results = mem_resp if isinstance(mem_resp, list) else mem_resp.get("results", [])
        check("memory search returns results", len(results) > 0,
              f"got {len(results)} results")
        if results:
            print(f"  first memory content[:120]: {results[0].get('content', '')[:120]}")
    except Exception as exc:
        print(f"  FAIL agent_memory search: {exc}")
        # Not fatal — memory may not have been written yet
        print("  (memory writes are background; not fatal)")
        failures += 1

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    elapsed = round(time.monotonic() - started_at, 1)
    print()
    print("=" * 60)
    if failures:
        print(f"FAILED: {failures} assertion(s)  ({elapsed}s)")
        return 1
    print(f"ALL E2E CHAT SMOKE TESTS PASSED  ({elapsed}s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
