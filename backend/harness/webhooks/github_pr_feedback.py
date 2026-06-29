"""GitHub PR feedback loop — detect @testai mentions and trigger agent iterations.

Pattern from Tembo (@tembo) and Greptile (@greptileai):
User comments "@testai fix this" on a PR → webhook detected → agent analyzes comment 
→ updates code → pushes new commit → PR updated.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)

MENTION_PATTERN = re.compile(r"@testai\b", re.IGNORECASE)


async def handle_pr_comment_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle GitHub PR comment webhook.
    
    Detects @testai mentions and triggers agent iteration.
    
    Args:
        payload: GitHub webhook payload for issue_comment event
        
    Returns:
        Dict with status and any spawned session info
    """
    action = payload.get("action", "")
    if action != "created":
        return {"status": "ignored", "reason": f"action={action}"}
    
    comment = payload.get("comment", {})
    body = comment.get("body", "")
    
    # Check for @testai mention
    if not MENTION_PATTERN.search(body):
        return {"status": "ignored", "reason": "no @testai mention"}
    
    # Extract PR info
    issue = payload.get("issue", {})
    pr_number = issue.get("number")
    repo = payload.get("repository", {})
    repo_full_name = repo.get("full_name", "")
    
    if not pr_number or not repo_full_name:
        return {"status": "error", "reason": "missing PR or repo info"}
    
    # Extract user comment (remove @testai mention)
    user_comment = MENTION_PATTERN.sub("", body).strip()
    
    logger.info("PR feedback detected: %s#%d — %s", repo_full_name, pr_number, user_comment[:100])
    
    # Get GitHub token
    import os
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    
    if not token:
        try:
            db = get_db()
            if db:
                row = await db.fetchrow(
                    "SELECT config FROM integration_configs WHERE platform = 'github' AND enabled = true LIMIT 1"
                )
                if row:
                    import json
                    config = row["config"]
                    if isinstance(config, str):
                        config = json.loads(config)
                    token = config.get("token", "")
        except Exception as e:
            logger.warning("Failed to fetch GitHub token: %s", e)
    
    if not token:
        return {"status": "error", "reason": "no GitHub token"}
    
    # Get PR diff and context
    try:
        from harness.ci.git_providers import GitHubProvider
        provider = GitHubProvider()
        pr_diff = await provider.get_pr_diff(repo_full_name, pr_number, token)
        
        # Post acknowledgment comment
        await provider.post_pr_comment(
            repo_full_name,
            pr_number,
            token,
            f"👀 Analyzing feedback: {user_comment[:200]}\n\n_I'll review the changes and update the PR shortly._"
        )
        
    except Exception as e:
        logger.error("Failed to get PR context: %s", e, exc_info=True)
        return {"status": "error", "reason": f"PR context failed: {str(e)}"}
    
    # Spawn agent to handle feedback
    try:
        from harness.orchestrator import OrchestratorEngine
        
        engine = OrchestratorEngine()
        
        repo_url = f"https://github.com/{repo_full_name}"
        goal = (
            f"PR #{pr_number} feedback iteration.\n\n"
            f"User comment: {user_comment}\n\n"
            f"PR diff:\n{pr_diff[:5000]}\n\n"
            f"Instructions: Analyze the user's feedback, make the requested changes, "
            f"run tests, and commit the updates. The PR will be automatically updated."
        )
        
        import uuid
        run_id = str(uuid.uuid4())[:8]
        session_id = str(uuid.uuid4())
        
        # Run in background
        import asyncio
        asyncio.create_task(
            engine.run_single(run_id, session_id, repo_url, goal),
            name=f"pr-feedback-{pr_number}"
        )
        
        logger.info("Spawned PR feedback agent: session=%s, pr=%s#%d", session_id[:8], repo_full_name, pr_number)
        
        return {
            "status": "spawned",
            "session_id": session_id,
            "run_id": run_id,
            "pr_number": pr_number,
            "repo": repo_full_name,
        }
    
    except Exception as e:
        logger.error("Failed to spawn PR feedback agent: %s", e, exc_info=True)
        return {"status": "error", "reason": f"spawn failed: {str(e)}"}


async def setup_github_webhook_listener(app: Any) -> None:
    """Register GitHub webhook endpoint with FastAPI app.
    
    Call this during app startup to enable PR feedback loop.
    """
    from fastapi import Request
    import hashlib
    import hmac
    import os
    
    @app.post("/api/webhooks/github")
    async def github_webhook(request: Request):
        """Handle GitHub webhook events."""
        # Verify webhook signature (if secret configured)
        webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
        if webhook_secret:
            signature = request.headers.get("X-Hub-Signature-256", "")
            body = await request.body()
            expected = "sha256=" + hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected):
                return {"status": "error", "reason": "invalid signature"}
        
        payload = await request.json()
        event_type = request.headers.get("X-GitHub-Event", "")
        
        if event_type == "issue_comment":
            result = await handle_pr_comment_webhook(payload)
            return result
        
        return {"status": "ignored", "reason": f"event={event_type}"}
    
    logger.info("GitHub webhook listener registered at /api/webhooks/github")
