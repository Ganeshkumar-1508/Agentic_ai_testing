"""commit_and_open_pr tool — git commit + gh pr create inside sandbox.

OpenSWE pattern: single tool, called by agent when work is done.
Runs inside the sandbox where GH_TOKEN is available.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)

PR_FLAG = "/workspace/.pr_created"


class CommitAndOpenPRTool(BaseTool):
    name = "commit_and_open_pr"
    description = (
        "Git commit all changes and open a GitHub draft PR. "
        "Call this when you've finished making changes and want to create a pull request. "
        "The tool commits all staged and unstaged changes, then runs `gh pr create --draft`. "
        "Requires GH_TOKEN to be configured (set via Settings > Integrations > GitHub)."
    )
    default_level = "allow"
    capabilities = ["can_write_git", "can_create_pr"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "PR title. Defaults to the last git commit message if not provided.",
                },
                "body": {
                    "type": "string",
                    "description": "PR body/description. Include a summary of what was changed and why.",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to push to. Defaults to current branch.",
                },
            },
            "required": ["title"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        title = kwargs.get("title", "")
        body = kwargs.get("body", "Automated changes by TestAI.")
        branch = kwargs.get("branch", "")

        if not title:
            return ToolResult(success=False, output="Title is required", error="missing_title")

        env = await self._get_env()
        if not env:
            return ToolResult(success=False, output="No sandbox environment available", error="no_sandbox")

        # Source GH_TOKEN from .testai_env (written by OrchestratorEngine) or use env var
        source_cmd = "export $(grep -s '^export GH_TOKEN=' /workspace/.testai_env 2>/dev/null | sed 's/^export //')"
        token_check = await env.run(f"{source_cmd} && echo ${GH_TOKEN:-}", timeout=5)
        gh_token = (token_check.stdout or "").strip()
        if not gh_token:
            return ToolResult(
                success=False,
                output="GH_TOKEN not set. Configure a GitHub PAT in Settings > Integrations > GitHub.",
                error="no_token",
            )

        cmds = [
            "cd /workspace/repo",
            "git add -A",
            f"git commit -m {_q(title)} --allow-empty 2>&1 || true",
        ]
        if branch:
            cmds.append(f"git checkout -b {_q(branch)} 2>&1 || git checkout {_q(branch)} 2>&1")
        cmds.append(
            f"GH_TOKEN={_q(gh_token)} gh pr create --draft --title {_q(title)} --body {_q(body)} 2>&1"
        )

        full_cmd = " && ".join(cmds)
        result = await env.run(f"cd /workspace/repo && {full_cmd}", timeout=60)

        output = (result.stdout or "") + (result.stderr or "")
        success = result.returncode == 0 or "already" in (result.stderr or "").lower()

        if success:
            await env.run(f"echo '{title}' > {PR_FLAG}", timeout=5)
            logger.info("PR created: %s", title[:80])
        else:
            logger.warning("PR creation failed: %s", output[:300])

        return ToolResult(
            success=success,
            output=output[:2000] if output else "PR created successfully.",
            data={"title": title, "branch": branch or "current"},
        )

    async def _get_env(self):
        try:
            from harness.context import manager as scope_manager
            scope = scope_manager.current
            if scope is None:
                return None
            session_id = scope.session_id
            if not session_id:
                return None
            from harness.backends.factory import get_backend
            from harness.memory.db_context import get_db
            _db = get_db()
            if _db is None:
                return None
            return get_backend(_db, session_id)
        except Exception:
            return None


def _q(s: str) -> str:
    escaped = s.replace("'", "'\\''")
    return f"'{escaped}'"


registry.register(CommitAndOpenPRTool(), toolset="write")
