"""Plugin Manager CRUD Test

Tests plugin management endpoints:
- List plugins
- Enable/Disable plugin
- Uninstall plugin

Run: python -m pytest backend/tests/test_plugin_manager.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_list_plugins():
    """List plugins returns 200 with plugins array."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/api/ops/plugins")
        assert r.status_code == 200
        assert "plugins" in r.json()
        assert isinstance(r.json()["plugins"], list)


@pytest.mark.asyncio
async def test_list_plugins_hooks():
    """List plugin hooks returns 200."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE}/api/ops/plugins/hooks")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_enable_nonexistent_plugin():
    """Enable non-existent plugin returns error."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{BASE}/api/ops/plugins/nonexistent-plugin/enable")
        assert r.status_code == 200
        assert r.json()["status"] == "error"


@pytest.mark.asyncio
async def test_disable_nonexistent_plugin():
    """Disable non-existent plugin returns error."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{BASE}/api/ops/plugins/nonexistent-plugin/disable")
        assert r.status_code == 200
        assert r.json()["status"] == "error"


@pytest.mark.asyncio
async def test_uninstall_nonexistent_plugin():
    """Uninstall non-existent plugin returns error."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.delete(f"{BASE}/api/ops/plugins/nonexistent-plugin")
        assert r.status_code == 200
        assert r.json()["status"] == "error"
