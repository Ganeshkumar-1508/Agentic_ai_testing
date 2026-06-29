"""E2E smoke test."""
from __future__ import annotations
import asyncio, sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/tests")

from harness.agent import Agent, AgentDependencies
from harness.core.events import AgentCompleted, AgentStarted, TokenGenerated, ToolExecutionStarted, ToolExecutionCompleted
from harness.events import EventBus
from harness.tools.registry import registry
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from tests.fake_llm import FakeLLMRouter, FakeChunk, make_tool_chunks
from tests.conftest import FakePermissions, FakeStore


def by_type(events, tp):
    """Filter events by type — avoids comprehension scoping issues."""
    out = []
    for e in events:
        if isinstance(e, tp):
            out.append(e)
    return out


async def main():
    print("=" * 50)
    print("E2E Smoke Test")
    print("=" * 50)

    bus = EventBus()

    # Register echo tool
    if not registry.get("echo"):
        class _Echo(BaseTool):
            name = "echo"
            description = "Echo"
            def spec(self):
                return ToolSpec(name="echo", description="echo", input_schema={
                    "type": "object", "properties": {"text": {"type": "string"}}})
            async def run(self, **kwargs):
                return ToolResult(success=True, output=f"echo: {kwargs.get('text', '')}")
        registry.register(_Echo(), toolset="test")

    # Test 1: Text response
    print("\n[1] Text response...")
    llm = FakeLLMRouter([FakeChunk(content="Hello world")])
    deps = AgentDependencies(llm=llm, store=FakeStore(), permissions=FakePermissions(), event_bus=bus)
    agent = Agent(deps=deps, mode="auto", allowed_tools=["echo"], max_tool_rounds=2, system_prompt="Test agent.")
    agent.session_id = "e2e-1"
    events1 = [ev async for ev in agent.run_stream("say hello")]
    tokens1 = by_type(events1, TokenGenerated)
    assert len(tokens1) >= 1
    assert len(by_type(events1, AgentCompleted)) >= 1
    print(f"  OK — {len(events1)} events, {len(tokens1)} tokens")

    # Test 2: Tool call
    print("\n[2] Tool call...")
    chunks = make_tool_chunks("using ", "echo", '{"text": "hi"}', "tc1")
    llm2 = FakeLLMRouter(chunks)
    deps2 = AgentDependencies(llm=llm2, store=FakeStore(), permissions=FakePermissions(), event_bus=bus)
    agent2 = Agent(deps=deps2, mode="auto", allowed_tools=["echo"], max_tool_rounds=1, system_prompt="Test agent.")
    agent2.session_id = "e2e-2"
    events2 = [ev async for ev in agent2.run_stream("use echo")]
    starts = by_type(events2, ToolExecutionStarted)
    dones = by_type(events2, ToolExecutionCompleted)
    assert len(starts) == 1
    assert len(dones) == 1
    assert dones[0].success
    print(f"  OK — {starts[0].tool_name} -> {dones[0].output_preview}")

    # Test 3: AgentStarted
    print("\n[3] AgentStarted...")
    assert len(by_type(events1, AgentStarted)) >= 1
    print("  OK")

    print("\n" + "=" * 50)
    print("ALL PASSED — %d events across 2 runs" % (len(events1) + len(events2)))
    print("=" * 50)
    return True


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
