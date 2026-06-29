"""Integration tests — verify all backend endpoints respond 200.

These tests run against the LIVE backend at http://localhost:8001.
Start the server with `docker compose up -d` before running tests.
"""

import pytest
import httpx

BASE = "http://localhost:8001"


@pytest.mark.parametrize("path,method", [
    ("/health", "GET"),
    ("/modes", "GET"),
    ("/runs", "GET"),
    ("/sessions", "GET"),
    ("/dashboard/stats", "GET"),
    ("/export/all", "GET"),
    ("/analytics/usage?days=7", "GET"),
    ("/analytics/models", "GET"),
    ("/ops/tools", "GET"),
    ("/ops/plugins", "GET"),
    ("/settings/providers", "GET"),
    ("/settings/mcp", "GET"),
    ("/settings/runners", "GET"),
    ("/settings/webhooks", "GET"),
    ("/settings/api-keys", "GET"),
    ("/settings/gates", "GET"),
    ("/settings/hooks", "GET"),
    ("/settings/prompts", "GET"),
    ("/settings/experiments", "GET"),
    ("/settings/memory", "GET"),
    ("/settings/dashboards", "GET"),
    ("/governance/config", "GET"),
    ("/skills", "GET"),
    ("/cron-jobs", "GET"),
    ("/coverage/history", "GET"),
    ("/approvals/pending", "GET"),
    ("/swarm/active", "GET"),
    ("/stream/recent", "GET"),
    ("/openapi.json", "GET"),
    ("/pipeline-templates", "GET"),
    ("/testcases", "GET"),
    ("/tests/flaky", "GET"),
])
def test_endpoint_returns_200(path: str, method: str) -> None:
    resp = httpx.request(method, f"{BASE}{path}", timeout=10)
    assert resp.status_code == 200, f"{method} {path} returned {resp.status_code}"
    assert len(resp.text) > 0


def test_openapi_has_many_paths() -> None:
    resp = httpx.get(f"{BASE}/openapi.json", timeout=10)
    data = resp.json()
    assert len(data["paths"]) > 20
