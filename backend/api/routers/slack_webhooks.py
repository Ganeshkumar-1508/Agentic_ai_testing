"""Slack-compatible incoming webhook (Q1+Q2+Q4 — minimal Slack integration).

The full Slack bot (Socket Mode, slash commands, DM parsing, OAuth)
is a follow-up. This file ships the *minimum* surface that lets a
Slack workspace trigger TestAI jobs via an outgoing webhook URL.

Two endpoints, both POST:

  POST /api/webhooks/slack/events
    Accepts Slack Events API payloads. Looks for messages that
    mention `@testai` (or `TestAI`) and submits a tier-1 job with
    the message text as the prompt. The response is the
    Slack-required 200 OK within 3 seconds (the actual run is
    spawned in the background).

  POST /api/webhooks/slack/commands
    Accepts Slack slash-command payloads (`Content-Type:
    application/x-www-form-urlencoded`). Recognizes:
      /testai fix <issue_number>          — submit tier-1 fix
      /testai review <pr_url_or_number>   — submit tier-2 review
      /testai <free-form prompt>          — submit tier-1 job
    Parses `application/x-www-form-urlencoded` (Slack's native
    format for slash commands). Returns a 200 with `{"text": "..."}`
    so Slack renders the response inline.

Verification: both endpoints check Slack's `X-Slack-Signature`
header against `SLACK_SIGNING_SECRET` using HMAC-SHA256. Fail-closed
when the env var is unset.

Reference: `reference/hermes-agent/gateway/platforms/slack.py` is
the deep version. This file is the shallow "single surface" version
that works with Slack's "Outgoing Webhooks" or "Event Subscriptions"
without OAuth, and is sufficient to demonstrate the trigger.

Run mode:
  - Slack workspace -> Apps -> Outgoing Webhooks OR Event Subscriptions
  - URL = https://<testai-host>/api/webhooks/slack/events
  - Or for slash commands, URL = /api/webhooks/slack/commands
  - Signing secret = SLACK_SIGNING_SECRET env var
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()


def _signing_secret() -> str:
    return os.environ.get("SLACK_SIGNING_SECRET", "").strip()


def _verify_slack_signature(
    body: bytes, timestamp: str, signature: str, secret: str,
) -> bool:
    """Slack signature verification (HMAC-SHA256 over `v0:{ts}:{body}`).

    Reference: https://api.slack.com/authentication/verifying-requests-from-slack
    Header format: `v0=<hex>`. Constant-time compare.
    Reject if timestamp is more than 5 minutes off (replay protection).
    """
    if not secret or not timestamp or not signature:
        return False
    if not signature.startswith("v0="):
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > 300:
        return False
    sig_basestring = f"v0:{timestamp}:".encode("utf-8") + body
    expected = "v0=" + hmac.new(
        secret.encode("utf-8"), sig_basestring, hashlib.sha256
    ).hexdigest()
    provided = signature
    return hmac.compare_digest(provided, expected)


async def _submit_testai_job(
    request: Request, *, prompt: str, repo_url: str, tier: int,
    source_label: str, capabilities: list[str] | None = None,
) -> dict:
    """Build a JobSpec + spawn the orchestrator (shared by both
    Slack endpoints + the generic webhook). Returns the queued
    payload (run_id, spec_id, tier, source).
    """
    import asyncio
    import uuid as _uuid
    from harness.jobs.spec import JobSpec
    from harness.orchestrator import OrchestratorEngine

    spec = JobSpec.from_chat_submission(
        prompt=prompt,
        repo_url=repo_url,
        branch="main",
        tier=tier,
        capabilities=capabilities or ["read", "write", "test"],
        session_id=f"slack-{_uuid.uuid4()}",
        agent_id=source_label,
    )

    engine = OrchestratorEngine()

    async def _run_in_background():
        try:
            await engine.run_job_spec(spec)
        except Exception as exc:
            logger.warning(
                "Slack TestAI run failed run_id=%s: %s", spec.run_id, exc,
            )

    try:
        asyncio.create_task(_run_in_background())
    except RuntimeError:
        pass
    return {
        "status": "queued",
        "run_id": spec.run_id,
        "tier": tier,
        "source": source_label,
    }


@router.post("/api/webhooks/slack/events")
async def slack_events(request: Request) -> dict:
    """Slack Events API. Looks for `@testai ...` mentions and submits."""
    secret = _signing_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="slack events disabled — set SLACK_SIGNING_SECRET",
        )
    raw = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(raw, timestamp, signature, secret):
        raise HTTPException(status_code=401, detail="invalid slack signature")

    import json
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    # URL verification handshake: Slack sends a one-shot challenge
    # when the Events URL is first registered. Echo it back so the
    # URL is verified.
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    if body.get("type") != "event_callback":
        return {"status": "ignored", "reason": "not an event_callback"}

    event = body.get("event", {}) or {}
    event_type = event.get("type", "")
    text = event.get("text", "") or ""
    # Only act on channel messages or DMs that mention the bot.
    # Bot user id is set when the workspace installs the app; for
    # the simpler "Outgoing Webhook" flow, we match on the literal
    # string `@testai` (case-insensitive) in the text.
    if event_type not in ("message", "app_mention"):
        return {"status": "ignored", "reason": f"event_type={event_type}"}
    if "@testai" not in text.lower() and "testai" not in text.lower():
        return {"status": "ignored", "reason": "no @testai mention"}

    # Strip the mention. The bot's display name is "TestAI" by
    # convention; users may write `@TestAI` or `@testai`.
    prompt = text
    for needle in ("<@U_TESTAI_BOT> ", "@TestAI ", "@testai "):
        if prompt.lower().startswith(needle.lower()):
            prompt = prompt[len(needle):]
            break

    if not prompt.strip():
        return {"status": "ignored", "reason": "empty prompt after mention"}

    channel = event.get("channel", "(unknown)")
    user = event.get("user", "(unknown)")
    resp = await _submit_testai_job(
        request,
        prompt=prompt,
        repo_url="",  # user didn't specify a repo; agent must ask
        tier=1,       # Q3: Slack = tier 1 (user asked for it)
        source_label=f"slack:event:{channel}:{user}",
        capabilities=["read", "write", "test", "run_tests"],
    )
    return {"status": "ok", "slack_reply": "queued", "testai": resp}


@router.post("/api/webhooks/slack/commands")
async def slack_commands(request: Request) -> dict:
    """Slack slash commands (`/testai ...`). application/x-www-form-urlencoded.

    Recognized forms:
      /testai fix <issue_number>          — tier 1
      /testai review <pr_number>          — tier 2
      /testai <free-form text>            — tier 1
    """
    secret = _signing_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="slack commands disabled — set SLACK_SIGNING_SECRET",
        )
    raw = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(raw, timestamp, signature, secret):
        raise HTTPException(status_code=401, detail="invalid slack signature")

    # Slack sends slash commands as application/x-www-form-urlencoded
    try:
        text_body = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid encoding: {exc}")
    parsed = parse_qs(text_body)
    def _first(key: str) -> str:
        v = parsed.get(key, [""])
        return v[0] if v else ""
    command = _first("command")
    text = _first("text")
    user = _first("user_name")
    channel = _first("channel_name")
    if not command.startswith("/testai"):
        return {"response_type": "ephemeral", "text": f"unknown command: {command}"}

    parts = (text or "").split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if sub == "fix":
        issue_number = rest.strip().lstrip("#")
        prompt = f"Fix issue #{issue_number} on the connected repo. {rest}"
        resp = await _submit_testai_job(
            request, prompt=prompt, repo_url="", tier=1,
            source_label=f"slack:cmd:fix:{user}:{channel}",
            capabilities=["read", "write", "test", "run_tests", "open_pr"],
        )
        text_reply = f"Queued fix for issue #{issue_number}: run_id={resp.get('run_id', '?')}"
    elif sub == "review":
        pr_ref = rest.strip().lstrip("#")
        prompt = f"Review PR #{pr_ref} on the connected repo. {rest}"
        resp = await _submit_testai_job(
            request, prompt=prompt, repo_url="", tier=2,
            source_label=f"slack:cmd:review:{user}:{channel}",
            capabilities=["read", "write", "test", "run_tests"],
        )
        text_reply = f"Queued review for PR #{pr_ref}: run_id={resp.get('run_id', '?')}"
    elif sub:
        # Free-form: treat as a prompt
        prompt = rest or sub
        resp = await _submit_testai_job(
            request, prompt=prompt, repo_url="", tier=1,
            source_label=f"slack:cmd:{user}:{channel}",
            capabilities=["read", "write", "test", "run_tests"],
        )
        text_reply = f"Queued: run_id={resp.get('run_id', '?')}"
    else:
        return {
            "response_type": "ephemeral",
            "text": "Usage: /testai fix <#issue>, /testai review <#pr>, or /testai <prompt>",
        }

    return {"response_type": "in_channel", "text": text_reply}
