"""Chat introspection tools — read-only queries for the chat Role.

The chat Role is read-only. It can introspect the harness's internal
state (runs, logs, test cases, coverage, artifacts, dashboard) but it
cannot mutate. The ONE allowed mutation — `submit_job` — is a
special-cased tool in `ToolDispatcher` that hands work to the
orchestrator.

The tools in this module read from the same Postgres tables the API
routers read. The duplication is acceptable for v1; the C4-revised
deepening will extract a shared `IntrospectionStore` that the tools
and the API routers both consume.

Usage:

    from harness.tools.chat_introspection import set_introspection_store
    set_introspection_store(store)   # call at app startup
"""
from __future__ import annotations

import json
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


# Module-level store reference, set at app startup by api/main.py.
# All tools read from this. If unset, the tools return a clear
# "introspection store not initialized" error rather than crashing.
_store_ref: dict[str, Any] = {}


def set_introspection_store(store: Any) -> None:
    """Inject the store at app startup. All chat introspection tools
    read from this."""
    _store_ref["store"] = store


def _store() -> Any:
    return _store_ref.get("store")


def _serialize_run(row: dict) -> dict[str, Any]:
    """Shared run-row serializer (mirrors the API's `_serialize_run`).
    Reads the JSONB `inputs` field and surfaces the common fields the
    chat LLM needs to triage failures."""
    raw = row.get("inputs")
    if not raw:
        inputs: dict = {}
    elif isinstance(raw, str):
        try:
            inputs = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            inputs = {}
    elif isinstance(raw, dict):
        inputs = raw
    else:
        inputs = {}
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "source": inputs.get("source") or "user",
        "task_type": inputs.get("task_type") or "",
        "repo_url": inputs.get("repo_url") or "",
        "branch": inputs.get("branch") or "",
        "prompt_preview": (inputs.get("requirements") or inputs.get("prompt") or "")[:200],
        "test_count": row.get("test_count") or 0,
        "passed_count": row.get("passed_count") or 0,
        "failed_count": row.get("failed_count") or 0,
        "duration_ms": row.get("duration") or 0,
        "cost_usd": float(row.get("cost_usd") or 0),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
    }


# ---------------------------------------------------------------------------
# 1. list_runs — recent runs with status summary
# ---------------------------------------------------------------------------


class ListRunsTool(BaseTool):
    name = "list_runs"
    default_level = "allow"
    description = (
        "List recent pipeline runs (CI runs, autonomous test runs, chat-"
        "submitted jobs) with status summary, source, and pass/fail "
        "counts. Use when the user asks 'what runs exist?' or 'what "
        "happened recently?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                    "status": {"type": "string",
                               "enum": ["", "pending", "running", "completed", "failed"],
                               "default": ""},
                    "source": {"type": "string",
                               "enum": ["", "user", "github", "cron", "slack", "linear", "chat-submission"],
                               "default": ""},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        try:
            limit = max(1, min(100, int(kwargs.get("limit", 20))))
        except (TypeError, ValueError):
            limit = 20
        status = kwargs.get("status") or ""
        source = kwargs.get("source") or ""

        # Build the query with optional filters. We filter on the JSONB
        # `inputs` field for the source — `inputs->>'source' = $X`.
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            params.append(status)
            clauses.append(f"status = ${len(params)}")
        if source:
            params.append(source)
            clauses.append(f"inputs->>'source' = ${len(params)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        sql = (
            "SELECT id, status, inputs, test_count, passed_count, "
            "failed_count, duration, cost_usd, created_at, completed_at "
            f"FROM pipeline_runs {where} "
            f"ORDER BY created_at DESC LIMIT ${len(params)}"
        )
        try:
            rows = await store.db.fetch(sql, *params)
        except Exception as exc:
            logger.warning("list_runs: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")

        if not rows:
            return ToolResult(success=True, output="No runs found.", data={"runs": []})

        serialized = [_serialize_run(dict(r)) for r in rows]
        lines = [f"## {len(serialized)} run(s)\n"]
        for r in serialized[:10]:
            short_prompt = r["prompt_preview"][:60] or "(no prompt recorded)"
            lines.append(
                f"- `{r['id'][:8]}` [{r['status']}] "
                f"source={r['source']} "
                f"tests={r['test_count']} pass/fail={r['passed_count']}/{r['failed_count']} "
                f"— {short_prompt}"
            )
        if len(serialized) > 10:
            lines.append(f"\n(... {len(serialized) - 10} more)")
        return ToolResult(success=True, output="\n".join(lines), data={"runs": serialized})


# ---------------------------------------------------------------------------
# 2. get_run — single run with full details
# ---------------------------------------------------------------------------


class GetRunTool(BaseTool):
    name = "get_run"
    default_level = "allow"
    description = (
        "Get the full detail of a single run by its run_id (full UUID "
        "or first 8 chars). Returns status, source, prompt, repo, "
        "pass/fail counts, cost, and timing. Use when the user asks "
        "about a specific run."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Run ID (full or first 8 chars)"},
                },
                "required": ["run_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        run_id = (kwargs.get("run_id") or "").strip()
        if not run_id:
            return ToolResult(success=False, output="`run_id` is required", error="missing_arg")

        # Allow short IDs (first 8 chars). The full id is the canonical
        # match; the prefix match is a convenience for the chat LLM.
        if len(run_id) >= 8:
            row = await store.db.fetchrow(
                "SELECT id, status, inputs, test_count, passed_count, "
                "failed_count, duration, cost_usd, created_at, completed_at "
                "FROM pipeline_runs WHERE id = $1 OR id LIKE $2 LIMIT 1",
                run_id, f"{run_id}%",
            )
        else:
            row = await store.db.fetchrow(
                "SELECT id, status, inputs, test_count, passed_count, "
                "failed_count, duration, cost_usd, created_at, completed_at "
                "FROM pipeline_runs WHERE id LIKE $1 LIMIT 1",
                f"{run_id}%",
            )
        if not row:
            return ToolResult(success=False, output=f"No run found matching '{run_id}'", error="not_found")

        serialized = _serialize_run(dict(row))
        output = (
            f"## Run `{serialized['id'][:8]}` — {serialized['status']}\n\n"
            f"- **Source:** {serialized['source']}\n"
            f"- **Task type:** {serialized['task_type']}\n"
            f"- **Repo:** {serialized['repo_url'] or '(none)'}\n"
            f"- **Branch:** {serialized['branch'] or '(default)'}\n"
            f"- **Prompt:** {serialized['prompt_preview']}\n"
            f"- **Tests:** {serialized['test_count']} total — "
            f"{serialized['passed_count']} pass / {serialized['failed_count']} fail\n"
            f"- **Duration:** {serialized['duration_ms']}ms\n"
            f"- **Cost:** ${serialized['cost_usd']:.4f}\n"
            f"- **Created:** {serialized['created_at']}\n"
            f"- **Completed:** {serialized['completed_at'] or '—'}\n"
        )
        return ToolResult(success=True, output=output, data=serialized)


# ---------------------------------------------------------------------------
# 3. get_logs — events / tool output for a run
# ---------------------------------------------------------------------------


class GetLogsTool(BaseTool):
    name = "get_logs"
    default_level = "allow"
    description = (
        "Get the recent event/tool/log output for a run. Returns the "
        "agent's tool calls, tool results, errors, and key lifecycle "
        "events. Use when the user asks 'why did this run fail?' or "
        "'what did the agent do?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Run ID (full or first 8 chars)"},
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                    "kinds": {"type": "array",
                              "items": {"type": "string",
                                        "enum": ["", "tool", "llm", "run", "error"]},
                              "default": []},
                },
                "required": ["run_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        run_id = (kwargs.get("run_id") or "").strip()
        if not run_id:
            return ToolResult(success=False, output="`run_id` is required", error="missing_arg")
        try:
            limit = max(1, min(200, int(kwargs.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50

        # The agent emits `StreamEvent` instances (ToolExecutionStarted,
        # LLMCallStarted, etc.) into the EventBus. They are persisted
        # by the `EventSourceSink`. We read them back here.
        try:
            rows = await store.db.fetch(
                "SELECT id, event_type, payload, created_at "
                "FROM stream_events WHERE session_id = $1 "
                "ORDER BY id DESC LIMIT $2",
                run_id, limit,
            )
        except Exception as exc:
            logger.warning("get_logs: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")

        if not rows:
            return ToolResult(
                success=True,
                output=f"No events recorded for run `{run_id[:8]}`.",
                data={"events": []},
            )

        events: list[dict[str, Any]] = []
        lines: list[str] = [f"## Last {len(rows)} event(s) for `{run_id[:8]}`\n"]
        for r in rows:
            payload = r["payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    payload = {}
            elif payload is None:
                payload = {}
            etype = r["event_type"]
            preview = ""
            if isinstance(payload, dict):
                preview = (
                    payload.get("output_preview")
                    or payload.get("error")
                    or payload.get("content")
                    or ""
                )
                if isinstance(preview, str) and len(preview) > 200:
                    preview = preview[:200] + "..."
            events.append({
                "id": r["id"], "event_type": etype,
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                "payload": payload,
            })
            lines.append(f"- `{r['id']:>5}` {etype}  {preview}")
        return ToolResult(success=True, output="\n".join(lines), data={"events": events})


# ---------------------------------------------------------------------------
# 4. list_testcases — test case inventory
# ---------------------------------------------------------------------------


class ListTestCasesTool(BaseTool):
    name = "list_testcases"
    default_level = "allow"
    description = (
        "List test cases with optional filters by status, type, and "
        "project. Returns the test name, type (api/e2e/unit/etc.), "
        "status (pending/passing/failing), and priority. Use when the "
        "user asks 'what tests do we have?' or 'which tests are "
        "failing?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string",
                               "enum": ["", "pending", "passing", "failing", "skipped"],
                               "default": ""},
                    "test_type": {"type": "string",
                                  "enum": ["", "api", "e2e", "unit", "integration"],
                                  "default": ""},
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        status = kwargs.get("status") or ""
        test_type = kwargs.get("test_type") or ""
        try:
            limit = max(1, min(200, int(kwargs.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50

        clauses: list[str] = []
        params: list[Any] = []
        if status:
            params.append(status)
            clauses.append(f"status = ${len(params)}")
        if test_type:
            params.append(test_type)
            clauses.append(f"test_type = ${len(params)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        sql = (
            "SELECT id, name, test_type, status, priority, "
            f"updated_at FROM test_cases {where} "
            f"ORDER BY updated_at DESC LIMIT ${len(params)}"
        )
        try:
            rows = await store.db.fetch(sql, *params)
        except Exception as exc:
            logger.warning("list_testcases: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if not rows:
            return ToolResult(success=True, output="No test cases found.", data={"test_cases": []})
        lines = [f"## {len(rows)} test case(s)\n"]
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r["id"], "name": r["name"],
                "test_type": r["test_type"], "status": r["status"],
                "priority": r.get("priority") or "medium",
            })
            lines.append(f"- `{r['id'][:8]}` [{r['status']}/{r['test_type']}/{r.get('priority') or 'medium'}] {r['name']}")
        return ToolResult(success=True, output="\n".join(lines), data={"test_cases": out})


# ---------------------------------------------------------------------------
# 5. get_testcase — single test case with code
# ---------------------------------------------------------------------------


class GetTestCaseTool(BaseTool):
    name = "get_testcase"
    default_level = "allow"
    description = (
        "Get a single test case by id (or first 8 chars), including "
        "its code, language, and current status. Use when the user "
        "asks 'show me the test for X' or 'what does the failing test "
        "look like?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "testcase_id": {"type": "string", "description": "Test case ID"},
                },
                "required": ["testcase_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        testcase_id = (kwargs.get("testcase_id") or "").strip()
        if not testcase_id:
            return ToolResult(success=False, output="`testcase_id` is required", error="missing_arg")
        if len(testcase_id) >= 8:
            row = await store.db.fetchrow(
                "SELECT id, name, description, test_type, status, priority, "
                "code, code_language, error_message, updated_at "
                "FROM test_cases WHERE id = $1 OR id LIKE $2 LIMIT 1",
                testcase_id, f"{testcase_id}%",
            )
        else:
            row = await store.db.fetchrow(
                "SELECT id, name, description, test_type, status, priority, "
                "code, code_language, error_message, updated_at "
                "FROM test_cases WHERE id LIKE $1 LIMIT 1",
                f"{testcase_id}%",
            )
        if not row:
            return ToolResult(success=False, output=f"No test case found matching '{testcase_id}'", error="not_found")
        data = dict(row)
        output = (
            f"## Test `{data['id'][:8]}` — {data['name']}\n\n"
            f"- **Type:** {data.get('test_type') or '?'}\n"
            f"- **Status:** {data.get('status') or '?'}\n"
            f"- **Priority:** {data.get('priority') or 'medium'}\n"
            f"- **Language:** {data.get('code_language') or '?'}\n"
            f"- **Updated:** {data.get('updated_at')}\n"
        )
        if data.get("description"):
            output += f"\n**Description:** {data['description']}\n"
        if data.get("error_message"):
            output += f"\n**Last error:**\n```\n{data['error_message']}\n```\n"
        if data.get("code"):
            output += f"\n**Code:**\n```{data.get('code_language') or ''}\n{data['code']}\n```\n"
        return ToolResult(success=True, output=output, data=data)


# ---------------------------------------------------------------------------
# 6. get_run_artifacts — files generated by a run
# ---------------------------------------------------------------------------


class GetRunArtifactsTool(BaseTool):
    name = "get_run_artifacts"
    default_level = "allow"
    description = (
        "List files (test files, coverage reports, logs) generated by a "
        "run. Returns path, size, and MIME type. Use when the user "
        "asks 'what files did the agent produce?' or 'where is the "
        "test file from run X?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Run/session ID"},
                },
                "required": ["session_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        session_id = (kwargs.get("session_id") or "").strip()
        if not session_id:
            return ToolResult(success=False, output="`session_id` is required", error="missing_arg")
        try:
            rows = await store.db.fetch(
                "SELECT id, path, size_bytes, mime_type, description, created_at "
                "FROM artifacts WHERE session_id = $1 "
                "ORDER BY created_at DESC",
                session_id,
            )
        except Exception as exc:
            logger.warning("get_run_artifacts: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if not rows:
            return ToolResult(success=True, output=f"No artifacts for session `{session_id[:8]}`.", data={"artifacts": []})
        out = []
        lines = [f"## {len(rows)} artifact(s) for `{session_id[:8]}`\n"]
        for r in rows:
            out.append({
                "id": r["id"], "path": r["path"],
                "size_bytes": r["size_bytes"], "mime_type": r.get("mime_type") or "text/plain",
                "description": r.get("description") or "",
            })
            lines.append(
                f"- `{r['path']}` ({r['size_bytes']}B, {r.get('mime_type') or 'text/plain'})"
                + (f" — {r['description']}" if r.get("description") else "")
            )
        return ToolResult(success=True, output="\n".join(lines), data={"artifacts": out})


# ---------------------------------------------------------------------------
# 7. search_runs — find runs by repo / branch / prompt fragment
# ---------------------------------------------------------------------------


class SearchRunsTool(BaseTool):
    name = "search_runs"
    default_level = "allow"
    description = (
        "Search runs by repo URL, branch, or a fragment of the prompt. "
        "Returns the matching runs. Use when the user asks 'have we "
        "tested <repo>?' or 'show me runs that mention X'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string"},
                    "branch": {"type": "string"},
                    "query": {"type": "string", "description": "Substring to match in the prompt"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        repo_url = (kwargs.get("repo_url") or "").strip()
        branch = (kwargs.get("branch") or "").strip()
        query = (kwargs.get("query") or "").strip()
        try:
            limit = max(1, min(100, int(kwargs.get("limit", 20))))
        except (TypeError, ValueError):
            limit = 20
        if not (repo_url or branch or query):
            return ToolResult(success=False, output="At least one of repo_url, branch, query is required", error="missing_arg")

        clauses: list[str] = []
        params: list[Any] = []
        if repo_url:
            params.append(f"%{repo_url}%")
            clauses.append(f"inputs->>'repo_url' ILIKE ${len(params)}")
        if branch:
            params.append(f"%{branch}%")
            clauses.append(f"inputs->>'branch' ILIKE ${len(params)}")
        if query:
            params.append(f"%{query}%")
            clauses.append(
                f"(inputs->>'requirements' ILIKE ${len(params)} "
                f"OR inputs->>'prompt' ILIKE ${len(params)})"
            )
        where = "WHERE " + " AND ".join(clauses)
        params.append(limit)
        sql = (
            "SELECT id, status, inputs, test_count, passed_count, failed_count, "
            "duration, cost_usd, created_at, completed_at "
            f"FROM pipeline_runs {where} "
            f"ORDER BY created_at DESC LIMIT ${len(params)}"
        )
        try:
            rows = await store.db.fetch(sql, *params)
        except Exception as exc:
            logger.warning("search_runs: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")
        if not rows:
            return ToolResult(success=True, output="No matching runs found.", data={"runs": []})
        serialized = [_serialize_run(dict(r)) for r in rows]
        lines = [f"## {len(serialized)} matching run(s)\n"]
        for r in serialized[:10]:
            short = r["prompt_preview"][:60] or "(no prompt)"
            lines.append(
                f"- `{r['id'][:8]}` [{r['status']}] {r['repo_url']}@{r['branch']} — {short}"
            )
        if len(serialized) > 10:
            lines.append(f"\n(... {len(serialized) - 10} more)")
        return ToolResult(success=True, output="\n".join(lines), data={"runs": serialized})


# ---------------------------------------------------------------------------
# 8. get_dashboard_status — top-level summary
# ---------------------------------------------------------------------------


class GetDashboardStatusTool(BaseTool):
    name = "get_dashboard_status"
    default_level = "allow"
    description = (
        "Get a one-shot summary of the harness's current state: run "
        "counts by status, last 24h token/cost spend, open kanban tasks, "
        "and recent test-case counts. Use when the user asks 'what's "
        "going on?' or 'give me a status overview'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={"type": "object", "properties": {}},
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        try:
            status_rows = await store.db.fetch(
                "SELECT status, COUNT(*) AS n FROM pipeline_runs GROUP BY status",
            )
            total_cost_row = await store.db.fetchrow(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                "FROM token_usage WHERE created_at > NOW() - INTERVAL '24 hours'",
            )
            total_tokens_row = await store.db.fetchrow(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS total "
                "FROM token_usage WHERE created_at > NOW() - INTERVAL '24 hours'",
            )
            tc_count_row = await store.db.fetchrow(
                "SELECT COUNT(*) AS n FROM test_cases",
            )
        except Exception as exc:
            logger.warning("get_dashboard_status: query failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}", error="db_error")

        status_counts = {r["status"]: r["n"] for r in status_rows}
        lines = ["## Dashboard summary\n"]
        lines.append("**Run counts by status:**")
        if status_counts:
            for status, n in sorted(status_counts.items()):
                lines.append(f"- {status}: {n}")
        else:
            lines.append("- (no runs yet)")
        lines.append("")
        lines.append(
            f"**Last 24h:** {int(total_tokens_row['total'] or 0)} tokens, "
            f"${float(total_cost_row['total'] or 0):.4f}"
        )
        lines.append(f"**Test cases total:** {tc_count_row['n']}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={
                "run_counts": status_counts,
                "last_24h_tokens": int(total_tokens_row["total"] or 0),
                "last_24h_cost_usd": float(total_cost_row["total"] or 0),
                "test_case_count": tc_count_row["n"],
            },
        )


# ---------------------------------------------------------------------------
# 9. get_coverage — coverage history for a run
# ---------------------------------------------------------------------------


class GetCoverageTool(BaseTool):
    name = "get_coverage"
    default_level = "allow"
    description = (
        "Get the coverage report(s) for a run. Returns language, "
        "framework, and line coverage. Use when the user asks 'how "
        "much of the code is covered?' or 'what's the coverage for "
        "run X?'."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Run ID (optional — omit for latest)"},
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        store = _store()
        if store is None or getattr(store, "db", None) is None:
            return ToolResult(success=False, output="Introspection store not initialized", error="not_initialized")
        run_id = (kwargs.get("run_id") or "").strip()

        if run_id:
            if len(run_id) >= 8:
                rows = await store.db.fetch(
                    "SELECT language, framework, line_coverage, branch_coverage, "
                    "total_lines, covered_lines, created_at "
                    "FROM coverage_reports WHERE run_id = $1 OR run_id LIKE $2 "
                    "ORDER BY created_at DESC",
                    run_id, f"{run_id}%",
                )
            else:
                rows = await store.db.fetch(
                    "SELECT language, framework, line_coverage, branch_coverage, "
                    "total_lines, covered_lines, created_at "
                    "FROM coverage_reports WHERE run_id LIKE $1 "
                    "ORDER BY created_at DESC",
                    f"{run_id}%",
                )
        else:
            rows = await store.db.fetch(
                "SELECT language, framework, line_coverage, branch_coverage, "
                "total_lines, covered_lines, created_at, run_id "
                "FROM coverage_reports ORDER BY created_at DESC LIMIT 20",
            )

        if not rows:
            scope = f"for run `{run_id[:8]}`" if run_id else "(no reports)"
            return ToolResult(success=True, output=f"No coverage reports {scope}.", data={"reports": []})
        out = []
        lines = [f"## {len(rows)} coverage report(s)\n"]
        for r in rows:
            out.append({
                "language": r["language"], "framework": r["framework"],
                "line_coverage": float(r["line_coverage"] or 0),
                "branch_coverage": float(r.get("branch_coverage") or 0),
                "total_lines": r["total_lines"], "covered_lines": r["covered_lines"],
            })
            lines.append(
                f"- {r['language']} / {r['framework']}: "
                f"{float(r['line_coverage'] or 0):.1f}% line "
                f"({r['covered_lines']}/{r['total_lines']})"
            )
        return ToolResult(success=True, output="\n".join(lines), data={"reports": out})


# ---------------------------------------------------------------------------
# Register the tools with the registry.
# Each one is registered in the `read` toolset so the chat Role's
# `CHAT_READONLY_TOOLSET` (which composes from the `read` toolset) gets
# them all. The orchestrator Role can opt out by listing its own
# toolset explicitly.
# ---------------------------------------------------------------------------

registry.register(ListRunsTool(), toolset="read")
registry.register(GetRunTool(), toolset="read")
registry.register(GetLogsTool(), toolset="read")
registry.register(ListTestCasesTool(), toolset="read")
registry.register(GetTestCaseTool(), toolset="read")
registry.register(GetRunArtifactsTool(), toolset="read")
registry.register(SearchRunsTool(), toolset="read")
registry.register(GetDashboardStatusTool(), toolset="read")
registry.register(GetCoverageTool(), toolset="read")
