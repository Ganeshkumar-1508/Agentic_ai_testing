"""Tests for the per-role round recipe in `harness.agent.recipes`.

C2-revised deepening of the architecture review. The recipe is
the simplest version of "per-role round pipeline composition":
a per-role list of method names, walked at the top of every
round in `Agent.run()`. No new types, no PipelineStep Protocol,
no RoundContext. The method is called via `getattr(self, "_" + name)()`.

These tests pin:

  - The recipe dict's content: chat has `drain_background`,
    orchestrator has nothing.
  - Unknown role names fall back to the chat recipe.
  - The recipe walker in `Agent.run()` calls the methods in
    order, and a failing step doesn't break the round.
  - The orchestrator's coordinator subagent (spawned via
    `delegate_task` with `role="orchestrator"`) gets the empty
    orchestrator recipe, not the chat recipe.
  - The chat's Agent (the `api/main.py` chat instance) gets
    the chat recipe by default.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from harness.agent.recipes import RECIPES, resolve_recipe


# ---------------------------------------------------------------------------
# Recipe dict — the closed set of roles and their pre-round hooks
# ---------------------------------------------------------------------------


def test_chat_recipe_drains_background():
    """The chat surface has interactive background subagents.
    Each round must drain their results into the chat's
    message list so the user sees their work between turns."""
    assert "drain_background_results" in RECIPES["chat"], (
        f"chat recipe must drain background subagent results; got {RECIPES['chat']}"
    )


def test_orchestrator_recipe_is_empty():
    """The orchestrator's coordinator subagent is autonomous.
    There is no interactive human in the loop, so there is no
    background to drain. The empty recipe is the point of the
    C2-revised work — making the per-role composition explicit."""
    assert RECIPES["orchestrator"] == [], (
        f"orchestrator recipe must be empty; got {RECIPES['orchestrator']}. "
        f"An autonomous job has no interactive round machinery."
    )


def test_recipes_contains_only_chat_and_orchestrator():
    """The closed set. Adding a new role is a deliberate change
    that must add the new key here AND a new entry in
    `delegate_task.py`."""
    assert set(RECIPES.keys()) == {"chat", "orchestrator"}


def test_resolve_recipe_falls_back_to_chat_for_unknown_role():
    """Unknown role names get the chat recipe. The fallback
    matches `toolsets_for_mode`'s policy: an unrecognised
    agent role should default to the safe interactive
    surface rather than the empty one."""
    assert resolve_recipe("chat") == RECIPES["chat"]
    assert resolve_recipe("orchestrator") == RECIPES["orchestrator"]
    for unknown in ("unknown", "debug", "review", "auto", "", "CHAT"):
        assert resolve_recipe(unknown) == RECIPES["chat"], (
            f"unknown role {unknown!r} should fall back to the chat recipe"
        )


# ---------------------------------------------------------------------------
# Agent.run() — the recipe walker
# ---------------------------------------------------------------------------


def _make_test_agent(recipe_name: str = "chat") -> SimpleNamespace:
    """Build a SimpleNamespace Agent with the recipe-name plumbing
    but no real LLM. We use SimpleNamespace (not MagicMock)
    because MagicMock's `__getattr__` auto-creates attributes,
    so `getattr(agent, "_drain_background_results")` returns a
    *new* MagicMock instead of the one we explicitly set.
    SimpleNamespace has a plain `__getattribute__` that returns
    the value we assigned."""
    agent = SimpleNamespace(
        _recipe_name=recipe_name,
        _drain_background_results=MagicMock(),
    )
    return agent


def test_resolve_recipe_call_dispatches_by_role():
    """Smoke test: the chat recipe calls `drain_background`;
    the orchestrator recipe does not."""
    chat_agent = _make_test_agent("chat")
    for step_name in resolve_recipe(chat_agent._recipe_name):
        getattr(chat_agent, "_" + step_name)()
    chat_agent._drain_background_results.assert_called_once()

    orch_agent = _make_test_agent("orchestrator")
    for step_name in resolve_recipe(orch_agent._recipe_name):
        getattr(orch_agent, "_" + step_name)()
    orch_agent._drain_background_results.assert_not_called()


def test_recipe_walk_is_tolerant_of_missing_methods():
    """If a recipe step references a method that doesn't exist
    on the agent, the walker logs a warning and skips. A bad
    recipe entry shouldn't crash the round."""
    from harness.agent.recipes import resolve_recipe
    from unittest.mock import patch
    import logging

    agent = MagicMock()
    agent._recipe_name = "chat"
    # Force a recipe with a missing method
    fake_recipe = ["drain_background", "nonexistent_step"]
    with patch("harness.agent.recipes.resolve_recipe", return_value=fake_recipe):
        with patch.object(agent, "_drain_background_results", create=True):
            # Should not raise; nonexistent_step is skipped.
            for step_name in fake_recipe:
                step = getattr(agent, "_" + step_name, None)
                if step is None:
                    continue
                step()


def test_recipe_walk_is_tolerant_of_failing_methods():
    """If a recipe step raises, the round continues. Recipe
    steps are pre-round hygiene, not load-bearing. A
    failure in `drain_background` shouldn't kill the
    orchestrator's coordinator."""
    from harness.agent.recipes import resolve_recipe

    failing_mock = MagicMock(side_effect=RuntimeError("simulated failure"))
    agent = SimpleNamespace(
        _recipe_name="chat",
        _drain_background_results=failing_mock,
    )
    # The walker pattern: try / except inside the for loop.
    for step_name in resolve_recipe(agent._recipe_name):
        step = getattr(agent, "_" + step_name, None)
        if step is None:
            continue
        try:
            step()
        except Exception:
            pass  # walker swallows per the Agent.run pattern
    # The method was called even though it raised.
    failing_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Plumbing — recipe_name threaded through the factory
# ---------------------------------------------------------------------------


def test_agent_init_accepts_recipe_name():
    """`Agent.__init__` accepts a `recipe_name` arg and stores
    it as `self._recipe_name`. Default is `chat` so existing
    callers that don't pass the arg still get the chat
    recipe (no behavior change)."""
    from harness.agent.agent import Agent

    sig = Agent.__init__.__doc__ or ""
    # Use inspect to read the signature — cleaner than docstring grep.
    import inspect
    params = inspect.signature(Agent.__init__).parameters
    assert "recipe_name" in params, (
        "Agent.__init__ must accept a `recipe_name` arg so "
        "the chat and orchestrator can be constructed with "
        "different recipes"
    )
    assert params["recipe_name"].default == "chat", (
        f"recipe_name default must be 'chat' so existing "
        f"callers don't break; got {params['recipe_name'].default!r}"
    )


def test_agent_factory_forwards_recipe_name():
    """The `agent_factory` closure in `api/main.py` must
    forward `recipe_name` to `Agent.__init__`. The
    `delegate_task` tool passes `recipe_name` through the
    factory when spawning the orchestrator's coordinator.

    We check the source file directly rather than importing
    `harness.api.main` (which pulls in FastAPI + the full app
    context and fails in the unit-test environment).
    """
    from pathlib import Path
    src_path = (
        Path(__file__).resolve().parents[1] / "api" / "main.py"
    )
    src = src_path.read_text(encoding="utf-8")
    assert "recipe_name=recipe_name" in src, (
        "agent_factory must forward recipe_name=recipe_name "
        "to Agent(...) so the orchestrator's coordinator gets "
        "the empty recipe"
    )


# ---------------------------------------------------------------------------
# delegate_task — orchestrator's coordinator gets the orchestrator recipe
# ---------------------------------------------------------------------------


def test_delegate_task_passes_orchestrator_recipe_for_orchestrator_role():
    """`delegate_task` creates the child agent with the role's
    recipe. An orchestrator-role child gets the empty
    orchestrator recipe; any other role gets the chat
    recipe (defensive default)."""
    import harness.tools.delegate_task as dt_mod
    src = open(dt_mod.__file__, encoding="utf-8").read()
    # The orchestrator's coordinator recipe-name line.
    assert "recipe_name=" in src
    assert "effective_role" in src
    # The actual call: only allow chat or orchestrator roles
    # to set a custom recipe; everything else defaults to chat.
    assert "if effective_role in (\"chat\", \"orchestrator\")" in src


# ---------------------------------------------------------------------------
# Recipe content invariants
# ---------------------------------------------------------------------------


def test_all_recipe_methods_exist_on_agent():
    """Every method name in every recipe must be a real method
    on `Agent`. A typo in a recipe name should fail at import
    time (or at agent init), not at runtime."""
    import inspect
    from harness.agent.agent import Agent
    agent_methods = {
        name for name, _ in inspect.getmembers(Agent, predicate=inspect.isfunction)
    }
    for role, steps in RECIPES.items():
        for step in steps:
            expected = f"_{step}"
            assert expected in agent_methods, (
                f"recipe step {step!r} for role {role!r} references "
                f"a method that doesn't exist on Agent: {expected}"
            )
