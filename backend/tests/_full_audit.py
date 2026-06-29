"""Audit every dashboard page: what API it calls, what it renders."""
import json, urllib.request, urllib.error, sys
from pathlib import Path

API = "http://localhost:8000"
SRC = Path(r"C:\Users\AswinPremnathChandra\Documents\testai-production\src\app\(dashboard)")

# Pages to audit: (route, frontend_file_exists, backend_api)
pages = {
    "dashboard":       {"file": "dashboard/page.tsx",       "api": "/api/dashboard/overview"},
    "jobs":            {"file": "jobs/page.tsx",            "api": "/api/jobs?limit=5"},
    "chat":            {"file": "chat/page.tsx",            "api": "/api/chat/threads"},
    "sessions":        {"file": "sessions/page.tsx",        "api": "/api/sessions?limit=3"},
    "history":         {"file": "history/[runId]/page.tsx", "api": "/api/runs?limit=3"},
    "sandbox":         {"file": "sandbox/page.tsx",         "api": "/api/sandbox/list"},
    "knowledge-graph": {"file": "knowledge-graph/page.tsx", "api": "/api/knowledge-graph/recent"},
    "test-cases":      {"file": "test-cases/page.tsx",      "api": "/api/testcases?project_id=default-project"},
    "quality":         {"file": "quality/page.tsx",         "api": "/api/quality/score?days=14"},
    "pull-requests":   {"file": "pull-requests/page.tsx",   "api": "/api/prs"},
    "kanban":          {"file": "kanban/page.tsx",          "api": "/api/kanban/boards"},
    "observability":   {"file": "observability/page.tsx",   "api": "/api/observability/status"},
    "tools":           {"file": "tools/page.tsx",           "api": "/api/tools"},
    "skills":          {"file": "skills/page.tsx",          "api": "/api/skills"},
    "channels":        {"file": "channels/page.tsx",        "api": "/api/channels"},
    "activity":        {"file": "activity/page.tsx",        "api": "/api/events/_global"},
    "ai-ops":          {"file": "ai-ops/page.tsx",          "api": "/api/ai-ops"},
    "artifacts":       {"file": "artifacts/page.tsx",       "api": "/api/artifacts"},
}

print("=" * 70)
print("COMPREHENSIVE PAGE AUDIT")
print("=" * 70)

for route, info in pages.items():
    frontend_path = SRC / info["file"]
    api_path = info["api"]
    
    # Check frontend exists
    fe_exists = "YES" if frontend_path.exists() else "NO"
    
    # Check backend API
    try:
        req = urllib.request.Request(f"{API}{api_path}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode()
            data = json.loads(body) if body else {}
            status = r.status
    except urllib.error.HTTPError as e:
        data = {}
        status = e.code
    except Exception as e:
        data = {}
        status = f"ERR {e}"
    
    # Determine if page gets data
    gets_data = "NO"
    if status == 200:
        if isinstance(data, dict):
            total = sum(len(v) for v in data.values() if isinstance(v, list))
            gets_data = f"YES ({total} items)" if total > 0 else "YES (empty - no data yet)"
        else:
            gets_data = "YES"
    
    print(f"  /{route:<20s} FE={fe_exists:<4s} API={str(status):<6s} {gets_data}")

print()
print("DONE")
