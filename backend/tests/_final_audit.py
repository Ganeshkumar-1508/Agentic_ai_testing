import json, urllib.request

endpoints = [
    ("runs", "/api/runs?limit=3"),
    ("sessions", "/api/sessions?limit=3"),
    ("kanban", "/api/kanban/boards"),
    ("dashboard", "/api/dashboard/overview"),
    ("artifacts", "/api/artifacts"),
    ("quality/score", "/api/quality/score?days=14"),
    ("testcases", "/api/testcases?project_id=default-project"),
    ("pull-requests", "/api/prs"),
    ("chat/threads", "/api/chat/threads"),
    ("sandbox/list", "/api/sandbox/list"),
    ("knowledge-graph", "/api/knowledge-graph/recent"),
    ("observability", "/api/observability/status"),
    ("health", "/health"),
]

for name, path in endpoints:
    try:
        req = urllib.request.Request(f"http://localhost:8000{path}", method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            data = json.loads(body) if body else {}
            status = r.status
    except urllib.error.HTTPError as e:
        data = {}
        status = e.code
    except Exception as e:
        data = {}
        status = f"ERR {e}"

    if isinstance(data, dict):
        summary = f"http={status} fields={list(data.keys())[:4]}"
        for k, v in data.items():
            if isinstance(v, list):
                summary += f" {k}={len(v)}"
    elif isinstance(data, list):
        summary = f"http={status} count={len(data)}"
    else:
        summary = f"http={status}"

    ok = "OK" if status == 200 else "FAIL"
    print(f"  [{ok}] {name:<25s} {summary}")
