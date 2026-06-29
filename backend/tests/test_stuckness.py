"""Tests for the StucknessDetector module (C1).

Each plugin gets a unit test for:
  - Normal pass-through (no pattern detected)
  - Warning threshold
  - Hard-limit threshold (where applicable)
  - State reset between sessions

The InProcessAdapter is tested via its hook methods.
"""
from __future__ import annotations

import pytest

from harness.services.stuckness import (
    ConsecutiveSameToolPlugin,
    InProcessAdapter,
    MonologuePlugin,
    PingPongPlugin,
    RepeatingErrorPlugin,
    RepeatingHashPlugin,
    StucknessDetector,
    StucknessVerdict,
)


def _tc(name: str, **kwargs: str) -> list[dict]:
    """Build a single tool-call entry."""
    return [{"function": {"name": name, "arguments": kwargs or {}}}]


def _tc_multi(*names: str) -> list[dict]:
    """Build multiple tool-call entries."""
    return [{"function": {"name": n, "arguments": {}}} for n in names]


# ---------------------------------------------------------------------------
# StucknessVerdict
# ---------------------------------------------------------------------------


class TestStucknessVerdict:
    def test_default_is_ok(self) -> None:
        v = StucknessVerdict()
        assert v.pattern == "ok"
        assert v.severity == "ok"
        assert v.message == ""

    def test_frozen(self) -> None:
        v = StucknessVerdict(pattern="test", severity="hard", message="boom")
        with pytest.raises(AttributeError):
            v.pattern = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RepeatingHashPlugin
# ---------------------------------------------------------------------------


class TestRepeatingHashPlugin:
    def test_normal_passes_through(self) -> None:
        p = RepeatingHashPlugin()
        ctx: dict = {}
        v1 = p.observe(action={"tool_calls": _tc("read", path="a.py")}, progress=None, context=ctx)
        v2 = p.observe(action={"tool_calls": _tc("read", path="b.py")}, progress=None, context=ctx)
        assert v1.severity == "ok"
        assert v2.severity == "ok"

    def test_warning_at_warn_threshold(self) -> None:
        p = RepeatingHashPlugin(warn_threshold=3, hard_limit=5)
        ctx: dict = {}
        for _ in range(2):
            p.observe(action={"tool_calls": _tc("read", path="a.py")}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("read", path="a.py")}, progress=None, context=ctx)
        assert v.severity == "warning"
        assert v.pattern == "repeating_hash"

    def test_hard_at_hard_limit(self) -> None:
        p = RepeatingHashPlugin(warn_threshold=2, hard_limit=3)
        ctx: dict = {}
        for _ in range(2):
            p.observe(action={"tool_calls": _tc("read", path="a.py")}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("read", path="a.py")}, progress=None, context=ctx)
        assert v.severity == "hard"
        assert v.pattern == "repeating_hash"

    def test_tool_frequency_warning(self) -> None:
        p = RepeatingHashPlugin(tool_freq_warn=3)
        ctx: dict = {}
        for i in range(3):
            p.observe(action={"tool_calls": _tc(f"tool_{i}")}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("tool_0")}, progress=None, context=ctx)
        # tool_0 called 2 times now, not yet at threshold
        assert v.severity == "ok"

    def test_empty_tool_calls_returns_ok(self) -> None:
        p = RepeatingHashPlugin()
        v = p.observe(action={"tool_calls": []}, progress=None, context={})
        assert v.severity == "ok"


# ---------------------------------------------------------------------------
# RepeatingErrorPlugin
# ---------------------------------------------------------------------------


class TestRepeatingErrorPlugin:
    def test_normal_passes_through(self) -> None:
        p = RepeatingErrorPlugin()
        v = p.observe(
            action={"tool_name": "bash", "tool_result": "hello world"},
            progress=None, context={},
        )
        assert v.severity == "ok"

    def test_warning_at_threshold(self) -> None:
        p = RepeatingErrorPlugin(threshold=3)
        ctx: dict = {}
        for _ in range(2):
            p.observe(
                action={"tool_name": "bash", "tool_result": "Error: timeout"},
                progress=None, context=ctx,
            )
        v = p.observe(
            action={"tool_name": "bash", "tool_result": "Error: timeout"},
            progress=None, context=ctx,
        )
        assert v.severity == "warning"
        assert v.pattern == "repeating_error"
        assert "bash" in v.message

    def test_resets_on_success(self) -> None:
        p = RepeatingErrorPlugin(threshold=2)
        ctx: dict = {}
        p.observe(action={"tool_name": "bash", "tool_result": "Error: fail"}, progress=None, context=ctx)
        # Success resets
        p.observe(action={"tool_name": "bash", "tool_result": "ok"}, progress=None, context=ctx)
        v = p.observe(action={"tool_name": "bash", "tool_result": "Error: fail"}, progress=None, context=ctx)
        assert v.severity == "ok"  # counter was reset

    def test_different_tool_does_not_accumulate(self) -> None:
        p = RepeatingErrorPlugin(threshold=2)
        ctx: dict = {}
        p.observe(action={"tool_name": "bash", "tool_result": "Error: fail"}, progress=None, context=ctx)
        v = p.observe(action={"tool_name": "read", "tool_result": "Error: fail"}, progress=None, context=ctx)
        assert v.severity == "ok"  # different tool


# ---------------------------------------------------------------------------
# MonologuePlugin
# ---------------------------------------------------------------------------


class TestMonologuePlugin:
    def test_normal_passes_through(self) -> None:
        p = MonologuePlugin()
        ctx: dict = {}
        v = p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        assert v.severity == "ok"

    def test_warning_at_threshold(self) -> None:
        p = MonologuePlugin(threshold=3)
        ctx: dict = {}
        for _ in range(2):
            p.observe(action={"tool_calls": []}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": []}, progress=None, context=ctx)
        assert v.severity == "warning"
        assert v.pattern == "monologue"

    def test_resets_when_tools_appear(self) -> None:
        p = MonologuePlugin(threshold=2)
        ctx: dict = {}
        p.observe(action={"tool_calls": []}, progress=None, context=ctx)
        p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": []}, progress=None, context=ctx)
        assert v.severity == "ok"  # counter was reset


# ---------------------------------------------------------------------------
# PingPongPlugin
# ---------------------------------------------------------------------------


class TestPingPongPlugin:
    def test_normal_passes_through(self) -> None:
        p = PingPongPlugin()
        ctx: dict = {}
        for name in ("read", "bash", "grep", "write"):
            p.observe(action={"tool_calls": _tc(name)}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        assert v.severity == "ok"

    def test_warning_at_threshold(self) -> None:
        p = PingPongPlugin(threshold=6)
        ctx: dict = {}
        # read, bash, read, bash = 4 entries, threshold=6 not yet hit
        p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        # 5th still below threshold
        p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        # 6th hits threshold
        v = p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        assert v.severity == "warning"

    def test_hard_on_second_detection(self) -> None:
        p = PingPongPlugin(threshold=6)
        ctx: dict = {}
        # Three full cycles = 6 entries, hits threshold at last iteration
        for _ in range(3):
            p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        # Wait — interleave read/bash properly
        ctx2: dict = {}
        p2 = PingPongPlugin(threshold=4)
        # read, bash = 2 entries, threshold=4 not yet hit
        p2.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx2)
        p2.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx2)
        p2.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx2)
        # 4th entry hits threshold
        v1 = p2.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx2)
        assert v1.severity == "warning"
        p2.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx2)
        v2 = p2.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx2)
        assert v2.severity == "hard"


# ---------------------------------------------------------------------------
# ConsecutiveSameToolPlugin
# ---------------------------------------------------------------------------


class TestConsecutiveSameToolPlugin:
    def test_normal_passes_through(self) -> None:
        p = ConsecutiveSameToolPlugin()
        ctx: dict = {}
        v1 = p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        assert v1.severity == "ok"

    def test_different_tools_no_trigger(self) -> None:
        p = ConsecutiveSameToolPlugin(limit=3)
        ctx: dict = {}
        for name in ("read", "bash", "grep"):
            p.observe(action={"tool_calls": _tc(name)}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("write")}, progress=None, context=ctx)
        assert v.severity == "ok"

    def test_hard_at_limit(self) -> None:
        p = ConsecutiveSameToolPlugin(limit=3)
        ctx: dict = {}
        p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        assert v.severity == "hard"
        assert v.pattern == "consecutive_same_tool"
        assert "bash" in v.message

    def test_resets_on_tool_change(self) -> None:
        p = ConsecutiveSameToolPlugin(limit=3)
        ctx: dict = {}
        p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        # Different tool resets
        p.observe(action={"tool_calls": _tc("read")}, progress=None, context=ctx)
        v = p.observe(action={"tool_calls": _tc("bash")}, progress=None, context=ctx)
        assert v.severity == "ok"  # reset to 1


# ---------------------------------------------------------------------------
# StucknessDetector (integration)
# ---------------------------------------------------------------------------


class TestStucknessDetector:
    def test_detector_runs_all_plugins(self) -> None:
        d = StucknessDetector()
        v = d.observe(action={"tool_calls": _tc("bash")})
        assert v.severity == "ok"

    def test_first_plugin_wins(self) -> None:
        class _AlwaysHard:
            name = "always_hard"
            def observe(self, **kwargs) -> StucknessVerdict:
                return StucknessVerdict(pattern="always", severity="hard", message="forced")

        d = StucknessDetector(plugins=[_AlwaysHard(), MonologuePlugin()])
        v = d.observe(action={"tool_calls": []})
        assert v.pattern == "always"

    def test_detector_continues_after_plugin_exception(self) -> None:
        class _Crashy:
            name = "crashy"
            def observe(self, **kwargs) -> StucknessVerdict:
                raise RuntimeError("boom")

        p = MonologuePlugin(threshold=1)
        d = StucknessDetector(plugins=[_Crashy(), p])
        v = d.observe(action={"tool_calls": []})
        # Plugin 2 (monologue) should still fire despite crashy raising
        assert v.severity == "warning"
        assert v.pattern == "monologue"

    def test_reset_clears_state(self) -> None:
        p = ConsecutiveSameToolPlugin(limit=2)
        d = StucknessDetector(plugins=[p])
        d.observe(action={"tool_calls": _tc("bash")})
        d.reset()
        v = d.observe(action={"tool_calls": _tc("bash")})
        assert v.severity == "ok"  # counter was reset


# ---------------------------------------------------------------------------
# InProcessAdapter
# ---------------------------------------------------------------------------


class TestInProcessAdapter:
    def test_after_llm_empty_tool_calls(self) -> None:
        a = InProcessAdapter()
        v = a.observe_after_llm([])
        assert v.severity == "ok"

    def test_after_llm_triggers_consecutive(self) -> None:
        a = InProcessAdapter()
        d = a._detector
        # Replace with a tighter ConsecutiveSameToolPlugin
        d.plugins = [ConsecutiveSameToolPlugin(limit=2)]
        d.reset()
        a.observe_after_llm(_tc("bash"))
        v = a.observe_after_llm(_tc("bash"))
        assert v.severity == "hard"
        assert v.pattern == "consecutive_same_tool"

    def test_after_tool_repeating_error(self) -> None:
        a = InProcessAdapter()
        d = a._detector
        d.plugins = [RepeatingErrorPlugin(threshold=2)]
        d.reset()
        a.observe_after_tool("bash", "Error: timeout")
        v = a.observe_after_tool("bash", "Error: timeout")
        assert v.severity == "warning"
        assert v.pattern == "repeating_error"

    def test_monologue_via_after_llm_and_end_of_round(self) -> None:
        a = InProcessAdapter()
        d = a._detector
        d.plugins = [MonologuePlugin(threshold=2)]
        d.reset()
        a.observe_after_llm([])   # turn 1: no tools, counter=1
        v = a.observe_end_of_round()  # end_of_round has no tool_calls: counter=2, >=2 → warning
        assert v.severity == "warning"
        assert v.pattern == "monologue"

    def test_reset(self) -> None:
        a = InProcessAdapter()
        d = a._detector
        d.plugins = [ConsecutiveSameToolPlugin(limit=2)]
        d.reset()
        a.observe_after_llm(_tc("bash"))
        a.reset()
        v = a.observe_after_llm(_tc("bash"))
        assert v.severity == "ok"  # reset cleared the counter
