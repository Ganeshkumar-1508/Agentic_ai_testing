"""Comprehensive Integration Test — All Bug Fixes

Tests all fixes from the bug-fixing session:
1. LLM Provider configuration persistence
2. Chat agent start (SSE flow)
3. API key visibility and label
4. Feature Flags (flag_key, rollout_percent)
5. Quality Gates (warn/fail thresholds)
6. Notification Preferences (target field)
7. Session Health (compressions table)
8. Agent PUT endpoint

Run: python -m pytest backend/tests/test_all_fixes.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


# ─── 1. LLM Provider Configuration ────────────────────────────

@pytest.mark.asyncio
async def test_provider_save_and_load():
    """Provider config persists in DB across refreshes."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Save
        r = await client.post(f"{BASE}/api/settings/providers", json=[{
            "provider": "test-llm", "api_key": "sk-test-123",
            "base_url": "https://test.example.com/v1", "model": "test-model",
            "enabled": True, "options": {}
        }])
        assert r.status_code == 200
        # Load
        r2 = await client.get(f"{BASE}/api/settings/providers")
        p = next((x for x in r2.json() if x["provider"] == "test-llm"), None)
        assert p is not None
        assert p["has_key"] is True
        assert p["model"] == "test-model"
        assert p["api_key"] == "sk-test-123"  # visible for single-user app
        # Cleanup
        await client.delete(f"{BASE}/api/settings/providers/test-llm")


@pytest.mark.asyncio
async def test_provider_status_endpoint():
    """Provider status shows configured flag."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/api/provider/status")
        assert r.status_code == 200
        assert r.json()["configured"] is True
        assert r.json()["active_provider"] is not None


@pytest.mark.asyncio
async def test_provider_delete_reloads():
    """Deleting one provider reloads remaining providers."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(f"{BASE}/api/settings/providers", json=[{
            "provider": "temp-prov", "api_key": "sk-temp", "base_url": "https://temp.com/v1",
            "model": "temp-model", "enabled": True, "options": {}
        }])
        await client.delete(f"{BASE}/api/settings/providers/temp-prov")
        r = await client.get(f"{BASE}/api/settings/providers")
        assert not any(x["provider"] == "temp-prov" for x in r.json())
        # opencode should still be there
        assert any(x["provider"] == "opencode" for x in r.json())


# ─── 2. Chat Agent Start ──────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_sse_flow():
    """Chat sends message via SSE and gets LLM response."""
    async with httpx.AsyncClient(timeout=90.0) as client:
        # Create thread
        t = await client.post(f"{BASE}/api/chat/threads", json={"title": "Test", "source": "user"})
        assert t.status_code == 200
        tid = t.json()["id"]
        # Send message via SSE
        r = await client.post(f"{BASE}/api/chat/threads/{tid}/messages",
                              json={"content": "say hi"}, timeout=60.0)
        assert r.status_code == 200
        # Parse SSE events
        text = ""
        for line in r.text.split("\n"):
            if line.startswith("data: "):
                try:
                    e = __import__("json").loads(line[6:])
                    if e.get("delta"):
                        text += e["delta"]
                except:
                    pass
        assert len(text) > 0  # LLM responded


# ─── 3. API Keys (Label Fix) ──────────────────────────────────

@pytest.mark.asyncio
async def test_api_key_label():
    """API key created with custom label persists."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/settings/api-keys", json={"label": "My Test Key"})
        assert r.status_code == 200
        assert r.json()["label"] == "My Test Key"
        assert r.json()["prefix"].startswith("tai_")
        # Verify in GET
        r2 = await client.get(f"{BASE}/api/settings/api-keys")
        key = next((k for k in r2.json().get("keys", []) if k["label"] == "My Test Key"), None)
        assert key is not None
        assert "prefix" in key
        assert "created_at" in key


# ─── 4. Feature Flags ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_feature_flag_flag_key():
    """Feature flag uses flag_key field correctly."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "test-ff", "label": "Test FF", "rollout_percent": 50, "enabled": True
        })
        assert r.status_code == 200
        r2 = await client.get(f"{BASE}/api/settings/feature-flags")
        flag = next((f for f in r2.json().get("flags", []) if f["key"] == "test-ff"), None)
        assert flag is not None
        assert flag["rollout_percent"] == 50
        assert flag["label"] == "Test FF"
        # Cleanup
        await client.delete(f"{BASE}/api/settings/feature-flags/test-ff")


# ─── 5. Quality Gates ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_quality_gate_thresholds():
    """Quality gate with warn/fail thresholds persists."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/settings/gates", json={
            "name": "Test Gate", "metric": "coverage",
            "warn_threshold": 85, "fail_threshold": 70
        })
        assert r.status_code == 200
        r2 = await client.get(f"{BASE}/api/settings/gates")
        gate = next((g for g in r2.json().get("gates", []) if g["name"] == "Test Gate"), None)
        assert gate is not None
        assert gate["warn_threshold"] == 85
        assert gate["fail_threshold"] == 70


# ─── 6. Notification Preferences ───────────────────────────────

@pytest.mark.asyncio
async def test_notification_target():
    """Notification target field persists."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "slack", "enabled": True,
            "events": ["run:completed"], "target": "#test-channel"
        })
        assert r.status_code == 200
        r2 = await client.get(f"{BASE}/api/settings/notification-prefs")
        notif = next((n for n in r2.json().get("preferences", []) if n["channel"] == "slack"), None)
        assert notif is not None
        assert notif["target"] == "#test-channel"
        # Cleanup
        await client.delete(f"{BASE}/api/settings/notification-prefs/slack")


# ─── 7. Session Health ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_health_endpoint():
    """Session health endpoint returns 200 with compressions field."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/api/sessions/test-session/health")
        assert r.status_code == 200
        assert "compressions" in r.json()
        assert "token_usage" in r.json()


# ─── 8. Agent PUT ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_put():
    """Agent PUT endpoint updates agent."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create
        await client.post(f"{BASE}/api/agents", json={
            "name": "test-put-agent", "description": "Original",
            "tools": ["read"], "skills": [], "prompt": "Test"
        })
        # Update
        r = await client.put(f"{BASE}/api/agents/test-put-agent", json={
            "name": "test-put-agent", "description": "Updated",
            "tools": ["read"], "skills": [], "prompt": "Updated"
        })
        assert r.status_code == 200
        assert r.json()["description"] == "Updated"
        # Cleanup
        await client.delete(f"{BASE}/api/agents/test-put-agent")


# ─── 9. All Config Endpoints Return 200 ───────────────────────

@pytest.mark.asyncio
async def test_all_config_endpoints():
    """All settings/config endpoints return 200."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        endpoints = [
            "/api/settings/providers", "/api/settings/webhooks", "/api/settings/api-keys",
            "/api/settings/budgets", "/api/settings/gates", "/api/settings/hooks",
            "/api/settings/env-vars", "/api/settings/mcp", "/api/settings/sandbox",
            "/api/settings/feature-flags", "/api/settings/memory",
            "/api/settings/escalation", "/api/settings/routing-rules",
            "/api/settings/notification-prefs", "/api/settings/pipeline-config",
            "/api/settings/otel", "/api/settings/experiments", "/api/settings/platforms",
            "/api/settings/provider-events", "/api/settings/saved-filters",
            "/api/skills", "/api/skills/hub", "/api/skills/categories",
            "/api/ops/tools", "/api/ops/plugins",
            "/api/agents", "/api/provider/status",
            "/api/integrations/configs", "/api/search/providers", "/api/modes",
            "/api/runs?limit=5", "/api/pipeline-templates",
            "/api/system/health", "/api/system/provider-health",
        ]
        for ep in endpoints:
            r = await client.get(f"{BASE}{ep}")
            assert r.status_code == 200, f"{ep} returned {r.status_code}"
