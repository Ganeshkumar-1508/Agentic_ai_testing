"""Evidence system — capture per-tool-call artifacts and bundle them for review.

Two halves, one module:

1. **Writer** — :func:`capture_evidence` runs after each tool call. Stores
   bash commands as script artifacts and browser/computer-use screenshots
   as image artifacts. Returns a metadata dict merged into
   ``ToolExecutionCompleted``.

2. **Reader** — :class:`EvidenceBundler` runs at end-of-run. Reads the
   captured artifacts from ``agent_artifacts``, groups them by kind, and
   either returns a markdown summary or posts it as a PR comment.

Pattern: Greptile TREX — "If your artifacts can't be verified, they're
decoration." A worker that says "test passed" without a log is just a
claim; a worker that returns a screenshot, a log, and a script is an
experiment the reviewer can re-run.

Both halves are fail-open: any storage/IO error returns an empty
result so a flaky evidence pipeline never breaks a real agent run.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "capture_evidence",
    "EvidenceBundler",
]


# ---------------------------------------------------------------------------
# WRITER — per-tool-call capture
# ---------------------------------------------------------------------------


async def capture_evidence(
    tool_name: str,
    tool_args: dict[str, Any],
    result: str,
    session_id: str,
    db: Any = None,
    sandbox: Any = None,
) -> dict[str, Any]:
    """Capture optional evidence for a tool execution.

    Returns a metadata dict to merge into ToolExecutionCompleted:
        {"evidence": {"screenshot_id": "...", "log_id": "...", ...}}

    Fail-open: returns empty dict on any error.
    """
    evidence: dict[str, Any] = {}
    if not db:
        return evidence

    # Bash: capture the executed command as a script artifact
    if tool_name == "bash":
        cmd = tool_args.get("command", "")
        if cmd:
            try:
                art_id = f"ev-bash-{int(time.time() * 1000)}"
                await db.execute(
                    "INSERT INTO artifacts (id, session_id, path, size_bytes, mime_type, description) "
                    "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (id) DO NOTHING",
                    art_id, session_id, f"cmd://{cmd[:80]}", len(cmd), "text/x-shellscript",
                    f"Bash command: {cmd[:200]}",
                )
                evidence["script_id"] = art_id
            except Exception as exc:
                logger.debug("Evidence capture for bash failed: %s", exc)

    # Computer use / browser: capture screenshot
    elif tool_name in ("computer_use", "browser_navigate") and sandbox:
        try:
            tmp = tempfile.mktemp(suffix=".png")
            code, out, err = await sandbox.execute(f"test -f /tmp/screenshot.png && cp /tmp/screenshot.png {tmp} || true")
            if code == 0 and os.path.getsize(tmp) > 0:
                with open(tmp, "rb") as f:
                    data = f.read()
                art_id = f"ev-shot-{int(time.time() * 1000)}"
                await db.execute(
                    "INSERT INTO artifacts (id, session_id, path, size_bytes, mime_type, description) "
                    "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (id) DO NOTHING",
                    art_id, session_id, f"screenshot-{art_id}.png", len(data), "image/png",
                    f"Screenshot after {tool_name}",
                )
                evidence["screenshot_id"] = art_id
        except Exception as exc:
            logger.debug("Evidence capture screenshot failed: %s", exc)

    return evidence


# ---------------------------------------------------------------------------
# READER — end-of-run bundling
# ---------------------------------------------------------------------------


class EvidenceBundler:
    """Group captured artifacts into a per-finding evidence bundle.

    Reads the ``agent_artifacts`` table for a session and produces a
    markdown summary suitable for posting as a PR comment. The bundler
    is the verification primitive: without it, the writer's artifacts
    sit unused in the database.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    async def build_finding_summary(self, session_id: str) -> str | None:
        """Build a markdown evidence summary for a worker session.

        Groups L0 artifacts by kind:
          - File edits → Files Changed
          - Bash commands → Commands Run
          - Test results → Test Results
          - Screenshots → Screenshots (when present)
          - Fallback: tool-call counts

        Returns a markdown string, or ``None`` if no evidence exists.
        """
        artifacts = await self._get_artifacts(session_id)
        if not artifacts:
            return None

        sections: list[str] = []
        screenshots: list[str] = []
        commands: list[str] = []
        test_results: list[str] = []
        file_changes: list[str] = []

        for art in artifacts:
            kind = art.get("kind", "")
            tool_name = art.get("tool_name", "") or ""
            payload = art.get("payload", {}) or {}
            if kind == "tool_call":
                args_str = str(payload.get("arguments", "") or "")
                if tool_name in ("write_file", "edit_file", "apply_patch"):
                    for prefix in ('"path":', "path="):
                        if prefix in args_str:
                            val = args_str.split(prefix, 1)[-1].split(",")[0].strip().strip('"').strip("'")
                            if val and val not in file_changes:
                                file_changes.append(val)
                if tool_name == "bash" and "test" in args_str.lower():
                    cmd = args_str[:200]
                    if cmd not in commands:
                        commands.append(cmd)

            elif kind == "tool_result":
                output = str(payload.get("output", "") or "")[:500]
                if "PASSED" in output or "FAILED" in output or "error" in output.lower():
                    test_results.append(output)

            elif kind == "screenshot":
                path = str(payload.get("path", "") or "")
                if path and path not in screenshots:
                    screenshots.append(path)

        if screenshots:
            sections.append("### Screenshots\n")
            for s in screenshots:
                sections.append(f"![{s}]({s})\n")

        if file_changes:
            sections.append("### Files Changed\n")
            for f in file_changes:
                sections.append(f"- `{f}`\n")

        if commands:
            sections.append("### Commands Run\n")
            for c in commands:
                sections.append(f"```\n{c}\n```\n")

        if test_results:
            sections.append("### Test Results\n")
            for r in test_results[:5]:
                sections.append(f"> {r}\n")

        if not sections:
            # Fallback: show tool counts so a finding is never empty
            tool_counts: dict[str, int] = {}
            for art in artifacts:
                n = str(art.get("tool_name", "") or "")
                if n:
                    tool_counts[n] = tool_counts.get(n, 0) + 1
            if tool_counts:
                sections.append("### Tools Used\n")
                for name, count in sorted(tool_counts.items()):
                    sections.append(f"- {name}: {count} call(s)\n")

        return "\n".join(sections) if sections else None

    async def post_finding_evidence(
        self,
        session_id: str,
        repo_url: str,
        pr_number: int,
        github_token: str,
    ) -> dict[str, Any]:
        """Build the evidence summary and post it as a PR comment.

        Deferred import of :mod:`harness.pr_integration` to avoid a
        top-level cycle and to keep the bundler importable in test
        environments that lack a real PR backend.
        """
        summary = await self.build_finding_summary(session_id)
        if not summary:
            return {"status": "skipped", "reason": "no evidence"}

        from harness.pr_integration import post_pr_comment

        comment = (
            f"## TestAI Finding\n\n"
            f"**Session:** `{session_id[:12]}`\n\n"
            f"{summary}\n\n"
            f"---\n*Auto-generated by TestAI evidence bundler*"
        )
        return await post_pr_comment(repo_url, pr_number, comment, github_token)

    async def _get_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        """Read L0 artifacts for a session from ``agent_artifacts``."""
        try:
            rows = await self.db.fetch(
                "SELECT kind, tool_name, payload::text FROM agent_artifacts "
                "WHERE session_id = $1 ORDER BY id ASC",
                session_id,
            )
            result: list[dict[str, Any]] = []
            for r in rows:
                payload = r["payload"]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": payload[:500]}
                result.append({"kind": r["kind"], "tool_name": r["tool_name"], "payload": payload})
            return result
        except Exception as exc:
            logger.debug("EvidenceBundler._get_artifacts failed: %s", exc)
            return []
