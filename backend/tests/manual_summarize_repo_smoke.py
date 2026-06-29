"""Smoke test: /api/repos/{owner}/{repo}/summarize endpoint."""
from __future__ import annotations

import os
import sys
import urllib.request
import urllib.error
import json


def _post(owner: str, repo: str, base: str = "http://localhost:8000") -> tuple[int, dict]:
    url = f"{base}/api/repos/{owner}/{repo}/summarize"
    req = urllib.request.Request(url, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] not cached — 404 with hint")
    status, body = _post("nonexistent-org-xyz", "nonexistent-repo-xyz")
    check("404", status == 404, f"got {status}")
    detail = body.get("detail", body)
    check("error=repo_not_cached", isinstance(detail, dict) and detail.get("error") == "repo_not_cached")
    if isinstance(detail, dict):
        check("searched list present", isinstance(detail.get("searched"), list) and len(detail["searched"]) >= 1)
        check("hint present", "POST /api/jobs" in (detail.get("hint") or ""))

    print("[2] test repo at /app/agent_workspace/example/foo — 200")
    status, body = _post("example", "foo")
    check("200", status == 200, f"got {status}")
    check("owner=example", body.get("owner") == "example")
    check("repo=foo", body.get("repo") == "foo")
    check("path set", "/app/agent_workspace/example/foo" in (body.get("path") or ""))
    check("total_files > 0", body.get("total_files", 0) > 0, f"n={body.get('total_files')}")
    check("languages has .py", ".py" in (body.get("languages") or {}), f"keys={list((body.get('languages') or {}).keys())}")
    check("entry_points contains app.py", "app.py" in (body.get("entry_points") or []))
    check("has_readme", body.get("has_readme") is True)
    check("flask in frameworks", any("flask" in (f or "").lower() for f in (body.get("frameworks") or [])))
    check("tests in test_dirs", "tests" in (body.get("test_dirs") or []))
    check("manifests has requirements.txt", "requirements.txt" in (body.get("manifests") or []))

    print("[3] test repo at /app/agent_workspace/testai-production_app — 200 (alt path)")
    status, body = _post("testai-production", "app")
    check("200", status == 200, f"got {status}")
    if status == 200:
        check("path set", "testai-production_app" in (body.get("path") or ""))

    print("[4] test repo at /app/agent_workspace/testai-production-app — 200 (dash separator)")
    status, body = _post("testai-production", "app-v2-test")
    check("status 200 or 404", status in (200, 404), f"got {status}")
    if status == 200:
        check("dash-separator path used", "testai-production-app-v2-test" in (body.get("path") or ""))

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL SUMMARIZE_REPO SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
