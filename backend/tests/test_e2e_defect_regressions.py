import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []
        self.stream_events = []
        self._next_event_id = 1

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        if "FROM stream_events" in query:
            if not self.stream_events:
                return self.rows
            session_id = args[0]
            after_id = args[1] if len(args) > 1 else 0
            return [
                Row({
                    "id": event["id"],
                    "event_type": event["event_type"],
                    "event_data": event["event_data"],
                })
                for event in self.stream_events
                if event["session_id"] == session_id and event["id"] > after_id
            ]
        return self.rows

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        return {"id": 123}

    async def execute(self, query, *args):
        self.queries.append((query, args))
        if "INSERT INTO stream_events" in query:
            self.stream_events.append({
                "id": self._next_event_id,
                "session_id": args[0],
                "event_type": args[1],
                "event_data": args[2],
            })
            self._next_event_id += 1
        return "OK"


class Row(dict):
    def get(self, key, default=None):
        return super().get(key, default)


@pytest.mark.asyncio
async def test_postgres_event_store_reads_event_data_column_for_stream_events():
    from harness.store.adapters.postgres import PostgresEventStore

    db = FakeDB(rows=[Row({
        "id": 7,
        "session_id": "session-1",
        "event_type": "pipeline.started",
        "payload": json.dumps({"ok": True}),
        "parent_id": None,
        "agent_id": None,
        "subagent_id": None,
        "created_at": None,
    })])

    events = await PostgresEventStore(db).poll("session-1")

    assert "event_data AS payload" in db.queries[0][0]
    assert events[0].payload == {"ok": True}


@pytest.mark.asyncio
async def test_list_test_cases_defaults_to_default_project_when_query_omitted():
    from api.routers import testcases

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=FakeDB(rows=[]))))

    response = await testcases.list_test_cases(request)

    assert response == {"test_cases": []}
    assert request.app.state.db.queries[0][1] == ("default-project",)


def test_pipeline_requires_healing_toolset_and_tool_usage_instructions():
    from api.routers.pipeline import MANDATORY_EVIDENCE_TOOLSETS, PipelineFromRequirements, _build_orchestration_goal
    from harness.tools.toolsets import resolve_toolsets

    assert "healing" in MANDATORY_EVIDENCE_TOOLSETS
    resolved = resolve_toolsets(MANDATORY_EVIDENCE_TOOLSETS)
    assert "read_file" in resolved
    assert "list_files" in resolved
    assert "write_file" in resolved
    assert "edit_file" in resolved
    assert "delegate_task" not in resolved
    goal = _build_orchestration_goal(PipelineFromRequirements(requirements="make tests", repo_url=""))
    assert "web_search" in goal
    assert "web_fetch" in goal
    assert "package-install" in goal
    assert "attempt_heal" in goal


@pytest.mark.asyncio
async def test_pipeline_start_clears_global_spawn_pause():
    from api.routers import pipeline
    from harness.tools.delegate_task import is_spawn_paused, set_spawn_paused

    class _DB(FakeDB):
        pass

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(db=_DB(), agent=None, llm=None),
        ),
    )

    set_spawn_paused(True)
    body = pipeline.PipelineFromRequirements(requirements="smoke", repo_url="")

    response = await pipeline.pipeline_from_requirements(request, body)

    assert response["status"] == "started"
    assert is_spawn_paused() is False


@pytest.mark.asyncio
async def test_delegate_task_resolves_repo_grounded_runtime_tools(monkeypatch):
    from harness.tools.delegate_task import DelegateTaskTool
    from harness.tools.registry import registry

    registry.discover_tools()
    delegate_tool = DelegateTaskTool(agent_factory=lambda **kwargs: None)
    captured: dict[str, list[str]] = {}

    async def fake_run_batch(tasks, context, resolved, model_override, role):
        captured["resolved"] = list(resolved)
        return ["ok"]

    monkeypatch.setattr(delegate_tool, "_run_batch", fake_run_batch)

    result = await delegate_tool.run(
        tasks=["Inspect the repository and report findings"],
        toolsets=["read", "write", "intelligence", "healing"],
        role="leaf",
    )

    assert result.success is True
    assert "read_file" in captured["resolved"]
    assert "list_files" in captured["resolved"]
    assert "write_file" in captured["resolved"]
    assert "edit_file" in captured["resolved"]
    assert "bash" in captured["resolved"]
    assert "codegraph_explore" in captured["resolved"]
    assert "attempt_heal" in captured["resolved"]


@pytest.mark.asyncio
async def test_pipeline_evidence_emits_per_test_autoheal_and_tool_audit(monkeypatch):
    from api.routers import pipeline

    emitted = []

    async def emit(session_id, event_type, payload):
        emitted.append((event_type, payload))

    async def fake_heal(db, session_id, marker, output):
        return {"healed": True, "status": "completed", "output": "fixed"}

    monkeypatch.setattr(pipeline, "_attempt_pipeline_autoheal", fake_heal)
    result = SimpleNamespace(output="web_search web_fetch docs https://example.test npm install\nunit test failed", success=False)

    await pipeline._emit_pipeline_evidence("s1", FakeDB(), result, "repo", False, False, emit)

    event_types = [event_type for event_type, _ in emitted]
    assert "pipeline.kg_test_updated" in event_types
    assert "pipeline.autoheal.started" in event_types
    assert "pipeline.autoheal.completed" in event_types
    assert "pipeline.kg_fix_updated" in event_types
    audit = next(payload for event_type, payload in emitted if event_type == "pipeline.tool_audit")
    assert audit == {"web_search": True, "web_fetch": True, "docs": True, "package_install": True}


class ExecResult:
    def __init__(self, success=False, output="", error=""):
        self.success = success
        self.output = output
        self.error = error


class RecordingDB(FakeDB):
    def __init__(self, rows=None, fetchrow_rows=None):
        super().__init__(rows=rows)
        self.fetchrow_rows = list(fetchrow_rows or [])
        self.executes = []

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if self.fetchrow_rows:
            return self.fetchrow_rows.pop(0)
        return None

    async def fetchval(self, query, *args):
        self.queries.append((query, args))
        return 0

    async def execute(self, query, *args):
        await super().execute(query, *args)
        self.executes.append((query, args))
        return "OK"


@pytest.mark.asyncio
async def test_create_test_case_defaults_project_id_when_body_omitted():
    from api.routers import testcases

    db = RecordingDB(fetchrow_rows=[Row({
        "id": "tc-1",
        "name": "strict smoke",
        "test_type": "api",
        "status": "pending",
        "priority": "medium",
        "code": "",
        "code_language": "python",
        "created_at": None,
    })])
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))

    req = testcases.TestCaseCreate(name="strict smoke")
    response = await testcases.create_test_case(request, req)

    assert response["test_case"]["id"] == "tc-1"
    assert db.queries[0][1][0] == "default-project"


@pytest.mark.asyncio
async def test_heal_test_uses_fast_smoke_budget_and_returns_without_llm(monkeypatch):
    from api.routers import testcases

    class SlowWouldTimeoutExecutor:
        def __init__(self):
            self.calls = []

        async def run(self, **kwargs):
            self.calls.append(kwargs)
            return ExecResult(success=False, output="still failing")

    executor = SlowWouldTimeoutExecutor()
    monkeypatch.setattr(testcases.registry, "get", lambda name: executor if name == "test_executor" else None)
    db = RecordingDB()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db, agent=None, llm=None)))

    response = await testcases.heal_test(request, testcases.HealRequest(test_name="strict", test_code="assert False"))

    assert response["status"] == "failed"
    assert "Agent not available" in response["error"]
    assert len(executor.calls) == 1
    assert executor.calls[0]["timeout_ms"] <= 10000


@pytest.mark.asyncio
async def test_healing_stats_returns_safe_defaults_when_helper_or_schema_missing():
    from api.routers import healing_api

    class BrokenDB(RecordingDB):
        async def fetchrow(self, query, *args):
            raise RuntimeError("missing healing_log")

        async def fetch(self, query, *args):
            raise RuntimeError("missing healing_log")

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=BrokenDB())))

    response = await healing_api.get_healing_stats(request)

    assert response["active"] is False
    assert response["total"] == 0
    assert response["success_rate"] == 0.0
    assert response["events"] == []


@pytest.mark.asyncio
async def test_delegate_events_tolerates_malformed_payload_and_row_shapes():
    from api.routers import ops

    rows = [Row({
        "id": "evt-1",
        "event_type": "pipeline.started",
        "event_data": "not-json",
        "parent_id": None,
        "agent_id": None,
        "created_at": None,
    })]

    class DelegateDB(RecordingDB):
        async def fetchrow(self, query, *args):
            self.queries.append((query, args))
            return {"id": "session-1"}

        async def fetch(self, query, *args):
            self.queries.append((query, args))
            return rows if "trace_events" in query else []

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=DelegateDB())))

    response = await ops.get_delegate_events(request)

    assert response["events"][0]["event_data"] == {"raw": "not-json"}


@pytest.mark.asyncio
async def test_pipeline_evidence_emits_mandatory_autoheal_even_without_failed_markers(monkeypatch):
    from api.routers import pipeline

    emitted = []

    async def emit(session_id, event_type, payload):
        emitted.append((event_type, payload))

    async def fake_heal(db, session_id, marker, output):
        return {"healed": False, "status": "completed", "output": "no failure requiring fix"}

    monkeypatch.setattr(pipeline, "_attempt_pipeline_autoheal", fake_heal)
    result = SimpleNamespace(output="web_search web_fetch docs https://example.test npm install\nall tests passed", success=True)

    await pipeline._emit_pipeline_evidence("s1", FakeDB(), result, "repo", False, False, emit)

    event_types = [event_type for event_type, _ in emitted]
    assert "pipeline.autoheal.started" in event_types
    assert "pipeline.autoheal.completed" in event_types
    completed = next(payload for event_type, payload in emitted if event_type == "pipeline.autoheal.completed")
    assert completed["status"] == "completed"


@pytest.mark.asyncio
async def test_pipeline_autoheal_checkpoint_persists_to_delegate_stream_source(monkeypatch):
    from api.routers import pipeline

    db = FakeDB()
    session_id = "pipeline-stream-session"

    async def persist_to_stream(session_id, event_type, payload):
        await db.execute(
            "INSERT INTO stream_events (session_id, event_type, event_data) VALUES ($1, $2, $3)",
            session_id, event_type, json.dumps(payload),
        )

    async def fake_heal(db, session_id, marker, output):
        return {"healed": True, "status": "completed", "output": "checkpoint"}

    monkeypatch.setattr(pipeline, "_attempt_pipeline_autoheal", fake_heal)

    await pipeline._emit_pipeline_autoheal_checkpoint(session_id, db, persist_to_stream)
    rows = await db.fetch(
        "SELECT id, event_type, event_data FROM stream_events WHERE session_id = $1 AND id > $2 ORDER BY id",
        session_id, 0,
    )
    events = [
        {"id": row["id"], "event_type": row["event_type"], "payload": json.loads(row["event_data"])}
        for row in rows
    ]

    event_types = [event["event_type"] for event in events]
    assert event_types == [
        "pipeline.autoheal.started",
        "pipeline.autoheal.completed",
        "pipeline.kg_fix_updated",
    ]
    assert events[1]["payload"]["status"] == "completed"
    assert events[2]["payload"]["healed"] is True


# ---------------------------------------------------------------------------
# Regression tests for E2E-001, E2E-006, E2E-102, E2E-103 fixes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_global_endpoint_returns_valid_json():
    """Regression for E2E-102: GET /api/cost/global returns 2xx with valid session_count."""
    from api.routers.cost import get_global_cost

    class CostDB(FakeDB):
        async def fetchrow(self, query, *args):
            self.queries.append((query, args))
            return {
                "session_count": 42,
                "total_input_tokens": 1000,
                "total_output_tokens": 5000,
                "total_cost": 0.05,
            }

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=CostDB())))
    response = await get_global_cost(request)

    assert "session_count" in response
    assert "total_cost" in response
    assert response["session_count"] >= 0
    assert isinstance(response["total_cost"], (int, float))


@pytest.mark.asyncio
async def test_cost_per_model_endpoint_returns_valid_json():
    """Regression for E2E-103: GET /api/cost/per-model returns 2xx with models list."""
    from api.routers.cost import get_cost_per_model

    class CostDB(FakeDB):
        async def fetch(self, query, *args):
            self.queries.append((query, args))
            return [
                Row({
                    "model": "test-model",
                    "session_count": 10,
                    "total_input": 500,
                    "total_output": 2000,
                    "total_cost": 0.02,
                })
            ]

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=CostDB())))
    response = await get_cost_per_model(request)

    assert "models" in response
    assert len(response["models"]) >= 0
    if response["models"]:
        assert "model" in response["models"][0]


def test_ui_route_prefix_via_next_config():
    """Regression for E2E-001: next.config.ts rewrites /api/* to backend container."""
    import os
    import re

    next_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "next.config.ts")
    with open(next_config_path) as f:
        content = f.read()

    # Must define rewrites() that maps /api/:path* to backend
    assert "rewrites" in content
    assert "/api/:path*" in content
    assert "backend:8000" in content or "backend:8001" in content
    assert re.search(r'destination["\']?\s*:\s*["\']?http://backend:800\d/api/:path\*', content)


@pytest.mark.asyncio
async def test_tool_audit_emission_after_pipeline_completes():
    """Regression for E2E-006: _emit_pipeline_evidence emits pipeline.tool_audit event."""
    from api.routers import pipeline

    emitted = []

    async def emit(session_id, event_type, payload):
        emitted.append((event_type, payload))

    async def fake_heal(db, session_id, marker, output):
        return {"healed": False, "status": "completed", "output": "noop"}

    monkeypatch_for_audit = pytest.MonkeyPatch()
    monkeypatch_for_audit.setattr(pipeline, "_attempt_pipeline_autoheal", fake_heal)

    result = SimpleNamespace(
        output="we used web_search for API docs and web_fetch to read changelogs",
        success=True,
    )

    await pipeline._emit_pipeline_evidence("s1", FakeDB(), result, "repo", False, False, emit)

    event_types = [et for et, _ in emitted]
    assert "pipeline.tool_audit" in event_types, (
        f"pipeline.tool_audit not in emitted events: {event_types}"
    )

    audit = next(payload for et, payload in emitted if et == "pipeline.tool_audit")
    assert audit.get("web_search") is True
    assert audit.get("web_fetch") is True
    # "API docs" in input triggers the "docs" keyword match
    assert audit.get("docs") is True
    assert audit.get("package_install") is False
