"""Feature Flags API Test

Tests the full CRUD flow for feature flags including
the flag_key, label, and rollout_percent fix.

Run: python -m pytest backend/tests/test_feature_flags.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_create_flag_with_correct_fields():
    """Create a flag with flag_key, label, and rollout_percent."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "test-flag",
            "label": "Test Feature",
            "description": "A test feature flag",
            "enabled": True,
            "rollout_percent": 50,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_flag_key_persists_after_load():
    """Flag key persists when loaded from DB."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "persist-test",
            "label": "Persist Test",
            "rollout_percent": 75,
        })
        r = await client.get(f"{BASE}/api/settings/feature-flags")
        flag = next((f for f in r.json().get("flags", []) if f["key"] == "persist-test"), None)
        assert flag is not None
        assert flag["label"] == "Persist Test"


@pytest.mark.asyncio
async def test_rollout_percent_persists():
    """Rollout percent persists when loaded from DB."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "rollout-test",
            "label": "Rollout Test",
            "rollout_percent": 42,
        })
        r = await client.get(f"{BASE}/api/settings/feature-flags")
        flag = next((f for f in r.json().get("flags", []) if f["key"] == "rollout-test"), None)
        assert flag is not None
        assert flag["rollout_percent"] == 42


@pytest.mark.asyncio
async def test_toggle_flag():
    """Toggle a flag enabled/disabled."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "toggle-test",
            "label": "Toggle Test",
            "enabled": False,
        })
        r = await client.get(f"{BASE}/api/settings/feature-flags")
        flag = next((f for f in r.json().get("flags", []) if f["key"] == "toggle-test"), None)
        assert flag["enabled"] is False
        # Toggle
        await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "toggle-test", "label": "Toggle Test", "enabled": True, "rollout_percent": 100,
        })
        r2 = await client.get(f"{BASE}/api/settings/feature-flags")
        flag2 = next((f for f in r2.json().get("flags", []) if f["key"] == "toggle-test"), None)
        assert flag2["enabled"] is True


@pytest.mark.asyncio
async def test_delete_flag():
    """Delete a flag."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/feature-flags", json={
            "flag_key": "delete-me", "label": "Delete Me",
        })
        r = await client.get(f"{BASE}/api/settings/feature-flags")
        flag = next((f for f in r.json().get("flags", []) if f["key"] == "delete-me"), None)
        assert flag is not None
        await client.delete(f"{BASE}/api/settings/feature-flags/delete-me")
        r2 = await client.get(f"{BASE}/api/settings/feature-flags")
        deleted = next((f for f in r2.json().get("flags", []) if f["key"] == "delete-me"), None)
        assert deleted is None


@pytest.mark.asyncio
async def test_multiple_flags():
    """Create multiple flags and verify all persist."""
    async with httpx.AsyncClient() as client:
        for i in range(3):
            await client.post(f"{BASE}/api/settings/feature-flags", json={
                "flag_key": f"flag-{i}",
                "label": f"Flag {i}",
                "rollout_percent": 10 * i,
            })
        r = await client.get(f"{BASE}/api/settings/feature-flags")
        flags = [f for f in r.json().get("flags", []) if f["key"].startswith("flag-")]
        assert len(flags) >= 3
