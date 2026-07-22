"""Integration tests — verify all backend endpoints respond 200.

These tests run against the LIVE backend at http://localhost:8001.
Start the server with `docker compose up -d` before running tests.
"""

import pytest
import httpx

BASE = "http://127.0.0.1:8001"


@pytest.mark.parametrize("path,method", [
    ("/health", "GET"),
    ("/api/modes", "GET"),
    ("/api/runs", "GET"),
    ("/api/sessions", "GET"),
    ("/api/dashboard/stats", "GET"),
    ("/api/export/all", "GET"),
    ("/api/analytics/usage?days=7", "GET"),
    ("/api/analytics/models", "GET"),
    ("/api/ops/tools", "GET"),
    ("/api/ops/plugins", "GET"),
    ("/api/settings/providers", "GET"),
    ("/api/settings/mcp", "GET"),
    ("/api/settings/webhooks", "GET"),
    ("/api/settings/api-keys", "GET"),
    ("/api/settings/gates", "GET"),
    ("/api/settings/hooks", "GET"),
    ("/api/settings/prompts", "GET"),
    ("/api/settings/experiments", "GET"),
    ("/api/settings/memory", "GET"),
    ("/api/skills", "GET"),
    ("/api/cron-jobs", "GET"),
    ("/api/coverage/history", "GET"),
    ("/api/delegate/approvals/pending", "GET"),
    ("/api/stream/recent", "GET"),
    ("/openapi.json", "GET"),
    ("/api/pipeline-templates", "GET"),
    ("/api/testcases", "GET"),
    ("/api/tests/flaky", "GET"),
])
def test_endpoint_returns_200(path: str, method: str) -> None:
    resp = httpx.request(method, f"{BASE}{path}", timeout=10)
    assert resp.status_code == 200, f"{method} {path} returned {resp.status_code}"
    assert len(resp.text) > 0


def test_openapi_has_many_paths() -> None:
    resp = httpx.get(f"{BASE}/openapi.json", timeout=10)
    data = resp.json()
    assert len(data["paths"]) > 20
