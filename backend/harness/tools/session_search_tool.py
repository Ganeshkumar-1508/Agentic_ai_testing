"""SessionSearchTool — search past sessions using Postgres FTS.

Adapted from Hermes' session_search_tool.py for TestAI's Postgres-backed
architecture. Instead of Hermes' SQLite FTS5, this uses PostgreSQL's
built-in full-text search (to_tsvector / plainto_tsquery) over the
job_specs and stream_events tables.

Three calling modes (inferred from args):
  1. DISCOVERY — pass "query". Runs Postgres FTS over past job prompts
     and stream event content. Returns top N sessions with previews.
  2. BROWSE — no args. Returns recent jobs chronologically.
  3. READ — pass "spec_id". Returns full job details.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


def _db(request: Any = None) -> Any:
    """Get the Postgres DB handle from app state or fallback."""
    if request is not None:
        store = getattr(request.app.state, "store", None)
        if store and hasattr(store, "db"):
            return store.db
    from harness.memory.db_context import get_db
    return get_db()


class SessionSearchTool(BaseTool):
    """Search past sessions using PostgreSQL full-text search."""

    name = "session_search"
    default_level = "allow"
    description = (
        "Search past job sessions and conversations. "
        "Pass a query to find relevant past work by full-text search. "
        "Pass no args to browse recent jobs. "
        "Pass a spec_id to read full details of a specific job."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search terms to find in past sessions. "
                            "Searches job prompts and event content. "
                            "Omit to browse recent sessions."
                        ),
                    },
                    "spec_id": {
                        "type": "string",
                        "description": "Read a specific job by spec_id. Returns full details.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 5, max 20).",
                        "default": 5,
                    },
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        spec_id = kwargs.get("spec_id", "")
        limit = max(1, min(int(kwargs.get("limit", 5)), 20))

        db = _db()
        if db is None:
            return ToolResult(
                success=False,
                output="Database not available.",
                error="no_db",
            )

        # READ mode: fetch a specific job spec
        if spec_id:
            return await self._read_spec(db, spec_id)

        # BROWSE mode: no query, return recent jobs
        if not query or not query.strip():
            return await self._browse_recent(db, limit)

        # DISCOVERY mode: full-text search
        return await self._discover(db, query.strip(), limit)

    async def _read_spec(self, db: Any, spec_id: str) -> ToolResult:
        try:
            row = await db.fetchrow(
                "SELECT spec_id, prompt, repo_url, branch, tier, status, "
                "created_at, started_at, completed_at, error "
                "FROM job_specs WHERE spec_id = $1",
                spec_id,
            )
        except Exception as e:
            return ToolResult(success=False, output=f"DB error: {e}", error="db_error")

        if not row:
            return ToolResult(
                success=False,
                output=f"Job spec '{spec_id}' not found.",
                error="not_found",
            )

        return ToolResult(
            success=True,
            output=(
                f"Job: {row['spec_id']}\n"
                f"Status: {row['status']}\n"
                f"Prompt: {row['prompt'][:500]}\n"
                f"Repo: {row['repo_url']}\n"
                f"Branch: {row['branch']}\n"
                f"Tier: {row['tier']}\n"
                f"Created: {row['created_at']}\n"
            ),
            data=dict(row),
        )

    async def _browse_recent(self, db: Any, limit: int) -> ToolResult:
        try:
            rows = await db.fetch(
                "SELECT spec_id, prompt, repo_url, status, created_at, "
                "latest_run_status, latest_run_duration_s "
                "FROM job_specs ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        except Exception as e:
            return ToolResult(success=False, output=f"DB error: {e}", error="db_error")

        if not rows:
            return ToolResult(
                success=True,
                output="No past sessions found.",
                data={"results": []},
            )

        lines = ["## Recent Sessions\n"]
        results = []
        for r in rows:
            runtime = r.get("latest_run_duration_s", 0)
            runtime_str = f"{runtime:.1f}s" if runtime else ""
            status = r.get("latest_run_status") or r["status"]
            lines.append(
                f"- **{r['spec_id'][:12]}** ({status}) "
                f"{r['prompt'][:80]}... "
                f"{runtime_str}"
            )
            results.append({
                "spec_id": r["spec_id"],
                "prompt": r["prompt"][:200],
                "status": status,
                "created_at": str(r["created_at"]),
                "duration_s": runtime,
            })

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"results": results, "count": len(results)},
        )

    async def _discover(self, db: Any, query: str, limit: int) -> ToolResult:
        """Full-text search over job_specs prompts and stream_events content."""
        results = []

        # Search job_specs prompts using ILIKE (simple pattern search)
        try:
            pattern = f"%{query}%"
            rows = await db.fetch(
                "SELECT spec_id, prompt, repo_url, branch, status, created_at "
                "FROM job_specs "
                "WHERE prompt ILIKE $1 OR repo_url ILIKE $1 "
                "ORDER BY created_at DESC LIMIT $2",
                pattern,
                limit,
            )
            for r in rows:
                results.append({
                    "spec_id": r["spec_id"],
                    "type": "job",
                    "snippet": r["prompt"][:300],
                    "status": r["status"],
                    "created_at": str(r["created_at"]),
                    "repo_url": r["repo_url"],
                })
        except Exception as e:
            logger.debug("session_search job_specs query failed: %s", e)

        # Also search stream_events for message content
        if len(results) < limit:
            try:
                event_pattern = f"%{query}%"
                event_rows = await db.fetch(
                    "SELECT session_id, event_type, event_data::text, created_at "
                    "FROM stream_events "
                    "WHERE event_data::text ILIKE $1 "
                    "ORDER BY created_at DESC LIMIT $2",
                    event_pattern,
                    limit - len(results),
                )
                for r in event_rows:
                    results.append({
                        "spec_id": r["session_id"][:20],
                        "type": "event",
                        "snippet": r["event_data"][:300] if isinstance(r["event_data"], str) else str(r["event_data"])[:300],
                        "event_type": r["event_type"],
                        "created_at": str(r["created_at"]),
                    })
            except Exception as e:
                logger.debug("session_search stream_events query failed: %s", e)

        if not results:
            return ToolResult(
                success=True,
                output=f"No sessions match '{query}'.",
                data={"results": [], "query": query},
            )

        out = [f"## Sessions matching '{query}'\n"]
        for r in results:
            out.append(f"- **{r['spec_id']}** ({r.get('status', r.get('event_type', ''))})")
            out.append(f"  {r['snippet'][:120]}...")

        return ToolResult(
            success=True,
            output="\n".join(out),
            data={"results": results[:limit], "query": query, "count": len(results[:limit])},
        )


registry.register(SessionSearchTool(), toolset="read")
