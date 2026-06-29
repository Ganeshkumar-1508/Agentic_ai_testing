"""GitHub, GitLab, and Bitbucket PR/MR webhook receivers — triggers TestAI pipeline on events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid

from fastapi import APIRouter, Request, HTTPException

from ..deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["webhook"])


def _verify_github_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature from GitHub webhook."""
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True  # no secret configured = skip verify in dev/test
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(request: Request):
    """Receive GitHub webhook events for pull requests.

    Triggers test generation + execution + PR comment on:
      - pull_request.opened
      - pull_request.synchronize (new commits pushed)
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_github_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    db = get_db(request)
    payload = json.loads(body)
    event = request.headers.get("X-GitHub-Event", "")
    delivery = request.headers.get("X-GitHub-Delivery", "")

    logger.info("GitHub webhook: event=%s, delivery=%s", event, delivery)

    # Handle @testai mentions in PR comments (feedback loop)
    if event == "issue_comment":
        return await _handle_pr_comment(request, payload)

    # Only handle pull_request events
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    action = payload.get("action", "")
    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "action": action}

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    repo_url = repo.get("clone_url", "")
    pr_number = pr.get("number", 0)
    pr_title = pr.get("title", "")
    pr_body = pr.get("body", "")
    head_sha = pr.get("head", {}).get("sha", "")
    source_branch = pr.get("head", {}).get("ref", "")
    github_token = None  # Would come from settings store

    if not repo_url or not pr_number:
        return {"error": "Missing repo_url or pr_number"}

    # Generate requirements from PR description
    requirements = f"PR #{pr_number}: {pr_title}\n\n{pr_body}" if pr_body else pr_title

    # Kick off the pipeline in background
    import asyncio
    asyncio.create_task(
        _run_pr_pipeline(request.app, repo_url, pr_number, source_branch, requirements, github_token),
        name=f"pr-pipeline-{repo_url.split('/')[-1]}-{pr_number}",
    )

    return {"status": "accepted", "pr": pr_number, "repo": repo_url}


def _verify_gitlab_token(request: Request) -> bool:
    """Verify GitLab webhook secret token."""
    secret = os.environ.get("GITLAB_WEBHOOK_SECRET", "")
    if not secret:
        return True
    token = request.headers.get("X-Gitlab-Token", "")
    return hmac.compare_digest(token, secret)


@router.post("/gitlab")
async def gitlab_webhook(request: Request):
    if not _verify_gitlab_token(request):
        raise HTTPException(status_code=401, detail="Invalid token")
    payload = await request.json()
    event = request.headers.get("X-Gitlab-Event", "")
    if event not in ("Merge Request Hook",):
        return {"status": "ignored", "event": event}
    mr = payload.get("object_attributes", {})
    action = mr.get("action", "")
    if action not in ("open", "reopen", "update"):
        return {"status": "ignored", "action": action}
    repo_url = payload.get("project", {}).get("git_http_url", "")
    pr_number = mr.get("iid", 0)
    pr_title = mr.get("title", "")
    source_branch = mr.get("source_branch", "")
    if not repo_url or not pr_number:
        return {"error": "Missing repo_url or pr_number"}
    import asyncio
    asyncio.create_task(
        _run_pr_pipeline(request.app, repo_url, pr_number, source_branch, pr_title, None),
    )
    return {"status": "accepted", "pr": pr_number, "repo": repo_url}


@router.post("/bitbucket")
async def bitbucket_webhook(request: Request):
    # Bitbucket uses URL token or IP whitelist — no HMAC signature
    payload = await request.json()
    event = request.headers.get("X-Event-Key", "")
    if "pullrequest" not in event:
        return {"status": "ignored", "event": event}
    pr = payload.get("pullrequest", {})
    action = "opened" if "created" in event else "synchronize" if "updated" in event else "unknown"
    if action == "unknown":
        return {"status": "ignored", "event": event}
    repo_url = (payload.get("repository", {}) or pr.get("source", {}).get("repository", {})).get("links", {}).get("html", {}).get("href", "") or ""
    pr_number = pr.get("id", 0)
    pr_title = pr.get("title", "")
    source_branch = pr.get("source", {}).get("branch", {}).get("name", "")
    if not repo_url or not pr_number:
        return {"error": "Missing repo_url or pr_number"}
    import asyncio
    asyncio.create_task(
        _run_pr_pipeline(request.app, repo_url, pr_number, source_branch, pr_title, None),
    )
    return {"status": "accepted", "pr": pr_number, "repo": repo_url}


async def _handle_pr_comment(request: Request, payload: dict) -> dict:
    """Handle @testai mentions in PR comments — feedback loop.

    Users comment '@testai fix this issue' on a PR, and the agent
    amends the PR with the requested changes.
    """
    action = payload.get("action", "")
    if action != "created":
        return {"status": "ignored", "action": action}

    comment = payload.get("comment", {})
    body = comment.get("body", "")

    # Only respond to @testai mentions
    if "@testai" not in body.lower():
        return {"status": "ignored", "reason": "no mention"}

    issue = payload.get("issue", {})
    pr_number = issue.get("number", 0)
    repo = payload.get("repository", {})
    repo_url = repo.get("clone_url", "")
    pr_title = issue.get("title", "")

    if not repo_url or not pr_number:
        return {"error": "Missing repo_url or pr_number"}

    # Check it's actually a PR (not a plain issue)
    if not issue.get("pull_request"):
        return {"status": "ignored", "reason": "not a PR"}

    # Strip the @testai prefix to get the actual request
    request_text = body.replace("@testai", "", 1).strip()
    requirements = f"PR #{pr_number}: {pr_title}\n\nFeedback: {request_text}\n\nApply the requested changes to the existing PR."

    import asyncio
    asyncio.create_task(
        _run_pr_pipeline(request.app, repo_url, pr_number, "", requirements, None),
        name=f"pr-feedback-{repo_url.split('/')[-1]}-{pr_number}",
    )

    return {"status": "accepted", "pr": pr_number, "repo": repo_url, "feedback": request_text}


async def _run_pr_pipeline(app, repo_url: str, pr_number: int, branch: str,
                           requirements: str, github_token: str | None):
    """Run the pipeline via OrchestratorEngine and post results back to the PR."""
    from harness.pr_integration import build_pr_comment, post_pr_comment, update_pr_commit_status
    from harness.orchestrator import OrchestratorEngine

    run_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    commit_sha = branch  # webhooks don't always have SHA; branch is the reliable identifier

    try:
        # Update commit status to pending
        if github_token and commit_sha:
            await update_pr_commit_status(
                repo_url, commit_sha, "pending",
                "TestAI running quality checks...", github_token,
            )

        goal = f"Analyze and test PR #{pr_number} for {repo_url}\n\n{requirements}"
        engine: OrchestratorEngine = app.state.orchestrator_engine
        result = await engine.run_single(
            run_id=run_id,
            session_id=session_id,
            repo_url=repo_url,
            goal=goal,
            branch=branch,
        )

        tasks = result.get("tasks", [])
        done_count = sum(1 for t in tasks if t.get("status") == "done")
        failed_count = sum(1 for t in tasks if t.get("status") == "blocked")
        total_count = len(tasks)
        success = result.get("success", False)

        test_summary = {
            "total": total_count,
            "passed": done_count,
            "failed": failed_count,
            "pass_rate": round((done_count / total_count * 100) if total_count > 0 else 0, 1),
        }

        # Build PR comment from real results
        comment = build_pr_comment(
            test_summary=test_summary,
            coverage=None,
            quality_score=None,
        )

        # Post comment and update commit status
        if github_token:
            pr_result = await post_pr_comment(repo_url, pr_number, comment, github_token)
            logger.info("PR comment posted: %s", pr_result)

            status_state = "success" if success else "failure"
            status_desc = f"TestAI: {test_summary['passed']}/{test_summary['total']} tasks passed"
            await update_pr_commit_status(
                repo_url, commit_sha, status_state, status_desc, github_token,
            )

    except Exception as e:
        logger.error("PR pipeline failed: %s", e)
        if github_token:
            await update_pr_commit_status(
                repo_url, commit_sha or "HEAD", "error", f"TestAI error: {str(e)[:100]}", github_token,
            )
