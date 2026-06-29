"""Comprehensive endpoint check for all pages."""
import json, urllib.request, urllib.error

API = "http://localhost:8000"

endpoints = [
    # Dashboard widgets
    ("/api/dashboard/overview", "dashboard overview"),
    ("/api/dashboard/widgets/analytics-30d", "dashboard analytics"),
    ("/api/dashboard/widgets/coverage?days=30", "dashboard coverage"),
    ("/api/dashboard/widgets/rca-clusters?days=30", "dashboard RCA"),
    ("/api/dashboard/widgets/system-health", "dashboard system-health"),
    ("/api/dashboard/widgets/sprint-trends?sprints=5", "dashboard sprint-trends"),
    
    # Jobs
    ("/api/jobs?limit=5", "jobs list"),
    ("/api/jobs?session_id=api-7839ab8a&limit=5", "jobs by session"),
    
    # Chat
    ("/api/chat/threads", "chat threads"),
    ("/api/chat/threads/0e37b18c-3e82-492d-88b4-ec1f141771e3", "chat thread detail"),
    
    # Sessions
    ("/api/sessions?limit=3", "sessions list"),
    ("/api/sessions/api-7839ab8a", "session detail"),
    ("/api/sessions/api-7839ab8a/events?limit=10", "session events"),
    
    # History / Runs
    ("/api/runs?limit=3", "runs list"),
    ("/api/runs?session_id=api-7839ab8a&limit=3", "runs by session"),
    
    # Sandbox
    ("/api/sandbox/list", "sandbox list"),
    ("/api/sandbox/exec-containers", "sandbox containers"),
    ("/api/artifacts/api-f1d7c086", "artifacts for session"),
    
    # Knowledge Graph
    ("/api/knowledge-graph/recent", "KG recent"),
    ("/api/knowledge-graph/a901b404fa3c2b12", "KG detail"),
    
    # Kanban
    ("/api/kanban/boards", "kanban boards"),
    ("/api/kanban/boards/53bc4457-24c8-4dfb-9fb8-ae4c88aff0a1/tasks", "kanban tasks"),
    
    # Quality
    ("/api/quality/score?days=14", "quality score"),
    ("/api/quality/trend?days=90", "quality trend"),
    ("/api/settings/gates", "quality gates"),
    
    # Test Cases
    ("/api/testcases?project_id=default-project", "testcases"),
    ("/api/testcases/folders", "testcase folders"),
    
    # Pull Requests
    ("/api/prs", "PRs list"),
    ("/api/prs/sync", "PRs sync (POST)"),
    
    # Tools
    ("/api/tools", "tools list"),
    
    # Skills
    ("/api/skills", "skills list"),
    
    # Observability
    ("/api/observability/status", "observability status"),
    ("/api/observability/compaction", "observability compaction"),
    
    # Digest
    ("/api/digest/configs", "digest configs"),
    
    # Memory
    ("/api/memory/search", "memory search (POST)"),
    
    # Settings
    ("/api/settings/providers", "settings providers"),
    
    # Coverage
    ("/api/coverage/history?limit=5", "coverage history"),
    
    # Delegate (SSE - just check it doesn't 500)
    # ("/api/delegate/api-7839ab8a/stream", "delegate stream"),
    
    # Health
    ("/health", "health"),
]

results = []
for path, label in endpoints:
    try:
        if "sync" in path or "search" in path:
            # Skip POST endpoints
            results.append((label, "SKIP", "POST"))
            continue
        req = urllib.request.Request(f"{API}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode()
            data = json.loads(body) if body else {}
            items = 0
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        items += len(v)
            results.append((label, "OK", f"items={items}"))
    except urllib.error.HTTPError as e:
        results.append((label, f"HTTP {e.code}", ""))
    except Exception as e:
        results.append((label, "TIMEOUT", str(e)[:40]))

print("=" * 70)
print("ALL BACKEND ENDPOINTS")
print("=" * 70)
for label, status, detail in results:
    icon = "✅" if "OK" in status else "❌" if "404" in status or "500" in status else "⏳"
    print(f"  {icon} {label:<40s} {status:<10s} {detail}")

ok = sum(1 for _, s, _ in results if "OK" in s)
skip = sum(1 for _, s, _ in results if "SKIP" in s)
fail = sum(1 for _, s, _ in results if "404" in s or "500" in s)
timeout = sum(1 for _, s, _ in results if "TIMEOUT" in s)

print(f"\n  {ok} OK / {skip} skip (POST) / {fail} fail / {timeout} timeout")
