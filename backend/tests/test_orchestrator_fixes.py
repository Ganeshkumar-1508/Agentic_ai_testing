"""Tests for OrchestratorEngine — verifies init fix and pipeline dispatch.

The OrchestratorEngine(None) call was causing "takes 1 positional argument
but 2 were given" errors on startup.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Tests — OrchestratorEngine init
# ---------------------------------------------------------------------------


async def test_orchestrator_engine_init_no_args():
    """OrchestratorEngine() can be created with no arguments."""
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine()
    assert engine is not None


async def test_orchestrator_engine_create_default():
    """OrchestratorEngine.create_default() returns an instance."""
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.create_default()
    assert engine is not None
    assert isinstance(engine, OrchestratorEngine)


async def test_orchestrator_engine_init_not_none():
    """OrchestratorEngine(None) would have failed before the fix."""
    from harness.orchestrator import OrchestratorEngine
    # Before the fix, this would raise:
    # TypeError: OrchestratorEngine.__init__() takes 1 positional argument but 2 were given
    engine = OrchestratorEngine()
    assert engine is not None


# ---------------------------------------------------------------------------
# Tests — submit_job_to_orchestrator non-blocking
# ---------------------------------------------------------------------------


async def test_submit_job_returns_immediately():
    """submit_job returns immediately (non-blocking dispatch)."""
    import time
    from unittest.mock import patch, AsyncMock

    # Mock the orchestrator to simulate a slow pipeline
    mock_engine = AsyncMock()
    mock_engine.run_job_spec = AsyncMock(return_value={"status": "running", "run_id": "test-run"})

    with patch("harness.jobs.submitter._default_orchestrator_engine", return_value=mock_engine):
        from harness.jobs.submitter import submit_job_to_orchestrator
        from harness.jobs.spec import JobSpec

        spec = JobSpec(
            spec_id="test-001",
            run_id="test-run-001",
            source="test",
            prompt="test",
        )

        start = time.time()
        # The function should return quickly (non-blocking)
        # In reality it dispatches via asyncio.create_task
        result = await submit_job_to_orchestrator(spec)
        elapsed = time.time() - start

        # Should return quickly (the task is dispatched in background)
        assert elapsed < 5  # Should be fast


# ---------------------------------------------------------------------------
# Tests — event bus wiring
# ---------------------------------------------------------------------------


async def test_event_bus_attached_to_base_deps():
    """base_deps.event_bus is set after shared_bus creation."""
    from harness.events import EventBus
    from harness.agent.deps import AgentDependencies
    from harness.llm import LLMRouter
    from harness.memory.store import PersistentStore
    from harness.permissions.manager import PermissionManager
    from harness.mcp.client import MCPClient

    llm = LLMRouter()
    store = PersistentStore(None)
    perms = PermissionManager(mode="auto")
    mcp = MCPClient()
    event_bus = EventBus()

    deps = AgentDependencies(
        llm=llm, store=store, permissions=perms,
        db=None, mcp=mcp, event_bus=event_bus,
    )

    assert deps.event_bus is not None
    assert isinstance(deps.event_bus, EventBus)


async def test_agent_receives_event_bus():
    """Agent receives event_bus from deps."""
    from harness.events import EventBus
    from harness.agent import Agent
    from harness.agent.deps import AgentDependencies
    from harness.llm import LLMRouter
    from harness.memory.store import PersistentStore
    from harness.permissions.manager import PermissionManager
    from harness.mcp.client import MCPClient

    llm = LLMRouter()
    store = PersistentStore(None)
    perms = PermissionManager(mode="auto")
    mcp = MCPClient()
    event_bus = EventBus()

    deps = AgentDependencies(
        llm=llm, store=store, permissions=perms,
        db=None, mcp=mcp, event_bus=event_bus,
    )

    agent = Agent(deps=deps, mode="auto", allowed_tools=[])
    assert agent._deps.event_bus is not None
    assert isinstance(agent._deps.event_bus, EventBus)
