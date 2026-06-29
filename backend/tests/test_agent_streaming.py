"""Tests for agent streaming — asserts on StreamEvent sequences from run_stream().

Uses FakeLLMRouter for deterministic, fast, no-API agent-loop tests.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.agent import Agent, AgentDependencies
from harness.core.events import (
    AgentCompleted,
    AgentStarted,
    StreamEvent,
    TokenGenerated,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from harness.delegation import DelegationContext
from harness.events import EventBus
from harness.permissions.manager import PermissionManager
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry as _registry

from tests.conftest import FakePermissions, FakeStore
from tests.fake_llm import FakeChunk, FakeLLMRouter, make_tool_chunks


class MockEchoTool(BaseTool):
    name = "mock_echo"
    description = "Echoes input back"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output=f"echo: {kwargs.get('text', '')}")


_echo_registered = False


def _ensure_mock_tool():
    global _echo_registered
    if not _echo_registered:
        if not _registry.get("mock_echo"):
            _registry.register(MockEchoTool(), toolset="test")
        _echo_registered = True


def _make_agent(llm: FakeLLMRouter) -> Agent:
    """Build a minimal Agent for testing, wired to a FakeLLMRouter."""
    bus = EventBus()
    deps = AgentDependencies(
        llm=llm,
        store=FakeStore(),
        permissions=FakePermissions(),
        event_bus=bus,
    )
    _ensure_mock_tool()
    return Agent(
        deps=deps,
        mode="auto",
        allowed_tools=["mock_echo"],
        max_tool_rounds=5,
        system_prompt="You are a test agent.",
    )


async def _collect(agent: Agent, prompt: str) -> list[StreamEvent]:
    """Run agent.run_stream() and collect all emitted StreamEvents."""
    return [ev async for ev in agent.run_stream(prompt)]


class TestStreamEventEmission:
    """Verify that run_stream() emits the correct StreamEvent sequence."""

    async def test_simple_response(self):
        """A single LLM response with text only → TokenGenerated + AgentCompleted."""
        llm = FakeLLMRouter([FakeChunk(content="Hello world")])
        agent = _make_agent(llm)
        events = await _collect(agent, "say hello")

        assert len(events) >= 2
        assert isinstance(events[-1], AgentCompleted)
        assert events[-1].output_preview.startswith("Hello world")

        tokens = [e for e in events if isinstance(e, TokenGenerated)]
        assert len(tokens) >= 1
        full = "".join(t.content for t in tokens)
        assert full == "Hello world"

    async def test_tool_call_sequence(self):
        """A tool-calling response emits ToolExecutionStarted + ToolExecutionCompleted."""
        chunks = make_tool_chunks("using tool ", "mock_echo", '{"text": "hello"}', "tc1")
        llm = FakeLLMRouter(chunks)
        agent = _make_agent(llm)
        agent.max_tool_rounds = 1
        events = await _collect(agent, "use echo tool")

        starts = [e for e in events if isinstance(e, ToolExecutionStarted)]
        completions = [e for e in events if isinstance(e, ToolExecutionCompleted)]
        assert len(starts) == 1
        assert len(completions) == 1
        assert starts[0].tool_name == "mock_echo"
        assert completions[0].tool_name == "mock_echo"
        assert "echo:" in completions[0].output_preview

    async def test_agent_started_emitted(self):
        """AgentStarted event should be emitted via EventBus during run_stream."""
        llm = FakeLLMRouter([FakeChunk(content="ok")])
        agent = _make_agent(llm)
        events = await _collect(agent, "start test")

        started = [e for e in events if isinstance(e, AgentStarted)]
        assert len(started) == 1
        assert started[0].input == "start test"


class TestFakeLLMRouter:
    """Verify the FakeLLMRouter itself works correctly."""

    async def test_chat_stream_yields_chunks(self):
        llm = FakeLLMRouter([FakeChunk(content="a"), FakeChunk(content="b")])
        chunks = []
        async for c in llm.chat_stream():
            chunks.append(c)
        assert len(chunks) == 2

    async def test_chat_returns_concatenated(self):
        llm = FakeLLMRouter([FakeChunk(content="hello "), FakeChunk(content="world")])
        resp = await llm.chat()
        assert resp.content == "hello world"

    async def test_call_count(self):
        llm = FakeLLMRouter([FakeChunk(content="x")])
        assert llm.call_count == 0
        async for _ in llm.chat_stream():
            pass
        assert llm.call_count == 1
        await llm.chat()
        assert llm.call_count == 2
