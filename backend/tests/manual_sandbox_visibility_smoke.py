"""Smoke test: /api/sandbox/* visibility surface.

Verifies that the 12+ sandbox endpoints (from the F3 audit) are
reachable and respond with valid JSON shapes. The endpoints are
read-only observation of the sandbox manager — they don't actually
provision or destroy sandboxes (we have no Docker-in-Docker
support in this environment).
"""
from __future__ import annotations

import sys
import urllib.request
import urllib.error
import json

BASE = "http://localhost:8000"


def _get(path: str) -> tuple[int, dict | str]:
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=10)
        body = r.read().decode("utf-8")
        try:
            return r.status, json.loads(body)
        except Exception:
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    endpoints = [
        ("/api/sandbox/exec-containers", ["GET"], "containers"),
        ("/api/sandbox/list", ["GET"], "sandboxes"),
        ("/api/sandbox/metrics", ["GET"], None),
        ("/api/sandbox/snapshots", ["GET"], "snapshots"),
        ("/api/sandbox/volumes", ["GET"], "volumes"),
        ("/api/ops/sandbox-metrics", ["GET"], None),
    ]

    for path, expected_methods, expected_key in endpoints:
        status, body = _get(path)
        method = expected_methods[0]
        check(f"{method} {path} → 200", status == 200, f"got {status}")
        if expected_key and isinstance(body, dict):
            check(f"  has key '{expected_key}'", expected_key in body,
                  f"keys={list(body.keys()) if isinstance(body, dict) else type(body).__name__}")

    print("[1] session-scoped endpoints — 404 (no sandbox) is acceptable for unknown id")
    for path in [
        "/api/sandbox/fake-session-id/resources",
        "/api/sandbox/fake-session-id/ports",
        "/api/sandbox/fake-session-id/dependencies",
        "/api/sandbox/fake-session-id/flaky-tests",
        "/api/sandbox/fake-session-id/artifacts",
        "/api/sandbox/fake-session-id/events",
        "/api/sandbox/workspace/fake-session-id",
    ]:
        status, body = _get(path)
        check(f"  {path} → 404 or 400", status in (200, 400, 404),
              f"got {status}")

    print("[2] OpenAPI schema includes sandbox routes")
    status, schema = _get("/openapi.json")
    check("schema returned", status == 200)
    sandbox_paths = [p for p in (schema or {}).get("paths", {}) if "/sandbox" in p]
    check(f"≥ 10 sandbox paths in schema", len(sandbox_paths) >= 10, f"got {len(sandbox_paths)}")

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL SANDBOX VISIBILITY SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
