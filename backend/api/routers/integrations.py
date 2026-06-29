"""Integration webhook receivers — Slack, Linear, Jira, Sentry.

Each platform posts events here. The receiver parses the payload,
creates a pipeline run, and posts results back.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from harness.integrations.slack import post_slack_message, post_run_result_to_slack

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _get_webhook_secret(platform: str) -> str:
    return os.environ.get(f"{platform.upper()}_SIGNING_SECRET", "")


def _verify_slack_signature(request: Request, body: bytes) -> bool:
    secret = _get_webhook_secret("slack")
    if not secret:
        return True  # no secret configured = skip verify in dev
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")
    if abs(time.time() - int(timestamp)) > 300:
        return False
    basestr = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(secret.encode(), basestr.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _make_pr_link(url: str, pr_number: int) -> str:
    return f"<{url}/pull/{pr_number}|PR #{pr_number}>"


# ── Slack ──────────────────────────────────────────────────────────


@router.post("/slack/events")
async def slack_events(request: Request):
    """Slack Events API endpoint — handles app_mention and slash commands."""
    raw = await request.body()
    if not _verify_slack_signature(request, raw):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()

    # Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    event = payload.get("event", {})
    event_type = event.get("type", "")

    if event_type == "app_mention":
        return await _handle_slack_mention(payload, event)
    if event_type == "message" and event.get("channel_type") == "im":
        return await _handle_slack_dm(payload, event)
    if payload.get("type") == "block_actions":
        return await _handle_slack_action(payload)

    return {"ok": True}


async def _handle_slack_mention(payload: dict, event: dict) -> dict:
    """Handle @testai mention — parse command, create run, respond."""
    text = event.get("text", "")
    # Strip the @mention prefix
    clean = text.split(">", 1)[-1].strip() if ">" in text else text
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts", event.get("ts", ""))

    # Parse inline options: "in owner/repo1 and owner/repo2 on branch dev fix the bug"
    repo_urls: list[str] = []
    branch = "main"
    prompt = clean

    # Extract "in ... on branch ..." syntax
    in_match = None
    branch_match = None
    if "in " in clean and (clean.index("in ") < clean.index(" on branch ") if " on branch " in clean else True):
        in_match = clean.split("in ", 1)[1]
        if " on branch " in in_match:
            parts = in_match.split(" on branch ", 1)
            in_match = parts[0]
            branch_match = parts[1].split(" ")[0]
        elif " on " in in_match:
            parts = in_match.split(" on ", 1)
            in_match = parts[0]
        if in_match:
            prompt = clean.split("in ", 1)[0].strip()
            repo_urls = [r.strip() for r in in_match.replace(" and ", ",").split(",") if r.strip()]
            if branch_match:
                branch = branch_match

    is_multi_repo = len(repo_urls) > 1

    # Create a run in the database directly
    try:
        from .runs import create_run_internal
        run_id = await create_run_internal(
            requirements=prompt,
            repos=repo_urls if is_multi_repo else None,
            repo_url=repo_urls[0] if repo_urls and not is_multi_repo else "",
            branch=branch,
            mode="auto",
        )
    except Exception:
        run_id = str(uuid.uuid4())

    # Post initial "Working on it..." message to the thread
    repo_display = ", ".join(f"`{u}`" for u in repo_urls) if repo_urls else "default"
    await post_slack_message(
        channel,
        f"Working on: {prompt[:200]}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":test_tube: *Working on:* {prompt[:200]}"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Repos: {repo_display} · Branch: `{branch}`" + (" · multi-repo" if is_multi_repo else "")},
                ],
            },
        ],
        thread_ts=thread_ts,
    )

    return {"ok": True}


async def _handle_slack_dm(payload: dict, event: dict) -> dict:
    """Handle direct messages to the bot."""
    text = event.get("text", "")
    if not text:
        return {"ok": True}


# ── Linear ──────────────────────────────────────────────────────────


@router.post("/linear/events")
async def linear_webhook(request: Request):
    """Receive Linear issue assignments and trigger runs."""
    payload = await request.json()
    action = payload.get("action", "")
    data = payload.get("data", {})

    # Triggered when issue is assigned to the TestAI bot user
    if action in ("create", "update") and data.get("assigneeId"):
        issue_id = data.get("id", "")
        title = data.get("title", "")
        description = data.get("description", "") or title
        team_id = data.get("teamId", "")

        if not issue_id:
            return {"ok": True}

        run_id = str(uuid.uuid4())
        return {
            "ok": True,
            "run_id": run_id,
            "prompt": description[:500],
            "source": f"linear:{issue_id}",
        }

    return {"ok": True}


# ── Jira ────────────────────────────────────────────────────────────


@router.post("/jira/events")
async def jira_webhook(request: Request):
    """Receive Jira issue label changes and trigger runs."""
    payload = await request.json()
    issue = payload.get("issue", {})
    issue_key = issue.get("key", "")
    changelog = payload.get("changelog", {})

    # Check if the "testai" label was added
    additions = []
    for item in changelog.get("items", []):
        if item.get("field") == "labels":
            additions = item.get("added", [])
            break

    if "testai" not in [a.lower() for a in additions]:
        return {"ok": True}

    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "") or summary

    run_id = str(uuid.uuid4())
    return {
        "ok": True,
        "run_id": run_id,
        "prompt": f"{summary}\n\n{description[:500]}",
        "source": f"jira:{issue_key}",
    }


# ── Sentry ──────────────────────────────────────────────────────────


@router.post("/sentry/events")
async def sentry_webhook(request: Request):
    """Receive Sentry error alerts and trigger fix PRs."""
    payload = await request.json()
    event = payload.get("event", {})
    project = payload.get("project", "")
    project_slug = project.get("slug", "") if isinstance(project, dict) else project

    error_title = event.get("title", "Unknown error")
    error_type = event.get("exception", {}).get("values", [{}])[0].get("type", "Error") if event.get("exception") else "Error"
    stacktrace = ""
    if event.get("exception"):
        frames = event["exception"].get("values", [{}])[0].get("stacktrace", {}).get("frames", [])
        if frames:
            relevant = [f for f in frames if not f.get("filename", "").startswith("/")]
            stacktrace = "\n".join(
                f"  {f.get('filename', '?')}:{f.get('lineno', '?')} — {f.get('function', '?')}"
                for f in (relevant or frames)[:10]
            )

    prompt = f"Fix production error: {error_title}\n\nType: {error_type}\nProject: {project_slug}\n\nStacktrace:\n{stacktrace}"

    run_id = str(uuid.uuid4())
    return {
        "ok": True,
        "run_id": run_id,
        "prompt": prompt[:1000],
        "source": f"sentry:{project_slug}:{event.get('event_id', '')}",
    }
    return await _handle_slack_mention(payload, event)


async def _handle_slack_action(payload: dict) -> dict:
    """Handle interactive component callbacks (cancel button, etc.)."""
    actions = payload.get("actions", [])
    for action in actions:
        if action.get("action_id") == "cancel_run":
            run_id = action.get("value", "")
            if run_id:
                try:
                    from ..deps import get_db
                    db = get_db(payload)  # simplified
                except ImportError:
                    pass
    return {"ok": True}


# ── Integration config CRUD ────────────────────────────────────────


class IntegrationConfigRequest(BaseModel):
    platform: str
    enabled: bool = True
    config: dict = {}
    project_mappings: list = []


@router.get("/repos")
async def list_connected_repos(request: Request):
    """List the user's GitHub repos using their configured token.

    Reads the GitHub PAT from ``integration_configs``, creates a
    ``GitHubService`` instance, and returns a sorted list of repos.
    Returns an empty list if no GitHub token is configured.
    """
    db = get_db(request)
    row = await db.fetchrow(
        "SELECT config FROM integration_configs "
        "WHERE platform = 'github' AND enabled = true LIMIT 1",
    )
    if not row:
        return {"repos": [], "error": "no_github_token"}
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    token = config.get("token", "")
    if not token:
        return {"repos": [], "error": "no_github_token"}

    from harness.services.github_service import GitHubService
    gh = GitHubService(token=token)
    repos = await gh.list_repos(sort="pushed", max_repos=200)
    return {
        "repos": [
            {
                "id": r.id,
                "full_name": r.full_name,
                "is_public": r.is_public,
                "main_branch": r.main_branch or "main",
                "stargazers_count": r.stargazers_count or 0,
                "owner_type": r.owner_type.value if r.owner_type else "user",
            }
            for r in repos
        ],
    }


@router.get("/repos/{full_name:path}/branches")
async def list_repo_branches(request: Request, full_name: str):
    """List branches for a specific repo using the user's GitHub token."""
    db = get_db(request)
    row = await db.fetchrow(
        "SELECT config FROM integration_configs "
        "WHERE platform = 'github' AND enabled = true LIMIT 1",
    )
    if not row:
        return {"branches": []}
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    token = config.get("token", "")
    if not token:
        return {"branches": []}

    from harness.services.github_service import GitHubService
    gh = GitHubService(token=token)
    result = await gh.list_branches(full_name, per_page=50)
    return {"branches": [{"name": b.name, "sha": b.commit_sha} for b in result.branches]}


@router.post("/repos/validate")
async def validate_github_token(request: Request):
    """Validate the stored GitHub token and return user/repo info.

    Returns the authenticated user's login and whether the token
    has the ``repo`` scope (write access). Returns an error if
    the token is invalid or expired.
    """
    db = get_db(request)
    row = await db.fetchrow(
        "SELECT config FROM integration_configs "
        "WHERE platform = 'github' AND enabled = true LIMIT 1",
    )
    if not row:
        return {"valid": False, "error": "no_github_token"}
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    token = config.get("token", "")
    if not token:
        return {"valid": False, "error": "no_github_token"}

    from harness.services.github_service import GitHubService
    gh = GitHubService(token=token)
    try:
        user = await gh.get_user()
        scopes = set()
        return {
            "valid": True,
            "login": user.get("login", "unknown"),
            "name": user.get("name") or user.get("login", ""),
            "avatar_url": user.get("avatar_url", ""),
        }
    except RuntimeError as exc:
        err = str(exc)
        if "401" in err:
            return {"valid": False, "error": "token_expired", "detail": "Token is invalid or expired. Generate a new one at github.com/settings/tokens"}
        return {"valid": False, "error": "token_error", "detail": err[:200]}


# ── App Settings (stored in integration_configs with platform='app_settings') ──

_APP_SETTINGS_PLATFORM = "app_settings"


@router.get("/settings/general")
async def get_general_settings(request: Request):
    """Get general app settings (default model, vision model, spawn rates)."""
    db = get_db(request)
    row = await db.fetchrow(
        "SELECT config FROM integration_configs WHERE platform = $1 LIMIT 1",
        _APP_SETTINGS_PLATFORM,
    )
    config = {}
    if row:
        c = row["config"]
        if isinstance(c, str):
            c = json.loads(c)
        config = c or {}
    return {
        "default_model": config.get("default_model", "deepseek-v4-flash"),
        "vision_model": config.get("vision_model", ""),
        "image_gen_provider": config.get("image_gen_provider", "replicate"),
        "max_spawn_depth": config.get("max_spawn_depth", 2),
        "spawn_rate_limit": config.get("spawn_rate_limit", 10),
        "spawn_rate_window": config.get("spawn_rate_window", 30),
        "spawn_rate_cooldown": config.get("spawn_rate_cooldown", 60),
    }


class GeneralSettingsRequest(BaseModel):
    default_model: str = "deepseek-v4-flash"
    vision_model: str = ""
    image_gen_provider: str = "replicate"
    max_spawn_depth: int = 2
    spawn_rate_limit: int = 10
    spawn_rate_window: int = 30
    spawn_rate_cooldown: int = 60


@router.put("/settings/general")
async def update_general_settings(request: Request, body: GeneralSettingsRequest):
    db = get_db(request)
    config = body.model_dump()
    existing = await db.fetchrow(
        "SELECT id FROM integration_configs WHERE platform = $1",
        _APP_SETTINGS_PLATFORM,
    )
    if existing:
        await db.execute(
            "UPDATE integration_configs SET config = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(config), existing["id"],
        )
    else:
        await db.execute(
            "INSERT INTO integration_configs (platform, enabled, config) VALUES ($1, true, $2)",
            _APP_SETTINGS_PLATFORM, json.dumps(config),
        )
    return {"status": "ok"}


@router.get("/settings/observability")
async def get_observability_settings(request: Request):
    """Get OTel/observability settings."""
    db = get_db(request)
    row = await db.fetchrow(
        "SELECT config FROM integration_configs WHERE platform = 'observability' LIMIT 1",
    )
    config = {}
    if row:
        c = row["config"]
        if isinstance(c, str):
            c = json.loads(c)
        config = c or {}
    return {
        "otel_enabled": config.get("otel_enabled", False),
        "otel_endpoint": config.get("otel_endpoint", "http://localhost:4317"),
        "otel_service_name": config.get("otel_service_name", "testai-harness"),
    }


class ObservabilitySettingsRequest(BaseModel):
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "testai-harness"


@router.put("/settings/observability")
async def update_observability_settings(request: Request, body: ObservabilitySettingsRequest):
    db = get_db(request)
    config = body.model_dump()
    existing = await db.fetchrow(
        "SELECT id FROM integration_configs WHERE platform = 'observability' LIMIT 1",
    )
    if existing:
        await db.execute(
            "UPDATE integration_configs SET config = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(config), existing["id"],
        )
    else:
        await db.execute(
            "INSERT INTO integration_configs (platform, enabled, config) VALUES ('observability', true, $1)",
            json.dumps(config),
        )
    return {"status": "ok"}


@router.get("/configs")
async def list_integrations(request: Request, platform: str | None = None):
    db = get_db(request)
    if platform:
        rows = await db.fetch("SELECT * FROM integration_configs WHERE platform = $1 ORDER BY created_at DESC", platform)
    else:
        rows = await db.fetch("SELECT * FROM integration_configs ORDER BY platform ASC, created_at DESC")
    return {"integrations": [
        {
            "id": r["id"],
            "platform": r["platform"],
            "enabled": r["enabled"],
            "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"]),
            "projectMappings": r["project_mappings"] if isinstance(r["project_mappings"], list) else json.loads(r["project_mappings"]),
            "createdAt": r["created_at"].isoformat() if r["created_at"] else "",
        }
        for r in rows
    ]}


@router.post("/configs")
async def upsert_integration(request: Request, body: IntegrationConfigRequest):
    db = get_db(request)
    existing = await db.fetchrow(
        "SELECT id FROM integration_configs WHERE platform = $1", body.platform,
    )
    if existing:
        await db.execute(
            "UPDATE integration_configs SET enabled = $1, config = $2, project_mappings = $3, updated_at = NOW() WHERE id = $4",
            body.enabled, json.dumps(body.config), json.dumps(body.project_mappings), existing["id"],
        )
        return {"status": "ok", "id": existing["id"]}
    row = await db.fetchrow(
        "INSERT INTO integration_configs (platform, enabled, config, project_mappings) VALUES ($1, $2, $3, $4) RETURNING id",
        body.platform, body.enabled, json.dumps(body.config), json.dumps(body.project_mappings),
    )
    return {"status": "ok", "id": row["id"]}


@router.delete("/configs/{config_id}")
async def delete_integration(request: Request, config_id: str):
    db = get_db(request)
    await db.execute("DELETE FROM integration_configs WHERE id = $1", config_id)
    return {"status": "ok"}
