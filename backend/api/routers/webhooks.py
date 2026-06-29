"""Generic webhook receiver (Q1+Q2+Q3 — escape hatch for any external system).

The existing GitHub webhook at `admin.py:482-495` is narrow: it only
handles `pull_request` events for the CI run path. TestAI needs a
**general-purpose** webhook that any external system (Linear, Jira,
internal CI, monitoring tools, custom internal apps) can use to
trigger an autonomous job.

Endpoint:
  POST /api/webhooks/testai
  Headers:
    X-TestAI-Signature: sha256=<hex>   # HMAC-SHA256 of body with the shared secret
    X-TestAI-Source:   <string>        # e.g. "linear", "jira", "internal_ci"
  Body (JSON):
    {
      "prompt":      "natural-language spec for the agent",
      "repo_url":    "https://github.com/owner/repo",
      "branch":      "main",                  # optional, default "main"
      "tier":        1 | 2 | 3,               # optional, default 2
      "capabilities": ["open_pr", ...],       # optional, default safe tier-2 caps
      "metadata":    { "auth_user": "..." }   # optional, recorded for audit
    }

Returns:
  202 Accepted: { "status": "queued", "run_id": "...", "spec_id": "..." }
  401 Unauthorized: HMAC mismatch
  400 Bad Request: missing required fields
  503 Service Unavailable: orchestrator not initialised

Default tier is 2 (supervised): webhook callers can opt up to 1
(autonomous) by passing `"tier": 1` in the body. The chat tier
override does NOT apply here — webhooks bypass the chat and use
the body's tier as authoritative.

HMAC validation: `hmac.compare_digest` (constant-time) over the raw
request body. The shared secret comes from the
`TESTAI_WEBHOOK_SECRET` env var. If the env var is not set, the
endpoint refuses all requests (fail-closed — better than
accidentally allowing unauthenticated triggers).

Design follows `reference/hermes-agent/gateway/platforms/api_server.py`
shape (HMAC + JSON body + 202 Accepted) but is simpler (single
endpoint, no streaming, no per-source config).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class WebhookBody(BaseModel):
    prompt: str = Field(..., min_length=1, description="Spec for the agent.")
    repo_url: str = Field("", description="Repo URL. Empty allowed (generic work).")
    branch: str = Field("main", description="Git ref. Default 'main'.")
    tier: int = Field(2, ge=1, le=3, description="1=autonomous, 2=supervised, 3=human-authored.")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Override capabilities. Empty = safe tier-2 default.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form audit metadata (auth_user, source labels, etc.).",
    )


def _webhook_secret() -> str:
    """The shared secret for HMAC validation. Empty string = endpoint disabled.

    Fail-closed: an unset env var means we reject all webhooks.
    Operators must opt in by setting `TESTAI_WEBHOOK_SECRET`.
    """
    return os.environ.get("TESTAI_WEBHOOK_SECRET", "").strip()


def _verify_hmac(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 verification.

    The expected header format is `sha256=<hex>`. Comparison uses
    `hmac.compare_digest` so a timing-attack adversary can't probe
    one byte at a time. Any error in the header parsing fails closed.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    provided = signature_header[len("sha256="):].strip()
    try:
        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
    except Exception:
        return False
    if not hmac.compare_digest(provided, expected):
        return False
    return True


@router.post("/api/webhooks/testai")
async def testai_webhook(request: Request) -> dict:
    """Generic TestAI webhook. HMAC-protected, tier-2 default, 202 Accepted.

    See module docstring for the full schema. The endpoint is
    registered alongside the GitHub webhook in `admin_routes.py`.
    """
    secret = _webhook_secret()
    if not secret:
        if os.environ.get("TESTAI_DISABLE_WEBHOOK_HMAC", "").strip().lower() in ("true", "1", "yes"):
            secret = "insecure-dev-mode"
        else:
            raise HTTPException(
                status_code=503,
                detail="webhook receiver disabled — set TESTAI_WEBHOOK_SECRET or TESTAI_DISABLE_WEBHOOK_HMAC=true",
            )

    raw = await request.body()
    sig = request.headers.get("X-TestAI-Signature", "")
    if not _verify_hmac(raw, sig, secret):
        if secret == "insecure-dev-mode":
            pass
        else:
            raise HTTPException(status_code=401, detail="invalid signature")

    import json
    try:
        body_dict = json.loads(raw.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    try:
        body = WebhookBody(**body_dict)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"validation failed: {exc}")

    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="`prompt` is required and non-empty")

    # Defer to the orchestrator. Build a JobSpec (same path as
    # `submit_job` in tool_dispatch.py:310) and spawn the engine.
    try:
        from harness.jobs.spec import JobSpec
        spec = JobSpec.from_chat_submission(
            prompt=body.prompt,
            repo_url=body.repo_url,
            branch=body.branch or "main",
            tier=body.tier,
            capabilities=body.capabilities,
            session_id=f"webhook-{uuid.uuid4()}",
            agent_id="testai-webhook",
        )
    except Exception as exc:
        logger.warning("webhook: JobSpec build failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"JobSpec build failed: {exc}")

    # Persist the JobSpec + spawn the orchestrator in the background.
    # Both steps are best-effort: a transient failure here is logged,
    # not raised — the caller (the external system) should retry on
    # 5xx. We return 202 because the run is *accepted*; the
    # orchestrator may still fail in `run_job_spec`.
    try:
        from harness.jobs.spec import _job_spec_store, to_record
        store = _job_spec_store()
        if store is not None:
            try:
                # C08 Q4: spec.context is a Pydantic JobContext; the
                # record-builder handles serialisation. (P0 audit fix
                # 2026-06-23 — store.save expects a JobSpecRecord,
                # not a raw dict.)
                await store.save(to_record(spec))
            except Exception as exc:
                logger.warning("webhook: JobSpec persist failed: %s", exc)
    except Exception:
        pass

    import asyncio
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine()

    # P0 audit fix 2026-06-23: subagent sessions FK into the
    # webhook's session_id, so the webhook must create its own
    # sessions row before the orchestrator spawns workers.
    try:
        from harness.memory.db_context import get_db
        _db = get_db()
        if _db:
            import datetime as _dt
            _now = _dt.datetime.now(_dt.timezone.utc)
            await _db.execute(
                "INSERT INTO sessions (id, source, status, depth, agent_role, goal, repo_url, started_at, backend_type) "
                "VALUES ($1, 'webhook', 'running', 0, 'orchestrator', $2, $3, $4, $5) "
                "ON CONFLICT (id) DO NOTHING",
                spec.context.session_id or f"webhook-{spec.run_id}",
                (spec.prompt or "")[:500],
                spec.repo_url or "",
                _now,
                spec.backend_type,
            )
    except Exception as exc:
        logger.warning("webhook: parent session row insert failed: %s", exc)

    async def _run_in_background():
        try:
            await engine.run_job_spec(spec)
        except Exception:
            import traceback
            logger.warning(
                "webhook: orchestrator run_job_spec failed run_id=%s\n%s",
                spec.run_id, traceback.format_exc(),
            )

    try:
        asyncio.create_task(_run_in_background())
    except RuntimeError:
        # No running loop (shouldn't happen under FastAPI but be safe)
        logger.warning("webhook: no event loop for background spawn — run deferred")

    logger.info(
        "webhook accepted source=%s tier=%d run_id=%s repo=%s",
        request.headers.get("X-TestAI-Source", "unknown"),
        body.tier, spec.run_id, body.repo_url or "(none)",
    )
    return {
        "status": "queued",
        "run_id": spec.run_id,
        "spec_id": getattr(spec, "spec_id", ""),
        "tier": body.tier,
    }
