"""Tests for the unified HookPipeline — replacing MiddlewareChain.

Verifies:
  1. Phase ordering (DETERMINISTIC_GATE → MIDDLEWARE → PLUGIN)
  2. Middleware adapter (AgentMiddleware → pipeline methods)
  3. Gate blocking semantics (return False = block)
  4. Plugin hook registration and dispatch
  5. Message mutation via on_before_llm (chained)
  6. Tool result transform via on_after_tool (chained)
  7. All 7 lifecycle events fire in correct order
  8. Cross-pipeline isolation (each pipeline has its own registry)
  9. Backward compatibility with AgentMiddleware base class
"""

from __future__ import annotations

from harness.hook.pipeline import HookPipeline
from harness.hook.registry import HookRegistry
from harness.hook.phases import HookType
from harness.middleware.base import AgentMiddleware


class _CallRecorder(AgentMiddleware):
    """Records calls to a list for asserting execution order."""

    def __init__(self, name: str, calls: list):
        self.name = name
        self._calls = calls

    async def on_before_tool(self, name: str, args: dict) -> bool | None:
        self._calls.append(self.name)
        return None


class TestHookPipelinePhaseOrdering:
    """Phase 0 = deterministic gates, Phase 1 = middlewares, Phase 2 = plugins."""

    def test_gates_run_before_middlewares(self):
        calls = []
        p = HookPipeline()
        p.add_gate(lambda name, args: (calls.append("gate") is None) or True)
        p.add_middleware(_CallRecorder("mw", calls))
        import asyncio
        asyncio.run(p.on_before_tool("x", {}))
        assert calls == ["gate", "mw"], f"Expected gate before mw, got {calls}"

    def test_plugins_run_last(self):
        calls = []
        p = HookPipeline()

        async def plugin_fn(**kw):
            calls.append("plugin")

        p.add_plugin("before_tool", plugin_fn)
        p.add_gate(lambda name, args: calls.append("gate") is None or None)
        p.add_middleware(_CallRecorder("mw", calls))
        import asyncio
        asyncio.run(p.on_before_tool("x", {}))
        assert calls == ["gate", "mw", "plugin"], f"Expected gate>mw>plugin, got {calls}"


class TestHookPipelineGateBlocking:
    """Gates can block tool execution by returning False."""

    def test_gate_block_prevents_tool(self):
        p = HookPipeline()
        p.add_gate(lambda name, args: False)
        import asyncio
        result = asyncio.run(p.on_before_tool("bash", {}))
        assert result is False

    def test_gate_allow_proceeds(self):
        p = HookPipeline()
        p.add_gate(lambda name, args: None)
        import asyncio
        result = asyncio.run(p.on_before_tool("bash", {}))
        assert result is True

    def test_middleware_block_also_prevents(self):
        p = HookPipeline()
        class BlockingMW(AgentMiddleware):
            async def on_before_tool(self, name, args):
                return False
        p.add_middleware(BlockingMW())
        import asyncio
        result = asyncio.run(p.on_before_tool("bash", {}))
        assert result is False

    def test_gate_plus_middleware_gate_block_wins(self):
        """If gate blocks and middleware allows, tool is still blocked."""
        p = HookPipeline()
        p.add_gate(lambda name, args: False)
        class AllowingMW(AgentMiddleware):
            async def on_before_tool(self, name, args):
                return None
        p.add_middleware(AllowingMW())
        import asyncio
        result = asyncio.run(p.on_before_tool("bash", {}))
        assert result is False


class TestHookPipelineLifecycle:
    """All 7 lifecycle events fire in order."""

    def test_all_lifecycle_events(self):
        events = []
        p = HookPipeline()
        class Recorder(AgentMiddleware):
            async def on_before_run(self, user_input): events.append("before_run")
            async def on_after_run(self, result, error): events.append("after_run")
            async def on_before_llm(self, messages, round_num): events.append("before_llm")
            async def on_after_llm(self, tool_calls, round_num): events.append("after_llm")
            async def on_before_tool(self, name, args): events.append("before_tool")
            async def on_after_tool(self, name, result): events.append("after_tool")
            async def on_end_of_round(self, round_num): events.append("end_of_round")
        p.add_middleware(Recorder())
        import asyncio
        asyncio.run(p.on_before_run("in"))
        asyncio.run(p.on_before_llm([], 0))
        asyncio.run(p.on_after_llm([], 0))
        asyncio.run(p.on_before_tool("t", {}))
        asyncio.run(p.on_after_tool("t", "r"))
        asyncio.run(p.on_end_of_round(0))
        asyncio.run(p.on_after_run("ok", None))
        expected = ["before_run", "before_llm", "after_llm", "before_tool",
                     "after_tool", "end_of_round", "after_run"]
        assert events == expected, f"Expected {expected}, got {events}"


class TestHookPipelineTransforms:
    """on_before_llm and on_after_tool can mutate their inputs (chained)."""

    def test_on_before_llm_mutates_messages(self):
        p = HookPipeline()
        class Injector(AgentMiddleware):
            async def on_before_llm(self, messages, round_num):
                return messages + [{"role": "user", "content": "injected"}]
        p.add_middleware(Injector())
        import asyncio
        result = asyncio.run(p.on_before_llm([{"role": "system", "content": "hello"}], 1))
        assert len(result) == 2, f"Expected 2 messages, got {len(result)}"
        assert result[1]["content"] == "injected"

    def test_on_after_tool_transforms_result(self):
        p = HookPipeline()
        class Transformer(AgentMiddleware):
            async def on_after_tool(self, name, result):
                return result.upper()
        p.add_middleware(Transformer())
        import asyncio
        result = asyncio.run(p.on_after_tool("bash", "hello world"))
        assert result == "HELLO WORLD"

    def test_multiple_middlewares_chain(self):
        """Multiple middlewares should chain — each gets the previous output."""
        p = HookPipeline()
        class UpperMW(AgentMiddleware):
            async def on_after_tool(self, name, result):
                return result.upper()
        class ExclaimMW(AgentMiddleware):
            async def on_after_tool(self, name, result):
                return result + "!"
        p.add_middleware(UpperMW())
        p.add_middleware(ExclaimMW())
        import asyncio
        result = asyncio.run(p.on_after_tool("bash", "hello"))
        assert result == "HELLO!", f"Expected 'HELLO!', got '{result}'"

    def test_on_after_llm_forced_text(self):
        p = HookPipeline()
        class Forcer(AgentMiddleware):
            async def on_after_llm(self, tool_calls, round_num):
                return [], "forced text answer"
        p.add_middleware(Forcer())
        import asyncio
        calls, text = asyncio.run(p.on_after_llm([{"function": {"name": "bash"}}], 0))
        assert text == "forced text answer"
        assert calls == []


class TestHookPipelineIsolation:
    """Each pipeline owns its own registry — no cross-contamination."""

    def test_pipelines_are_isolated(self):
        p1 = HookPipeline()
        p2 = HookPipeline()
        p1.add_gate(lambda name, args: False)
        import asyncio
        result1 = asyncio.run(p1.on_before_tool("x", {}))
        result2 = asyncio.run(p2.on_before_tool("x", {}))
        assert result1 is False
        assert result2 is True

    def test_registry_supports_multiple_handlers_per_event(self):
        r = HookRegistry()
        calls = []
        async def h1(**kw): calls.append("h1")
        async def h2(**kw): calls.append("h2")
        r.register("before_tool", h1, HookType.MIDDLEWARE)
        r.register("before_tool", h2, HookType.MIDDLEWARE)
        import asyncio
        asyncio.run(r.invoke("before_tool"))
        assert calls == ["h1", "h2"]


class TestHookPipelineBackwardCompat:
    """Verify old MiddlewareChain still works (deprecated but not removed)."""

    def test_middleware_chain_still_imports(self):
        from harness.middleware.base import MiddlewareChain
        chain = MiddlewareChain()
        assert chain is not None

    def test_agent_middleware_base_still_imports(self):
        from harness.middleware import AgentMiddleware
        assert AgentMiddleware is not None

    def test_middleware_repr(self):
        """Deprecated MiddlewareChain still has basic functionality."""
        from harness.middleware.base import MiddlewareChain
        chain = MiddlewareChain()
        assert len(chain._middlewares) == 0
