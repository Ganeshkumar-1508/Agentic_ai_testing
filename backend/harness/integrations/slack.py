"""Slack message sender — posts Block Kit messages using the stored bot token.

Called by the pipeline after a run completes to post results back to Slack.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

SLACK_API = "https://slack.com/api"


async def _get_bot_token() -> str | None:
    """Read the stored Slack bot token from integration_configs."""
    from ..deps import get_db
    from fastapi import Request
    # This is called from context where we don't have a request object.
    # We use a direct DB query via a helper.
    try:
        from harness.db_helpers import get_db_direct
        db = await get_db_direct()
        row = await db.fetchrow(
            "SELECT config FROM integration_configs WHERE platform = 'slack' AND enabled = true LIMIT 1",
        )
        if row:
            config = row["config"]
            if isinstance(config, str):
                config = json.loads(config)
            return config.get("bot_token")
    except Exception:
        pass
    return None


async def post_slack_message(
    channel: str,
    text: str,
    blocks: list[dict] | None = None,
    thread_ts: str | None = None,
) -> bool:
    """Post a message to a Slack channel using the stored bot token."""
    token = await _get_bot_token()
    if not token:
        return False

    payload: dict[str, Any] = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API}/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        data = resp.json()
        return data.get("ok", False)


async def post_run_result_to_slack(
    channel: str,
    thread_ts: str,
    run_id: str,
    status: str,
    test_count: int = 0,
    passed: int = 0,
    failed: int = 0,
    pr_url: str | None = None,
    duration_s: float = 0,
    cost_usd: float = 0,
):
    """Post a formatted run result message to a Slack thread."""
    status_emoji = {"completed": "\u2705", "failed": "\u274c", "running": "\U0001f50e", "pending": "\u23f3"}
    emoji = status_emoji.get(status, "\u2753")
    pass_rate = f"{round(passed / test_count * 100)}%" if test_count > 0 else "N/A"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *Pipeline {status}*",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "value": f"*Tests:* {test_count}"},
                {"type": "mrkdwn", "value": f"*Passed:* {passed}"},
                {"type": "mrkdwn", "value": f"*Failed:* {failed}"},
                {"type": "mrkdwn", "value": f"*Pass Rate:* {pass_rate}"},
                {"type": "mrkdwn", "value": f"*Duration:* {duration_s:.1f}s"},
                {"type": "mrkdwn", "value": f"*Cost:* ${cost_usd:.2f}"},
            ],
        },
    ]

    if pr_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Pull Request"},
                    "url": pr_url,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Run"},
                    "url": f"/history/{run_id}",
                    "action_id": "view_run",
                },
            ],
        })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Run `{run_id[:8]}`"},
        ],
    })

    return await post_slack_message(channel, f"Pipeline {status}: {passed}/{test_count} tests passed", blocks, thread_ts)
