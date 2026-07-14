"""Notification Preferences API Test

Tests the full CRUD flow for notification preferences including
the target field fix (Slack URL, email, webhook URL persistence).

Run: docker exec testai-backend python -m pytest tests/test_notification_pref.py -v
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_save_slack_notification_with_target():
    """Save a Slack notification with target channel."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "slack",
            "enabled": True,
            "events": ["run:completed", "test:failed"],
            "target": "#dev-alerts"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_save_email_notification_with_target():
    """Save an email notification with target address."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "email",
            "enabled": True,
            "events": ["agent:error"],
            "target": "user@example.com"
        })
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_save_webhook_notification_with_target():
    """Save a webhook notification with target URL."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "webhook",
            "enabled": False,
            "events": ["pipeline:started"],
            "target": "https://hooks.slack.com/xxx"
        })
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_target_persists_after_load():
    """Target field persists when loaded from DB."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/api/settings/notification-prefs")
        prefs = r.json().get("preferences", [])
        slack = next((p for p in prefs if p["channel"] == "slack"), None)
        email = next((p for p in prefs if p["channel"] == "email"), None)
        webhook = next((p for p in prefs if p["channel"] == "webhook"), None)
        assert slack["target"] == "#dev-alerts"
        assert email["target"] == "user@example.com"
        assert webhook["target"] == "https://hooks.slack.com/xxx"


@pytest.mark.asyncio
async def test_update_target():
    """Update a notification's target field."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "slack", "enabled": True,
            "events": ["run:completed"], "target": "#old-channel"
        })
        await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "slack", "enabled": True,
            "events": ["run:completed"], "target": "#new-channel"
        })
        r = await client.get(f"{BASE}/api/settings/notification-prefs")
        slack = next((p for p in r.json().get("preferences", []) if p["channel"] == "slack"), None)
        assert slack["target"] == "#new-channel"


@pytest.mark.asyncio
async def test_delete_notification():
    """Delete a notification preference."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/settings/notification-prefs", json={
            "channel": "delete-me", "enabled": True, "events": [], "target": "test"
        })
        assert r.status_code == 200
        # Get the id from the saved record
        r2 = await client.get(f"{BASE}/api/settings/notification-prefs")
        saved = next((p for p in r2.json().get("preferences", []) if p["channel"] == "delete-me"), None)
        assert saved is not None
        pref_id = saved["id"]
        # Delete by id
        r3 = await client.delete(f"{BASE}/api/settings/notification-prefs/{pref_id}")
        assert r3.status_code == 200
        # Verify deleted
        r4 = await client.get(f"{BASE}/api/settings/notification-prefs")
        deleted = next((p for p in r4.json().get("preferences", []) if p["channel"] == "delete-me"), None)
        assert deleted is None
