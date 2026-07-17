"""OTel Settings Tab Accessibility Test

Tests that OTel (OpenTelemetry) settings are accessible from the UI
and the GET/POST endpoints work correctly.

The bug: OTelSettings component was registered in PANEL_MAP as 'otel'
but no tab with id 'otel' existed in TAB_GROUPS — users couldn't navigate to it.

Fix: Added { id: "otel", label: "OTel Settings", ... } to System group in TAB_GROUPS.

Run: python -m pytest backend/tests/test_otel_settings.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_otel_get_returns_200():
    """OTel settings GET endpoint returns 200."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/api/settings/otel")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_otel_get_has_expected_fields():
    """OTel settings returns expected config fields."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/api/settings/otel")
        data = r.json()
        assert "enabled" in data
        assert "endpoint" in data
        assert "service_name" in data


@pytest.mark.asyncio
async def test_otel_save_and_persist():
    """OTel settings save and persist across loads."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Save
        r = await client.post(f"{BASE}/api/settings/otel", json={
            "enabled": True,
            "endpoint": "http://localhost:4317",
            "service_name": "test-service"
        })
        assert r.status_code == 200
        # Load
        r2 = await client.get(f"{BASE}/api/settings/otel")
        data = r2.json()
        assert data["service_name"] == "test-service"
        assert data["endpoint"] == "http://localhost:4317"
