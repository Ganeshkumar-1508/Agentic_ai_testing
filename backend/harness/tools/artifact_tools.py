"""Artifact tools — save, list, and read task outputs across runs.

Pattern: Google ADK ArtifactService (light) + CI/CD centralized storage.
Artifacts are files saved from the sandbox to host storage with metadata
in the `artifacts` DB table. Agents can query artifacts from the current
or past runs by repo_url, enabling cross-run memory.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)

from harness.testai_constants import get_testai_home
ARTIFACT_ROOT = os.environ.get("ARTIFACT_ROOT", str(get_testai_home() / "artifacts"))


def _get_db():
    from harness.memory.db_context import get_db
    return get_db()


async def _get_env():
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


class ArtifactSaveTool(BaseTool):
    name = "artifact_save"
    description = (
        "Save a file from the sandbox to persistent artifact storage. "
        "Use this to preserve test reports, coverage data, logs, screenshots, "
        "or any output you want available across runs. "
        "Saved artifacts can be found by future agents via artifact_list."
    )
    default_level = "allow"
    capabilities = ["can_write_artifacts"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file in the sandbox (e.g., /workspace/repo/coverage.json)",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this artifact is",
                },
                "tags": {
                    "type": "string",
                    "description": "Optional comma-separated tags: coverage,test-report,log,screenshot,config",
                },
            },
            "required": ["path", "description"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        description = kwargs.get("description", "")
        tags = kwargs.get("tags", "")

        if not path or not description:
            return ToolResult(success=False, output="path and description are required", error="missing_args")

        env = await _get_env()
        if not env:
            return ToolResult(success=False, output="No sandbox environment available", error="no_sandbox")

        # Check file exists in sandbox
        exists = await env.run(f"test -f {_q(path)} && echo 'exists'", timeout=5)
        if exists.stdout.strip() != "exists":
            return ToolResult(success=False, output=f"File not found in sandbox: {path}", error="not_found")

        db = _get_db()
        if not db:
            return ToolResult(success=False, output="Database not available", error="no_db")

        try:
            from harness.context import manager as scope_manager
            scope = scope_manager.current
            session_id = scope.session_id if scope else "unknown"

            # Read file content from sandbox
            result = await env.run(f"cat {_q(path)}", timeout=30)
            content = result.stdout.encode("utf-8") if result.stdout else b""
            if not content:
                return ToolResult(success=False, output=f"Empty or unreadable file: {path}", error="empty")

            mime = _detect_mime(path)
            filename = os.path.basename(path)
            dest_dir = os.path.join(ARTIFACT_ROOT, session_id[:12])
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, f"{int(time.time())}_{filename}")

            with open(dest_path, "wb") as f:
                f.write(content)

            tags_str = tags.strip()
            meta = {"tags": tags_str} if tags_str else {}

            await db.execute(
                "INSERT INTO artifacts (session_id, path, size_bytes, mime_type, description, meta) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                session_id, dest_path, len(content), mime, description, json.dumps(meta) if meta else "{}",
            )

            return ToolResult(
                success=True,
                output=f"Saved {filename} ({len(content)} bytes, {mime})",
                data={"path": dest_path, "size": len(content), "mime": mime},
            )
        except Exception as e:
            logger.warning("artifact_save failed: %s", e)
            return ToolResult(success=False, output=str(e), error="save_failed")


class ArtifactListTool(BaseTool):
    name = "artifact_list"
    description = (
        "List artifacts from the current or past runs. "
        "Use this to discover what outputs previous agents saved: "
        "test reports, coverage data, logs, etc. "
        "Filter by repo_url to find artifacts from all runs of a project."
    )
    default_level = "allow"
    capabilities = ["can_read_artifacts"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Filter by session ID. Defaults to current session.",
                },
                "tags": {
                    "type": "string",
                    "description": "Filter by comma-separated tags (coverage, test-report, log, screenshot)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                },
            },
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        session_id = kwargs.get("session_id", "")
        tags = kwargs.get("tags", "")
        limit = min(int(kwargs.get("limit", 20)), 100)

        if not session_id:
            try:
                from harness.context import manager as scope_manager
                scope = scope_manager.current
                session_id = scope.session_id if scope else ""
            except Exception:
                pass

        db = _get_db()
        if not db:
            return ToolResult(success=False, output="Database not available", error="no_db")

        try:
            if tags:
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                like_clauses = " AND ".join(f"meta ILIKE '%{t}%'" for t in tag_list)
                if session_id:
                    rows = await db.fetch(
                        f"SELECT id, session_id, path, size_bytes, mime_type, description, meta, created_at "
                        f"FROM artifacts WHERE session_id = $1 AND ({like_clauses}) "
                        f"ORDER BY created_at DESC LIMIT $2",
                        session_id, limit,
                    )
                else:
                    rows = await db.fetch(
                        f"SELECT id, session_id, path, size_bytes, mime_type, description, meta, created_at "
                        f"FROM artifacts WHERE {like_clauses} "
                        f"ORDER BY created_at DESC LIMIT $1",
                        limit,
                    )
            elif session_id:
                rows = await db.fetch(
                    "SELECT id, session_id, path, size_bytes, mime_type, description, meta, created_at "
                    "FROM artifacts WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2",
                    session_id, limit,
                )
            else:
                rows = await db.fetch(
                    "SELECT id, session_id, path, size_bytes, mime_type, description, meta, created_at "
                    "FROM artifacts ORDER BY created_at DESC LIMIT $1",
                    limit,
                )

            artifacts = []
            for r in rows:
                art = dict(r)
                art["created_at"] = str(art.get("created_at", ""))
                if isinstance(art.get("meta"), str):
                    try:
                        art["meta"] = json.loads(art["meta"])
                    except json.JSONDecodeError:
                        art["meta"] = {}
                artifacts.append(art)

            return ToolResult(
                success=True,
                output=json.dumps({"count": len(artifacts), "artifacts": artifacts}, indent=2),
                data={"artifacts": artifacts},
            )
        except Exception as e:
            logger.warning("artifact_list failed: %s", e)
            return ToolResult(success=False, output=str(e), error="list_failed")


class ArtifactReadTool(BaseTool):
    name = "artifact_read"
    description = (
        "Read the content of a saved artifact by ID. "
        "Use artifact_list first to find artifact IDs, then read the one you need. "
        "Returns the full file content."
    )
    default_level = "allow"
    capabilities = ["can_read_artifacts"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "Artifact ID from artifact_list results",
                },
            },
            "required": ["artifact_id"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        artifact_id = kwargs.get("artifact_id", "")
        if not artifact_id:
            return ToolResult(success=False, output="artifact_id is required", error="missing_id")

        db = _get_db()
        if not db:
            return ToolResult(success=False, output="Database not available", error="no_db")

        try:
            row = await db.fetchrow(
                "SELECT path, mime_type, description FROM artifacts WHERE id = $1",
                artifact_id,
            )
            if not row:
                return ToolResult(success=False, output=f"Artifact not found: {artifact_id}", error="not_found")

            file_path = row["path"]
            if not os.path.exists(file_path):
                return ToolResult(success=False, output=f"Artifact file missing: {file_path}", error="file_missing")

            with open(file_path, "rb") as f:
                content = f.read()

            text = content.decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=text[:50000],
                data={"mime_type": row["mime_type"], "size": len(content), "description": row["description"]},
            )
        except Exception as e:
            logger.warning("artifact_read failed: %s", e)
            return ToolResult(success=False, output=str(e), error="read_failed")


def _detect_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".json": "application/json",
        ".xml": "application/xml",
        ".html": "text/html",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".log": "text/plain",
        ".csv": "text/csv",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".toml": "text/toml",
        ".zip": "application/zip",
        ".tar": "application/x-tar",
        ".gz": "application/gzip",
    }.get(ext, "application/octet-stream")


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


registry.register(ArtifactSaveTool(), toolset="write")
registry.register(ArtifactListTool(), toolset="read")
registry.register(ArtifactReadTool(), toolset="read")
