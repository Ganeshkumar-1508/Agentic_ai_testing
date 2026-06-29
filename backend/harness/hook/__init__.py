"""Unified hook pipeline — replaces MiddlewareChain, _hook_system, and hook_registry.

Three execution phases (in order):
  0  DETERMINISTIC_GATE  — JSON-file rules (allow/block/ask)
  1  MIDDLEWARE           — Ordered middleware chain (16 classes)
  2  PLUGIN               — Plugin hooks from _hook_system

Usage:
    from harness.hook.pipeline import HookPipeline

    pipeline = HookPipeline()
    pipeline.add_middleware(SomeMiddleware())
    pipeline.add_gate(hook_registry.check_pre)
    pipeline.add_plugin(plugin_handler)

    # Fire lifecycle events (Agent.run_stream calls these)
    await pipeline.on_before_run(user_input)
    await pipeline.on_before_llm(messages, round_num)
    await pipeline.on_before_tool(name, args)
"""

from harness.hook.phases import HookType

__all__ = [
    "HookType",
]
