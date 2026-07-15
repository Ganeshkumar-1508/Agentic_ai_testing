"""API Keys Label & Prefix Test

Tests that API keys are created with correct label, prefix, and
that the key prefix and created_at are returned for display.

Run: python -m pytest backend/tests/test_api_keys_label.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_create_api_key_with_custom_label():
    """API key created with custom label persists."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/api-keys", json={
            "label": "Production Key"
        })
        assert r.status_code == 200
        data = r.json()
        assert "key" in data
        assert data["label"] == "Production Key"
        assert data["prefix"] is not None


@pytest.mark.asyncio
async def test_create_api_key_default_label():
    """API key created without label gets 'default'."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/api-keys", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["label"] == "default"


@pytest.mark.asyncio
async def test_key_prefix_returned():
    """Key prefix is returned in create response."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Test"})
        data = r.json()
        assert "prefix" in data
        assert len(data["prefix"]) > 0
        assert data["prefix"].startswith("tai_")


@pytest.mark.asyncio
async def test_label_persists_after_load():
    """Label persists when loaded from DB."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Staging Key"})
        r = await client.get(f"{BASE}/api/settings/api-keys")
        keys = r.json().get("keys", [])
        staging = next((k for k in keys if k["label"] == "Staging Key"), None)
        assert staging is not None
        assert staging["label"] == "Staging Key"


@pytest.mark.asyncio
async def test_prefix_and_created_at_returned():
    """Prefix and created_at are returned in GET response."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Prefix Test"})
        prefix = r.json().get("prefix")
        r2 = await client.get(f"{BASE}/api/settings/api-keys")
        key = next((k for k in r2.json().get("keys", []) if k["prefix"] == prefix), None)
        assert key is not None
        assert "prefix" in key
        assert "created_at" in key
        assert key["prefix"].startswith("tai_")


@pytest.mark.asyncio
async def test_multiple_keys_different_labels():
    """Multiple keys with different labels coexist."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Key A"})
        await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Key B"})
        await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Key C"})
        r = await client.get(f"{BASE}/api/settings/api-keys")
        labels = [k["label"] for k in r.json().get("keys", [])]
        assert "Key A" in labels
        assert "Key B" in labels
        assert "Key C" in labels


@pytest.mark.asyncio
async def test_delete_api_key():
    """Delete an API key by id."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/api-keys", json={"label": "Delete Me"})
        prefix = r.json().get("prefix")
        # Find the key by prefix in GET response
        r2 = await client.get(f"{BASE}/api/settings/api-keys")
        key = next((k for k in r2.json().get("keys", []) if k["prefix"] == prefix), None)
        assert key is not None
        key_id = key["id"]
        await client.delete(f"{BASE}/api/settings/api-keys/{key_id}")
        r3 = await client.get(f"{BASE}/api/settings/api-keys")
        deleted = next((k for k in r3.json().get("keys", []) if k["id"] == key_id), None)
        assert deleted is None
