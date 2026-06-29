"""Smoke test: /api/memory/* + memory_search / memory_add tools.

Verifies the full Phase 3 memory substrate:
  1. Direct DB calls: add() then search() round-trip
  2. HTTP API: POST /api/memory/add + POST /api/memory/search
  3. Chat tools: memory_search + memory_add via the tool registry
  4. FTS ranking: out-of-scope queries return nothing
  5. Tier filter: source=L0 vs L1 vs L2
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
import uuid


BASE = "http://localhost:8000"


def _post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}


async def run() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] direct DB add + search round-trip")
    from harness.memory.database import Database
    from harness.memory.agent_memory_store import add, search, VALID_SOURCES
    from harness.tools.chat_read_tools import set_chat_db
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    db = Database(db_url)
    await db.connect()
    set_chat_db(db)

    repo = f"smoke-mem-{uuid.uuid4().hex[:8]}"
    f1 = await add(
        "user prefers verbose commit messages with rationale",
        repo_slug=repo, source="L2", target="convention",
        confidence=0.9, source_kind="chat_observation",
        metadata={"channel": "support", "agent": "claude-opus-4-7"},
        db=db,
    )
    f2 = await add(
        "auth middleware uses Redis for session lookup",
        repo_slug=repo, source="L1", target="auth",
        confidence=0.7, source_kind="compaction_summary",
        db=db,
    )
    f3 = await add(
        "payment service requires idempotency keys for POST /charge",
        repo_slug=repo, source="L0", target="payment",
        confidence=1.0, source_kind="chat_observation",
        db=db,
    )
    check("add L2 returns id", bool(f1.id))
    check("add L1 returns id", bool(f2.id))
    check("add L0 returns id", bool(f3.id))
    check("source is preserved", f1.source == "L2")

    hits = await search("commit messages", repo_slug=repo, db=db)
    check("search 'commit messages' finds L2", len(hits) >= 1 and hits[0].id == f1.id)
    hits = await search("auth middleware", repo_slug=repo, db=db)
    check("search 'auth middleware' finds L1", any(h.id == f2.id for h in hits))
    hits = await search("idempotency", repo_slug=repo, db=db)
    check("search 'idempotency' finds L0", any(h.id == f3.id for h in hits))
    hits = await search("nonexistent_term_xyz_123", repo_slug=repo, db=db)
    check("OOV query returns nothing", len(hits) == 0)

    hits = await search("auth", repo_slug=repo, source="L1", db=db)
    check("filter source=L1 returns L1 only", all(h.source == "L1" for h in hits) and len(hits) >= 1)
    hits = await search("auth", repo_slug=repo, source="L2", db=db)
    check("filter source=L2 (no L2 match for 'auth')", len(hits) == 0)

    hits = await search("commit", repo_slug=repo, min_confidence=0.95, db=db)
    check("min_confidence 0.95 filters out 0.9", len(hits) == 0)
    hits = await search("commit", repo_slug=repo, min_confidence=0.5, db=db)
    check("min_confidence 0.5 includes 0.9", len(hits) >= 1)

    hits = await search("commit", repo_slug="other_repo_unrelated", db=db)
    check("repo_slug filter excludes our repo", len(hits) == 0)

    print("[2] HTTP API")
    http_repo = f"smoke-http-{uuid.uuid4().hex[:8]}"
    status, resp = _post("/api/memory/add", {
        "content": "POST /charge requires idempotency key header",
        "repo_slug": http_repo, "source": "L0", "target": "payment",
        "confidence": 0.8, "metadata": {"src": "test"},
    })
    check("HTTP add → 201", status == 201, f"got {status}")
    if status == 201:
        check("HTTP add returns id", "id" in resp)
    fact_id = resp.get("id", "")

    status, resp = _post("/api/memory/add", {
        "content": "x", "repo_slug": "",  # missing
    })
    check("HTTP add empty repo_slug → 400 or 422", status in (400, 422), f"got {status}")

    status, resp = _post("/api/memory/add", {
        "content": "x", "repo_slug": "x", "source": "INVALID",
    })
    check("HTTP add invalid source → 400 or 422", status in (400, 422), f"got {status}")

    status, resp = _post("/api/memory/search", {
        "query": "idempotency", "repo_slug": http_repo, "limit": 5,
    })
    check("HTTP search → 200", status == 200, f"got {status}")
    if status == 200:
        check("HTTP search returns count", "count" in resp and resp["count"] >= 1)
        check("HTTP search returns results", "results" in resp and len(resp["results"]) >= 1)
        if resp.get("results"):
            check("HTTP result has content", "content" in resp["results"][0])
            check("HTTP result has tier", "source" in resp["results"][0])

    status, resp = _post("/api/memory/search", {"query": ""})
    check("HTTP search empty query → 400 or 422 (validation)", status in (400, 422), f"got {status}")

    print("[3] chat tools — memory_search + memory_add")
    from harness.tools.memory_search import MemorySearchTool, MemoryAddTool
    from harness.tools.chat_read_tools import set_chat_db
    set_chat_db(db)

    tool = MemoryAddTool()
    res = await tool.run(content="chat tool test fact", repo_slug=repo, source="L1", confidence=0.6)
    check("MemoryAddTool success", res.success, f"err={res.error} out={res.output[:120]}")
    check("MemoryAddTool data has fact", res.data and "fact" in res.data)

    res = await tool.run(content="", repo_slug=repo)
    check("MemoryAddTool empty content → error", not res.success and res.error == "missing_arg")
    res = await tool.run(content="x", repo_slug="")
    check("MemoryAddTool empty repo_slug → error", not res.success and res.error == "missing_arg")

    tool = MemorySearchTool()
    res = await tool.run(query="commit messages", repo_slug=repo, limit=5)
    check("MemorySearchTool success", res.success, f"err={res.error}")
    check("MemorySearchTool finds L2", "commit" in (res.output or "").lower())

    res = await tool.run(query="", repo_slug=repo)
    check("MemorySearchTool empty query → error", not res.success and res.error == "missing_arg")
    res = await tool.run(query="nonexistent_xyz_abc", repo_slug=repo)
    check("MemorySearchTool OOV → success no results", res.success and (res.data or {}).get("results") == [])

    print("[4] toolset wiring")
    from harness.tools.toolsets import CHAT_READONLY_TOOLSET
    check("memory_search in CHAT_READONLY_TOOLSET", "memory_search" in CHAT_READONLY_TOOLSET)
    check("memory_add in CHAT_READONLY_TOOLSET", "memory_add" in CHAT_READONLY_TOOLSET)

    await db.disconnect()
    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL MEMORY SUBSTRATE SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
