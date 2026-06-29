"""Unit tests for the 3 new agent capabilities (shipped in this session).

  1. ReflexionMixin: self-critique injection after tool errors
  2. curate_subagent_context: context pre-fill for delegate_task
  3. validate_subagent_output: subagent output sanity-check

All three are exercised against the real Agent class (no LLM mock needed
for the standalone helpers; for Reflexion we use a tool that always errors).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.agent import (
    Agent,
    AgentDependencies,
    ValidationResult,
    curate_subagent_context,
    validate_subagent_output,
)
from harness.events import EventBus
from harness.llm import ChatMessage
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry as _registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class AlwaysErrorTool(BaseTool):
    name = "always_error"
    description = "Always returns an error (for testing reflexion)"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={"type": "object"})

    async def run(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, output="", error="simulated tool failure")


class _Chunk:
    """Minimal stream chunk for chat_stream (matches loop.py expectations)."""

    def __init__(self, content=None, tool_calls=None):
        delta = {}
        if content is not None:
            delta["content"] = content
        if tool_calls:
            delta["tool_calls"] = [
                SimpleNamespace(
                    index=tc.get("index", 0),
                    id=tc.get("id", ""),
                    function=SimpleNamespace(
                        name=tc.get("function", {}).get("name", ""),
                        arguments=tc.get("function", {}).get("arguments", ""),
                    ),
                )
                for tc in tool_calls
            ]
        self.choices = [SimpleNamespace(delta=SimpleNamespace(**delta), index=0)]


class FakeLLM:
    """Records every stream request; replays pre-loaded chunks in order."""

    def __init__(self, streams: list[list[_Chunk]]):
        self._streams = streams
        self._idx = 0

    async def chat_stream(self, *args, **kwargs):
        if self._idx < len(self._streams):
            for chunk in self._streams[self._idx]:
                yield chunk
            self._idx += 1


@pytest.fixture
def error_tool_registered():
    if not _registry.get("always_error"):
        _registry.register(AlwaysErrorTool(), toolset="test")
    yield


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. ReflexionMixin tests
# ---------------------------------------------------------------------------


class TestReflexion:
    def test_agent_has_methods(self):
        """Agent class has all expected methods (post-mixin consolidation)."""
        assert hasattr(Agent, "run")
        assert hasattr(Agent, "run_stream")
        assert hasattr(Agent, "interrupt")
        assert hasattr(Agent, "_should_reflect")
        assert hasattr(Agent, "_build_reflection")
        assert hasattr(Agent, "_execute_with_recovery")
        assert hasattr(Agent, "_emit")

    def test_should_reflect_on_error(self, error_tool_registered, fake_store, fake_permissions):
        deps = AgentDependencies(
            llm=FakeLLM([[]]), store=fake_store,
            permissions=fake_permissions, event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", max_tool_rounds=2, allowed_tools=["always_error"])
        # No errors → no reflection
        assert not agent._should_reflect([("c1", "always_error", "all good")])
        # Error in result → reflect
        assert agent._should_reflect([("c1", "always_error", "Error: boom")])
        assert agent._should_reflect([("c1", "always_error", "Exception: oops")])
        assert agent._should_reflect([("c1", "always_error", "Traceback (most recent call last)...")])

    def test_reflection_caps(self, error_tool_registered, fake_store, fake_permissions):
        deps = AgentDependencies(
            llm=FakeLLM([[]]), store=fake_store,
            permissions=fake_permissions, event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", max_tool_rounds=5, allowed_tools=["always_error"])
        agent._reflection_count = 3  # at the cap
        assert not agent._should_reflect([("c1", "always_error", "Error: x")])
        agent._reflection_count = 0
        agent._reflection_per_tool = {"always_error": 2}  # at per-tool cap
        assert not agent._should_reflect([("c1", "always_error", "Error: x")])

    def test_build_reflection_message(self, error_tool_registered, fake_store, fake_permissions):
        deps = AgentDependencies(
            llm=FakeLLM([[]]), store=fake_store,
            permissions=fake_permissions, event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", allowed_tools=["always_error"])
        msg = agent._build_reflection([
            ("c1", "always_error", "Error: tool failed at step 1"),
            ("c2", "other_tool", "ok"),
        ])
        assert "Self-critique" in msg
        assert "always_error" in msg
        assert "Error: tool failed" in msg
        # non-error tool should not be in the message
        assert "other_tool" not in msg or "ok" not in msg

    def test_record_reflection_increments(self, error_tool_registered, fake_store, fake_permissions):
        deps = AgentDependencies(
            llm=FakeLLM([[]]), store=fake_store,
            permissions=fake_permissions, event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", allowed_tools=["always_error"])
        agent._record_reflection([("c1", "always_error", "Error: x"), ("c2", "ok_tool", "ok")])
        assert agent._reflection_count == 1
        assert agent._reflection_per_tool.get("always_error") == 1
        assert "ok_tool" not in agent._reflection_per_tool  # only errors counted

    def test_reflexion_injected_in_loop(self, error_tool_registered, fake_store, fake_permissions):
        """End-to-end: when the tool errors, a self-critique message lands in
        the conversation before the next LLM call."""
        # Round 1: model calls always_error (which errors)
        round1 = _Chunk(tool_calls=[{
            "index": 0, "id": "c1",
            "function": {"name": "always_error", "arguments": "{}"},
        }])
        # Round 2: model sees reflexion message + tool error → emits final
        round2 = _Chunk(content="I see the tool errored. Let me try a different approach.")
        deps = AgentDependencies(
            llm=FakeLLM([[round1], [round2]]),
            store=fake_store,
            permissions=fake_permissions,
            event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto", max_tool_rounds=3, allowed_tools=["always_error"])
        agent.session_id = "test"

        result = _run(agent.run("try the failing tool"))
        # Verify the self-critique message was injected
        user_messages = [m for m in agent._messages if m.role == "user"]
        self_critique_msgs = [m for m in user_messages if "Self-critique" in (m.content or "")]
        assert len(self_critique_msgs) == 1
        # Verify counters updated
        assert agent._reflection_count == 1
        assert agent._reflection_per_tool.get("always_error") == 1


# ---------------------------------------------------------------------------
# 2. curate_subagent_context tests
# ---------------------------------------------------------------------------


class TestCuration:
    def test_skips_system_prompts(self):
        msgs = [
            ChatMessage(role="system", content="You are a code assistant."),
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there"),
        ]
        ctx = curate_subagent_context("any goal", msgs)
        assert "You are a code assistant" not in ctx
        assert "[user] Hello" in ctx
        assert "[assistant] Hi there" in ctx

    def test_truncates_to_max_chars(self):
        msgs = [
            ChatMessage(role="user", content="x" * 200),
            ChatMessage(role="assistant", content="y" * 200),
            ChatMessage(role="user", content="z" * 200),
        ]
        ctx = curate_subagent_context("goal", msgs, max_chars=300)
        # Should include at most 1-2 messages, not all 3
        assert len(ctx) <= 350  # some overhead for labels
        # Recent message (z) should be present
        assert "z" in ctx

    def test_handles_empty_messages(self):
        msgs = [
            ChatMessage(role="system", content="sys"),
            ChatMessage(role="user", content=""),
        ]
        ctx = curate_subagent_context("goal", msgs)
        assert ctx == "No prior context."

    def test_goal_included_in_header(self):
        msgs = [ChatMessage(role="user", content="do thing")]
        ctx = curate_subagent_context("specific goal", msgs)
        assert "specific goal" in ctx

    def test_truncates_long_message_content(self):
        msgs = [ChatMessage(role="user", content="a" * 5000)]
        ctx = curate_subagent_context("g", msgs, max_chars=4000)
        # Each message is capped at 500 chars
        assert len(ctx) < 4100


# ---------------------------------------------------------------------------
# 3. validate_subagent_output tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_empty_output(self):
        r = validate_subagent_output("")
        assert not r.valid
        assert "empty" in r.issues

    def test_none_output(self):
        r = validate_subagent_output(None)
        assert not r.valid
        assert "empty" in r.issues

    def test_error_prefix_caught(self):
        r = validate_subagent_output("Error: tool execution failed")
        assert not r.valid
        assert "error_prefix" in r.issues

    def test_exception_prefix_caught(self):
        r = validate_subagent_output("Exception: something went wrong")
        assert not r.valid
        assert "error_prefix" in r.issues

    def test_traceback_caught(self):
        r = validate_subagent_output("Traceback (most recent call last):\n  File...")
        assert not r.valid
        assert "error_prefix" in r.issues

    def test_normal_output_valid(self):
        r = validate_subagent_output("Task completed successfully.")
        assert r.valid
        assert r.issues == []

    def test_oversized_truncated(self):
        r = validate_subagent_output("x" * 100_000)
        assert not r.valid
        assert "too_long" in r.issues
        assert "truncated" in r.sanitized
        assert len(r.sanitized) <= 50_500

    def test_control_chars_rejected(self):
        r = validate_subagent_output("hello\x00world")
        assert not r.valid
        assert "control_chars" in r.issues

    def test_newline_and_tab_allowed(self):
        r = validate_subagent_output("line1\nline2\tcol2")
        assert r.valid

    def test_bool_coercion(self):
        r = validate_subagent_output("ok")
        assert bool(r) is True
        r2 = validate_subagent_output("Error: x")
        assert bool(r2) is False
