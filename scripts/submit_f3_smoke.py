import json
import urllib.request
import sys

body = json.dumps({
    "prompt": "Create /tmp/f3_smoke_test.py with 3 passing pytest tests (use assertEqual, assertTrue, assertIn). Then run pytest /tmp/f3_smoke_test.py -v and report the result count.",
    "repo_url": "https://github.com/rails/rails",
    "branch": "main",
    "tier": 1,
    "capabilities": ["write_test_files"],
    "context": {"session_id": "e2e-f3smoke-2026-06-24"},
}).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8001/api/jobs",
    data=body,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
try:
    r = urllib.request.urlopen(req, timeout=15)
    print("Status:", r.status)
    print(r.read().decode("utf-8")[:500])
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code)
    print(e.read().decode("utf-8")[:500])
except Exception as e:
    print("Error:", e)
