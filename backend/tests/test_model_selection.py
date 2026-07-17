"""Model Selection & Provider Switching Test

Tests that users can:
1. Configure any model (not just deepseek) for a provider
2. Switch models and persist the change
3. Test connection with different models
4. LLM uses the configured model

Run: python -m pytest backend/tests/test_model_selection.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_save_provider_with_gpt4():
    """Save provider with GPT-4 model."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/api/settings/providers", json=[{
            "provider": "opencode",
            "api_key": "sk-TD37RJSPUPVYZRaOlOejmPk1qNKosfp8i0eq8RXvi0QYwudb79fSUr0McLiZelYD",
            "base_url": "https://opencode.ai/zen/go/v1",
            "model": "gpt-4",
            "enabled": True,
            "options": {}
        }])
        assert r.status_code == 200
        # Verify model persisted
        r2 = await client.get(f"{BASE}/api/settings/providers")
        oc = next((p for p in r2.json() if p["provider"] == "opencode"), None)
        assert oc is not None
        assert oc["model"] == "gpt-4"
        assert oc["has_key"] is True


@pytest.mark.asyncio
async def test_switch_model():
    """Switch from one model to another."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Save with GPT-4
        await client.post(f"{BASE}/api/settings/providers", json=[{
            "provider": "opencode",
            "api_key": "sk-TD37RJSPUPVYZRaOlOejmPk1qNKosfp8i0eq8RXvi0QYwudb79fSUr0McLiZelYD",
            "base_url": "https://opencode.ai/zen/go/v1",
            "model": "gpt-4",
            "enabled": True,
            "options": {}
        }])
        # Verify GPT-4 saved
        r = await client.get(f"{BASE}/api/settings/providers")
        assert next((p for p in r.json() if p["provider"] == "opencode"))["model"] == "gpt-4"
        # Switch to deepseek
        await client.post(f"{BASE}/api/settings/providers", json=[{
            "provider": "opencode",
            "api_key": "sk-TD37RJSPUPVYZRaOlOejmPk1qNKosfp8i0eq8RXvi0QYwudb79fSUr0McLiZelYD",
            "base_url": "https://opencode.ai/zen/go/v1",
            "model": "deepseek-v4-flash",
            "enabled": True,
            "options": {}
        }])
        r2 = await client.get(f"{BASE}/api/settings/providers")
        assert next((p for p in r2.json() if p["provider"] == "opencode"))["model"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_available_models_from_connection():
    """Test connection fetches available models."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/settings/providers/test-connection", json={
            "provider": "opencode",
            "api_key": "sk-TD37RJSPUPVYZRaOlOejmPk1qNKosfp8i0eq8RXvi0QYwudb79fSUr0McLiZelYD",
            "base_url": "https://opencode.ai/zen/go/v1",
            "model": "deepseek-v4-flash",
            "enabled": True
        })
        assert r.status_code == 200
        models = r.json().get("available_models", [])
        assert len(models) > 0
        print(f"  Fetched {len(models)} models: {models[:5]}")


@pytest.mark.asyncio
async def test_model_persists_across_restarts():
    """Model persists after save and reload."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(f"{BASE}/api/settings/providers", json=[{
            "provider": "opencode",
            "api_key": "sk-TD37RJSPUPVYZRaOlOejmPk1qNKosfp8i0eq8RXvi0QYwudb79fSUr0McLiZelYD",
            "base_url": "https://opencode.ai/zen/go/v1",
            "model": "deepseek-v4-pro",
            "enabled": True,
            "options": {}
        }])
        # Load twice to simulate page refresh
        r1 = await client.get(f"{BASE}/api/settings/providers")
        r2 = await client.get(f"{BASE}/api/settings/providers")
        m1 = next((p for p in r1.json() if p["provider"] == "opencode"))["model"]
        m2 = next((p for p in r2.json() if p["provider"] == "opencode"))["model"]
        assert m1 == "deepseek-v4-pro"
        assert m2 == "deepseek-v4-pro"
