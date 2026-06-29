"""Audit every dashboard page's backend API endpoint."""
import json, urllib.request, urllib.error, sys

API = "http://localhost:8000"

pages = [
    # (name, method, path, expected_fields)
    ("knowledge-graph", "GET", "/api/knowledge-graph/recent", ["graphs"]),
    ("test-cases", "GET", "/api/testcases?project_id=default-project", ["test_cases"]),
    ("test-cases/folders", "GET", "/api/testcases/folders", ["folders"]),
    ("quality/score", "GET", "/api/quality/score?days=14", ["score", "verdict"]),
    ("quality/trend", "GET", "/api/quality/trend?days=90", ["trend"]),
    ("quality/gates", "GET", "/api/settings/gates", ["gates"]),
    ("jobs", "GET", "/api/jobs?limit=5", ["items"]),
    ("jobs/by-session", "GET", "/api/jobs?session_id=api-7839ab8a&limit=5", ["items"]),
    ("pull-requests", "GET", "/api/prs", ["prs"]),
    ("chat/threads", "GET", "/api/chat/threads", ["threads"]),
    ("sandbox", "GET", "/api/sandbox", None),  # 404 expected
    ("sessions", "GET", "/api/sessions", None),
    ("agents", "GET", "/api/agents", None),
    ("kanban", "GET", "/api/kanban", None),
    ("pipeline/runs", "GET", "/api/runs", None),
    ("dashboard", "GET", "/api/dashboard", None),
    ("health", "GET", "/health", ["status"]),
    ("events", "GET", "/api/events/_global", None),
    ("digest", "GET", "/api/digest", None),
    ("observability", "GET", "/api/observability", None),
    ("tools", "GET", "/api/tools", None),
    ("artifacts", "GET", "/api/artifacts", None),
]

failures = 0
for name, method, path, expected_fields in pages:
    try:
        req = urllib.request.Request(f"{API}{path}", method=method)
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            data = json.loads(body) if body else {}
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        data = {}
        status = e.code
    except Exception as e:
        data = {}
        status = f"ERR {e}"

    has_fields = "no"
    if expected_fields and isinstance(data, dict):
        present = [f for f in expected_fields if f in data]
        has_fields = str(present) if present else "MISSING"

    ok = "OK" if (status == 200 and (not expected_fields or has_fields != "MISSING")) else "BROKEN" if status != 200 else "EMPTY"
    detail = f"http={status}"
    if isinstance(data, dict):
        if expected_fields and has_fields == "MISSING":
            detail += f" missing_fields={expected_fields}"
        elif isinstance(data, dict):
            detail += f" fields={list(data.keys())[:5]}"
    elif isinstance(data, list):
        detail += f" count={len(data)}"

    print(f"  [{ok:6s}] {name:<30s} {detail}")
    if ok == "BROKEN":
        failures += 1

print(f"\n{failures} broken endpoints")
if failures:
    sys.exit(1)
