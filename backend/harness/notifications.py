"""Multi-channel notification system — Slack, Email, Webhook alerts.

Triggers on events: session.completed, session.failed, budget.alert,
flaky.quarantine, pipeline.failed.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

EVENT_FORMATS: dict[str, dict] = {
    "session.completed": {
        "emoji": "✅",
        "title": "Pipeline completed",
        "color": "good",
    },
    "session.failed": {
        "emoji": "❌",
        "title": "Pipeline failed",
        "color": "danger",
    },
    "budget.alert": {
        "emoji": "💰",
        "title": "Budget alert",
        "color": "warning",
    },
    "flaky.quarantine": {
        "emoji": "🔄",
        "title": "Test quarantined",
        "color": "warning",
    },
    "pipeline.started": {
        "emoji": "▶️",
        "title": "Pipeline started",
        "color": "#36a64f",
    },
}

_NOTIFY_HANDLERS: dict[str, list[callable]] = {}


def register_handler(event_type: str, handler: callable) -> None:
    _NOTIFY_HANDLERS.setdefault(event_type, []).append(handler)


def build_slack_payload(event_type: str, data: dict) -> dict:
    fmt = EVENT_FORMATS.get(event_type, {"emoji": "ℹ️", "title": event_type, "color": "#cccccc"})
    fields = []
    for k, v in data.items():
        if isinstance(v, (int, float)):
            fields.append({"title": k.replace("_", " ").title(), "value": str(v), "short": True})
        elif isinstance(v, str) and len(v) < 100:
            fields.append({"title": k.replace("_", " ").title(), "value": v, "short": True})

    return {
        "attachments": [{
            "color": fmt["color"],
            "title": f"{fmt['emoji']} {fmt['title']}",
            "fields": fields,
            "footer": "TestAI",
            "ts": int(__import__("time").time()),
        }]
    }


def build_email_body(event_type: str, data: dict) -> str:
    fmt = EVENT_FORMATS.get(event_type, {"emoji": "ℹ️", "title": event_type})
    lines = [f"Subject: {fmt['emoji']} {fmt['title']}", ""]
    for k, v in data.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


async def send_slack(webhook_url: str, payload: dict) -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(webhook_url, json=payload)
            return r.status_code == 200
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)
        return False


async def send_webhook(url: str, payload: dict) -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json=payload, headers={"Content-Type": "application/json"})
            return r.status_code in (200, 201, 202, 204)
    except Exception as e:
        logger.warning("Webhook notification failed: %s", e)
        return False


async def dispatch(event_type: str, data: dict, db=None) -> None:
    """Dispatch a notification event to all configured channels."""
    try:
        if db:
            configs = await db.fetch(
                "SELECT * FROM webhook_configs WHERE enabled = true"
            )
            for cfg in configs:
                url = cfg.get("url", "")
                if not url:
                    continue
                event_filter = json.loads(cfg.get("events", "[]")) if isinstance(cfg.get("events"), str) else cfg.get("events", [])
                if event_filter and event_type not in event_filter:
                    continue

                payload = build_slack_payload(event_type, data)
                await send_webhook(url, payload)
    except Exception as e:
        logger.warning("Notification dispatch failed: %s", e)
