"""Quality Gates Panel API Test

Tests the full CRUD flow for quality gates including
the warn_threshold and fail_threshold fix.

Run: python -m pytest backend/tests/test_gates_panel.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_create_gate_with_dual_thresholds():
    """Create a gate with both warn and fail thresholds."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/gates", json={
            "name": "Pass Rate Gate",
            "metric": "pass_rate",
            "description": "Blocks when pass rate drops",
            "warn_threshold": 85.0,
            "fail_threshold": 70.0,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_gate_default_thresholds():
    """Create a gate with default thresholds."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/gates", json={
            "name": "Coverage Gate",
            "metric": "coverage",
        })
        assert r.status_code == 200
        # Should use defaults: warn=0.8, fail=0.6
        gates = await client.get(f"{BASE}/api/settings/gates")
        gate = next((g for g in gates.json().get("gates", []) if g["name"] == "Coverage Gate"), None)
        assert gate is not None
        assert gate["warn_threshold"] == 0.8
        assert gate["fail_threshold"] == 0.6


@pytest.mark.asyncio
async def test_thresholds_persist_after_load():
    """Thresholds persist when loaded from DB."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/gates", json={
            "name": "Threshold Test",
            "metric": "errors",
            "warn_threshold": 90.0,
            "fail_threshold": 50.0,
        })
        r = await client.get(f"{BASE}/api/settings/gates")
        gate = next((g for g in r.json().get("gates", []) if g["name"] == "Threshold Test"), None)
        assert gate is not None
        assert gate["warn_threshold"] == 90.0
        assert gate["fail_threshold"] == 50.0


@pytest.mark.asyncio
async def test_toggle_gate():
    """Toggle a gate enabled/disabled."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/gates", json={
            "name": "Toggle Test",
            "metric": "coverage",
            "warn_threshold": 80,
            "fail_threshold": 60,
        })
        gates = await client.get(f"{BASE}/api/settings/gates")
        gate = next((g for g in gates.json().get("gates", []) if g["name"] == "Toggle Test"), None)
        assert gate is not None
        assert gate["enabled"] is True
        # Toggle
        await client.patch(f"{BASE}/api/settings/gates/{gate['id']}", json={"enabled": False})
        gates2 = await client.get(f"{BASE}/api/settings/gates")
        gate2 = next((g for g in gates2.json().get("gates", []) if g["name"] == "Toggle Test"), None)
        assert gate2["enabled"] is False


@pytest.mark.asyncio
async def test_delete_gate():
    """Delete a gate."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/gates", json={
            "name": "Delete Me",
            "metric": "test",
            "warn_threshold": 80,
            "fail_threshold": 60,
        })
        gates = await client.get(f"{BASE}/api/settings/gates")
        gate = next((g for g in gates.json().get("gates", []) if g["name"] == "Delete Me"), None)
        assert gate is not None
        await client.delete(f"{BASE}/api/settings/gates/{gate['id']}")
        gates2 = await client.get(f"{BASE}/api/settings/gates")
        deleted = next((g for g in gates2.json().get("gates", []) if g["name"] == "Delete Me"), None)
        assert deleted is None


@pytest.mark.asyncio
async def test_multiple_gates():
    """Create multiple gates and verify all persist."""
    async with httpx.AsyncClient() as client:
        for i in range(3):
            await client.post(f"{BASE}/api/settings/gates", json={
                "name": f"Gate {i}",
                "metric": f"metric_{i}",
                "warn_threshold": 80 + i,
                "fail_threshold": 60 + i,
            })
        r = await client.get(f"{BASE}/api/settings/gates")
        gates = [g for g in r.json().get("gates", []) if g["name"].startswith("Gate ")]
        assert len(gates) >= 3
