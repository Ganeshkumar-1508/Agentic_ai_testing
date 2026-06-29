"""SendMessage tool — inter-agent communication + external channel delivery.

Inter-agent: orchestrator sends messages to subagent sessions.
External: delivers messages to Slack, email, or webhook via integration_configs.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry, any_env_available


async def _get_db() -> Any:
    """Get a database connection for background operations."""
    from harness.db_helpers import get_db_direct
    return await get_db_direct()


async def _get_integration_config(platform: str) -> dict | None:
    """Fetch integration config from the DB."""
    try:
        db = await _get_db()
        row = await db.fetchrow(
            "SELECT config FROM integration_configs WHERE platform = $1 AND enabled = true LIMIT 1",
            platform,
        )
        if row:
            cfg = row["config"]
            return json.loads(cfg) if isinstance(cfg, str) else cfg
    except Exception:
        pass
    return None


async def _save_notification(channel: str, recipient: str, subject: str, body: str, status: str, run_id: str = "", error: str = "") -> str:
    """Persist a notification record."""
    notif_id = str(uuid.uuid4())
    try:
        db = await _get_db()
        await db.execute(
            "INSERT INTO notifications (id, channel, recipient, subject, body, status, error, run_id, delivered_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            notif_id, channel, recipient, subject, body, status, error, run_id,
            datetime.now(timezone.utc) if status == "delivered" else None,
        )
    except Exception:
        pass
    return notif_id


async def _deliver_slack(channel: str, subject: str, body: str) -> tuple[bool, str]:
    """Deliver a message to Slack via bot token."""
    config = await _get_integration_config("slack")
    if not config:
        return False, "Slack not configured. Go to Settings > Integrations > Slack to set it up."

    token = config.get("bot_token")
    if not token:
        return False, "Slack bot token not found in integration config."

    target = channel if channel.startswith("#") or channel.startswith("@") else config.get("default_channel", "#general")
    text = f"*{subject}*\n\n{body[:3000]}"

    try:
        import httpx
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"channel": target, "text": text, "mrkdwn": True},
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            return True, f"Delivered to Slack channel {target}"
        return False, f"Slack API error: {data.get('error', 'unknown')}"
    except Exception as e:
        return False, str(e)


async def _deliver_webhook(url: str, subject: str, body: str) -> tuple[bool, str]:
    """Deliver a message to a generic webhook URL."""
    try:
        import httpx
        payload = {"subject": subject, "body": body, "source": "testai", "timestamp": datetime.now(timezone.utc).isoformat()}
        resp = httpx.post(url, json=payload, timeout=15)
        if resp.is_success:
            return True, f"Delivered to webhook ({resp.status_code})"
        return False, f"Webhook returned {resp.status_code}"
    except Exception as e:
        return False, str(e)


class SendMessageTool(BaseTool):
    name = "send_message"
    description = "Send a message to an agent session or to an external channel (Slack, webhook). For inter-agent use 'to' with a session ID. For external delivery use 'channel' (slack, webhook) with 'subject' and 'body'."
    default_level = "allow"

    _active_messages: dict[str, list[dict[str, Any]]] = {}

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Agent session ID (for inter-agent messaging)"},
                    "message": {"type": "string", "description": "Message content (for inter-agent)"},
                    "channel": {"type": "string", "description": "External channel: 'slack', 'webhook', or a URL starting with http"},
                    "subject": {"type": "string", "description": "Message subject/title (for external delivery)"},
                    "body": {"type": "string", "description": "Message body content (for external delivery)"},
                    "recipient": {"type": "string", "description": "Slack channel (#general) or webhook URL override"},
                    "run_id": {"type": "string", "description": "Optional run ID to associate with the notification"},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        # Inter-agent messaging
        to = kwargs.get("to", "")
        message = kwargs.get("message", "")
        if to and message:
            self._active_messages.setdefault(to, []).append({
                "from": "orchestrator",
                "content": message,
                "timestamp": __import__("time").time(),
            })
            await _save_notification("agent", to, "", message, "delivered")
            return ToolResult(success=True, output=f"Message sent to agent '{to}'.")

        # External delivery
        channel = kwargs.get("channel", "")
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        recipient = kwargs.get("recipient", "")
        run_id = kwargs.get("run_id", "")

        if not channel:
            return ToolResult(success=False, output="Provide 'to' + 'message' for inter-agent, or 'channel' + 'subject' + 'body' for external delivery.")

        success = False
        result_msg = ""

        if channel == "slack":
            success, result_msg = await _deliver_slack(recipient, subject, body)
        elif channel == "webhook" or channel.startswith("http"):
            url = channel if channel.startswith("http") else recipient
            success, result_msg = await _deliver_webhook(url, subject, body)
        else:
            return ToolResult(success=False, output=f"Unknown channel '{channel}'. Supported: slack, webhook, or HTTP URL.")

        status = "delivered" if success else "failed"
        notif_id = await _save_notification(channel, recipient, subject, body, status, run_id, error="" if success else result_msg)

        if success:
            return ToolResult(success=True, output=result_msg, data={"notification_id": notif_id})
        return ToolResult(success=False, output=result_msg, data={"notification_id": notif_id})

    @classmethod
    def get_messages(cls, session_id: str) -> list[dict[str, Any]]:
        return cls._active_messages.get(session_id, [])

    @classmethod
    def clear_messages(cls, session_id: str) -> None:
        cls._active_messages.pop(session_id, None)


registry.register(SendMessageTool(), toolset="delegate", check_fn=any_env_available("SLACK_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"))
