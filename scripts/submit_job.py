import json
import urllib.request
import sys

body = json.dumps({
    "prompt": "Create /tmp/empty_test.py with 3 passing pytest tests, then run pytest and report results.",
    "repo_url": "https://github.com/rails/rails",
    "branch": "main",
    "tier": 1,
    "capabilities": ["write_test_files"],
    "context": {"session_id": "e2e-f3-eventfixes-2026-06-24"},
}).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8001/api/jobs",
    data=body,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
try:
    r = urllib.request.urlopen(req, timeout=20)
    print("Status:", r.status)
    print(r.read().decode("utf-8")[:500])
except Exception as e:
    print("Error:", e)
