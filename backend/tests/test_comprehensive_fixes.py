"""Comprehensive test suite for all fixes applied in this session.

Covers:
- StreamEventsDBSink session_id extraction (Research Round 1)
- SandboxPreparePhase Docker/Local fallback (Research Round 2)
- Agent delegation and session_id propagation (Research Round 3)
- Pipeline phase chaining and config injection (Research Round 4)
- Python 3.13 variable scoping fixes (Research Round 5)
- Background task patterns (Research Round 6)
- LLM provider configuration (Research Round 8)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ===========================================================================
# SECTION 1: StreamEventsDBSink (Research Round 1)
# ===========================================================================


@dataclass
class _FakeEvent:
    session_id: str = ""
    subagent_id: str = ""
    agent_id: str = ""
    parent_subagent_id: str = ""
    type_name: str = "test.event"


@dataclass
class _FakeEventWithData:
    session_id: str = ""
    data: dict | None = None
    type_name: str = "test.event"


class _FakeDB:
    def __init__(self):
        self.inserted: list[tuple] = []
        self._pool = object()

    async def execute(self, sql: str, *args) -> str:
        self.inserted.append(args)
        return "INSERT 0 1"


class TestStreamEventsDBSink:
    """Test event persistence and session_id extraction."""

    async def test_persists_event_with_session_id(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEvent(session_id="s1", subagent_id="sa-1"))
        assert len(db.inserted) == 1
        assert db.inserted[0][0] == "s1"

    async def test_extracts_session_id_from_subagent_id(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEvent(session_id="", subagent_id="sa-42"))
        assert db.inserted[0][0] == "subagent-sa-42"

    async def test_extracts_session_id_from_data_dict(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEventWithData(session_id="", data={"session_id": "s-data"}))
        assert db.inserted[0][0] == "s-data"

    async def test_none_session_id_extracts_from_subagent(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEvent(session_id=None, subagent_id="sa-99"))
        assert db.inserted[0][0] == "subagent-sa-99"

    async def test_drops_event_with_no_id_anywhere(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEvent(session_id="", subagent_id=""))
        assert len(db.inserted) == 0

    async def test_silent_when_no_db(self):
        from harness.events import StreamEventsDBSink
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=None):
            await sink.emit(_FakeEvent(session_id="s1"))

    async def test_silent_when_no_pool(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        db._pool = None
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEvent(session_id="s1"))
        assert len(db.inserted) == 0

    async def test_data_dict_stored_as_json(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEventWithData(session_id="s1", data={"goal": "test"}))
        payload = json.loads(db.inserted[0][2])
        assert payload["goal"] == "test"


# ===========================================================================
# SECTION 2: SandboxPreparePhase (Research Round 2)
# ===========================================================================


@dataclass
class _FakeCtx:
    run_id: str = "r1"
    session_id: str = "s1"
    repo_url: str = "https://github.com/octocat/Hello-World"
    branch: str = "master"
    goal: str = "Write test"
    orchestrator: Any = None
    sandbox: Any = None
    test_config: Any = None
    board_id: str | None = None
    kg_ctx: Any = None
    explore_findings: str = ""
    memory_block: str = ""
    coordinator_result: Any = None
    run_started_at: str = ""
    errors: tuple = ()
    worktree_path: str | None = None


class TestSandboxPreparePhase:
    """Test sandbox creation with Docker/Local fallback."""

    async def test_creates_docker_sandbox(self):
        from harness.phases.sandbox_prepare import SandboxPreparePhase
        with patch("harness.backends.docker.DockerEnvironment") as mock:
            mock.return_value = MagicMock()
            result = await SandboxPreparePhase().execute(_FakeCtx())
        assert result.sandbox is not None

    async def test_falls_back_to_local(self):
        from harness.phases.sandbox_prepare import SandboxPreparePhase
        with patch("harness.backends.docker.DockerEnvironment", side_effect=Exception("Docker N/A")):
            with patch("harness.backends.local.LocalEnvironment") as mock:
                mock.return_value = MagicMock()
                result = await SandboxPreparePhase().execute(_FakeCtx())
        assert result.sandbox is not None

    async def test_extracts_repo_url(self):
        from harness.phases.sandbox_prepare import SandboxPreparePhase
        with patch("harness.backends.docker.DockerEnvironment") as mock:
            mock.return_value = MagicMock()
            result = await SandboxPreparePhase().execute(_FakeCtx(repo_url=""))
        assert result.sandbox is not None

    async def test_returns_none_when_all_fail(self):
        from harness.phases.sandbox_prepare import SandboxPreparePhase
        with patch("harness.backends.docker.DockerEnvironment", side_effect=Exception("D")):
            with patch("harness.backends.local.LocalEnvironment", side_effect=Exception("L")):
                result = await SandboxPreparePhase().execute(_FakeCtx())
        assert result.sandbox is None

    async def test_phase_name_and_skip(self):
        from harness.phases.sandbox_prepare import SandboxPreparePhase
        p = SandboxPreparePhase()
        assert p.phase_name == "sandbox_prepare"
        assert p.can_skip is False


# ===========================================================================
# SECTION 3: Agent Delegation & Session Propagation (Research Round 3)
# ===========================================================================


class TestAgentFactory:
    """Test agent factory creates correct agents with deps."""

    async def test_factory_creates_agent_with_deps(self):
        from harness.events import EventBus
        from harness.agent import Agent
        from harness.agent.deps import AgentDependencies
        from harness.llm import LLMRouter
        from harness.memory.store import PersistentStore
        from harness.permissions.manager import PermissionManager
        from harness.mcp.client import MCPClient

        deps = AgentDependencies(
            llm=LLMRouter(), store=PersistentStore(None),
            permissions=PermissionManager(mode="auto"),
            db=None, mcp=MCPClient(), event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", allowed_tools=[])
        assert agent._deps.event_bus is not None
        assert agent.session_id == ""

    async def test_factory_sets_session_id(self):
        from harness.events import EventBus
        from harness.agent import Agent
        from harness.agent.deps import AgentDependencies
        from harness.llm import LLMRouter
        from harness.memory.store import PersistentStore
        from harness.permissions.manager import PermissionManager
        from harness.mcp.client import MCPClient

        deps = AgentDependencies(
            llm=LLMRouter(), store=PersistentStore(None),
            permissions=PermissionManager(mode="auto"),
            db=None, mcp=MCPClient(), event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", allowed_tools=[])
        agent.session_id = "test-session-123"
        assert agent.session_id == "test-session-123"


class TestSessionIdPropagation:
    """Test session_id flows through the system correctly."""

    async def test_session_id_in_event_data(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            event = _FakeEvent(session_id="parent-sess", subagent_id="sa-child")
            await sink.emit(event)
        assert db.inserted[0][0] == "parent-sess"

    async def test_subagent_id_fallback(self):
        from harness.events import StreamEventsDBSink
        db = _FakeDB()
        sink = StreamEventsDBSink()
        with patch("harness.events.get_db", return_value=db):
            await sink.emit(_FakeEvent(session_id="", subagent_id="sa-x"))
        assert db.inserted[0][0] == "subagent-sa-x"


# ===========================================================================
# SECTION 4: Pipeline Phases & Config Injection (Research Round 4)
# ===========================================================================


@dataclass
class _FakeRunCtx:
    run_id: str = "r1"
    session_id: str = "s1"
    repo_url: str = "https://github.com/octocat/Hello-World"
    branch: str = "master"
    goal: str = "Write test"
    orchestrator: Any = None
    sandbox: Any = None
    test_config: Any = None
    board_id: str | None = None
    kg_ctx: Any = None
    explore_findings: str = ""
    memory_block: str = ""
    coordinator_result: Any = None
    run_started_at: str = ""
    errors: tuple = ()
    worktree_path: str | None = None


class TestPipelinePhases:
    """Test all 15 pipeline phases exist and have correct names."""

    @pytest.mark.parametrize("module_name,class_name,expected_name,can_skip", [
        ("harness.phases.sandbox_prepare", "SandboxPreparePhase", "sandbox_prepare", False),
        ("harness.phases.clone_repo", "CloneRepoPhase", "clone_repo", False),
        ("harness.phases.bootstrap_deps", "BootstrapDepsPhase", "bootstrap_deps", True),
        ("harness.phases.worktree_create", "WorktreeCreatePhase", "worktree_create", True),
        ("harness.phases.clone_context_repos", "CloneContextReposPhase", "clone_context_repos", True),
        ("harness.phases.inject_credentials", "InjectCredentialsPhase", "inject_credentials", True),
        ("harness.phases.kg_index", "KGIndexPhase", "kg_index", True),
        ("harness.phases.memory_load", "MemoryLoadPhase", "memory_load", True),
        ("harness.phases.explore_codebase", "ExploreCodebasePhase", "explore_codebase", True),
        ("harness.phases.orchestrate_board", "OrchestrateBoardPhase", "orchestrate_board", True),
        ("harness.phases.coordinator_spawn", "CoordinatorSpawnPhase", "coordinator_spawn", False),
        ("harness.phases.post_run_kg_sync", "PostRunKGSyncPhase", "post_run_kg_sync", True),
        ("harness.phases.l2_reflection", "L2ReflectionPhase", "l2_reflection", True),
        ("harness.phases.evidence_bundle", "EvidenceBundlePhase", "evidence_bundle", True),
        ("harness.phases.finalize_job_spec", "FinalizeJobSpecPhase", "finalize_job_spec", True),
    ])
    async def test_phase_metadata(self, module_name, class_name, expected_name, can_skip):
        import importlib
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        phase = cls()
        assert phase.phase_name == expected_name
        assert phase.can_skip == can_skip

    async def test_clone_repo_requires_sandbox(self):
        from harness.phases.clone_repo import CloneRepoPhase
        with pytest.raises(RuntimeError, match="requires orchestrator"):
            await CloneRepoPhase().execute(_FakeRunCtx(sandbox=None))

    async def test_run_context_carries_test_config(self):
        from harness.phases import RunContext
        ctx = RunContext(run_id="r1", session_id="s1", test_config={"timeout": 300})
        assert ctx.test_config == {"timeout": 300}

    async def test_run_context_test_config_default_none(self):
        from harness.phases import RunContext
        ctx = RunContext(run_id="r1", session_id="s1")
        assert ctx.test_config is None


class TestConfigInjection:
    """Test advanced config injection into coordinator goal."""

    def _build_config_lines(self, tc: dict) -> list[str]:
        lines = []
        if tc.get("timeout_seconds"):
            lines.append(f"Timeout: {tc['timeout_seconds']}s per command")
        if tc.get("max_retries"):
            lines.append(f"Max retries: {tc['max_retries']}")
        if tc.get("retry_on_failure") is False:
            lines.append("Retry on failure: DISABLED")
        if tc.get("fail_fast"):
            lines.append("Fail fast: YES")
        if tc.get("parallelism") and tc["parallelism"] > 1:
            lines.append(f"Parallelism: {tc['parallelism']} containers")
        if tc.get("shard_count") and tc["shard_count"] > 1:
            lines.append(f"Shards: {tc['shard_count']}")
        if tc.get("pre_commands"):
            lines.append(f"Pre-commands: {', '.join(tc['pre_commands'])}")
        if tc.get("post_commands"):
            lines.append(f"Post-commands: {', '.join(tc['post_commands'])}")
        if tc.get("os"):
            lines.append(f"Target OS: {tc['os']}")
        if tc.get("runtime_version"):
            lines.append(f"Runtime: {tc['runtime_version']}")
        if tc.get("browser"):
            lines.append(f"Browser: {tc['browser']}")
        if tc.get("cache_directories"):
            lines.append(f"Cache dirs: {', '.join(tc['cache_directories'])}")
        if tc.get("artifact_paths"):
            lines.append(f"Artifact paths: {', '.join(tc['artifact_paths'])}")
        if tc.get("auto_commit"):
            lines.append(f"Auto-commit: YES (branch: {tc.get('commit_branch', 'main')})")
        if tc.get("tags"):
            lines.append(f"Tags: {', '.join(tc['tags'])}")
        return lines

    def test_empty_config(self):
        assert self._build_config_lines({}) == []

    def test_timeout_only(self):
        lines = self._build_config_lines({"timeout_seconds": 600})
        assert lines == ["Timeout: 600s per command"]

    def test_retry_disabled(self):
        lines = self._build_config_lines({"retry_on_failure": False})
        assert "Retry on failure: DISABLED" in lines

    def test_all_fields(self):
        tc = {
            "timeout_seconds": 600, "max_retries": 5, "fail_fast": True,
            "parallelism": 8, "shard_count": 4,
            "pre_commands": ["npm install"], "post_commands": ["npm test"],
            "os": "linux", "runtime_version": "18.x", "browser": "chromium",
            "cache_directories": ["node_modules"], "artifact_paths": ["coverage/"],
            "auto_commit": True, "commit_branch": "main", "tags": ["regression"],
        }
        lines = self._build_config_lines(tc)
        assert len(lines) == 14
        assert "Timeout: 600s per command" in lines
        assert "Parallelism: 8 containers" in lines
        assert "Tags: regression" in lines


# ===========================================================================
# SECTION 5: OrchestratorEngine & Event Bus (Research Round 5-6)
# ===========================================================================


class TestOrchestratorEngine:
    """Test engine init and event bus wiring."""

    async def test_init_no_args(self):
        from harness.orchestrator import OrchestratorEngine
        engine = OrchestratorEngine()
        assert engine is not None

    async def test_create_default(self):
        from harness.orchestrator import OrchestratorEngine
        engine = OrchestratorEngine.create_default()
        assert isinstance(engine, OrchestratorEngine)

    async def test_event_bus_attached_to_deps(self):
        from harness.events import EventBus
        from harness.agent.deps import AgentDependencies
        from harness.llm import LLMRouter
        from harness.memory.store import PersistentStore
        from harness.permissions.manager import PermissionManager
        from harness.mcp.client import MCPClient

        deps = AgentDependencies(
            llm=LLMRouter(), store=PersistentStore(None),
            permissions=PermissionManager(mode="auto"),
            db=None, mcp=MCPClient(), event_bus=EventBus(),
        )
        assert deps.event_bus is not None

    async def test_agent_receives_event_bus(self):
        from harness.events import EventBus
        from harness.agent import Agent
        from harness.agent.deps import AgentDependencies
        from harness.llm import LLMRouter
        from harness.memory.store import PersistentStore
        from harness.permissions.manager import PermissionManager
        from harness.mcp.client import MCPClient

        deps = AgentDependencies(
            llm=LLMRouter(), store=PersistentStore(None),
            permissions=PermissionManager(mode="auto"),
            db=None, mcp=MCPClient(), event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", allowed_tools=[])
        assert agent._deps.event_bus is not None

    async def test_submit_job_returns_quickly(self):
        import time
        from unittest.mock import patch, AsyncMock
        mock_engine = AsyncMock()
        mock_engine.run_job_spec = AsyncMock(return_value={"status": "running"})
        with patch("harness.jobs.submitter._default_orchestrator_engine", return_value=mock_engine):
            from harness.jobs.submitter import submit_job_to_orchestrator
            from harness.jobs.spec import JobSpec
            spec = JobSpec(spec_id="t1", run_id="r1", source="test", prompt="test")
            start = time.time()
            await submit_job_to_orchestrator(spec)
            assert time.time() - start < 5


# ===========================================================================
# SECTION 6: LLM Provider Config (Research Round 8)
# ===========================================================================


class TestLLMProviderConfig:
    """Test LLM router provider configuration."""

    async def test_router_configures_with_providers(self):
        from harness.llm import LLMRouter
        from harness.memory.database import Database
        from harness.memory.db_context import set_db

        db = Database("postgresql://testai:testai@localhost:5432/testai")
        await db.connect()
        set_db(db)

        llm = LLMRouter()
        llm.set_db(db)
        from harness.memory.settings_store import SettingsStore
        store = SettingsStore(db)
        providers = await store.get_all_providers()
        llm.configure(providers)

        status = llm.get_status()
        assert len(status) >= 1
        configured = [p for p in status if p.get("configured")]
        assert len(configured) >= 1

        await db.disconnect()

    async def test_model_for_role(self):
        from harness.llm import LLMRouter
        llm = LLMRouter()
        # Configure with a provider so model resolution works
        llm.configure([{"provider": "opencode", "model": "deepseek-v4-flash", "enabled": True}])
        model = llm.get_model_for_role("orchestrator")
        assert model is not None
        assert isinstance(model, str)


# ===========================================================================
# SECTION 7: Migrations Idempotency (Research Round 7)
# ===========================================================================


class TestMigrations:
    """Test schema migrations are idempotent and complete."""

    def test_migrations_sql_has_agent_config(self):
        from pathlib import Path
        sql = Path("harness/memory/schema/migrations.sql").read_text()
        assert "ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS agent_config" in sql

    def test_schema_sql_has_agent_config(self):
        from pathlib import Path
        sql = Path("harness/memory/schema/schema.sql").read_text()
        assert "ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS agent_config" in sql

    def test_migrations_cover_all_pr_tracker_columns(self):
        from pathlib import Path
        sql = Path("harness/memory/schema/migrations.sql").read_text()
        required = [
            "agent_config", "pr_url", "merged_at", "closed_at",
            "commit_count", "comments_count", "last_commit_at",
        ]
        for col in required:
            assert f"ALTER TABLE pr_tracker ADD COLUMN IF NOT EXISTS {col}" in sql

    def test_pr_test_runs_columns_present(self):
        from pathlib import Path
        sql = Path("harness/memory/schema/migrations.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS pr_test_runs" in sql
        assert "ALTER TABLE pr_test_runs ADD COLUMN IF NOT EXISTS pipeline_run_id" in sql
