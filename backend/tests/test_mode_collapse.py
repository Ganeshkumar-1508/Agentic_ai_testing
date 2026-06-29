"""Tests for the collapsed chat-surface mode surface.

TestAI collapsed from 9 modes (chat/auto/ask/architect/debug/plan/
explore/batch/review/custom) to a single chat surface. The agent
infers intent from the message. The job-runner surface doesn't
go through `MODES` at all — it has a fixed toolset wired into
the orchestrator.

These tests pin the new contract:

  - `MODES` only contains `chat`.
  - `toolsets_for_mode("chat")` returns the chat toolset.
  - `toolsets_for_mode(<anything else>)` falls back to the chat
    toolset rather than raising or returning the historical
    full toolset.
  - `prompt_for_mode` and `system_prompts_for_mode` behave the
    same way: `chat` is the only "real" mode; anything else
    falls back to chat.
  - The `orchestrator` toolset (which the orchestrator wires
    into the coordinator subagent) still resolves cleanly
    alongside the chat toolset.
"""
from __future__ import annotations

import pytest

from harness.tools.toolsets import (
    CHAT_READONLY_TOOLSET, MODES,
    prompt_for_mode, system_prompts_for_mode, toolsets_for_mode,
)


# ---------------------------------------------------------------------------
# MODES surface — the only mode that exists now is `chat`
# ---------------------------------------------------------------------------


def test_modes_contains_only_chat():
    assert set(MODES.keys()) == {"chat"}, (
        f"MODES should only contain `chat`; the 8 non-chat modes "
        f"were collapsed. Found: {sorted(MODES.keys())}"
    )


def test_chat_mode_has_expected_shape():
    cfg = MODES["chat"]
    assert "description" in cfg and cfg["description"]
    assert cfg["toolsets"] == ["chat"]
    assert "prompt" in cfg and cfg["prompt"]
    assert cfg["system_prompts"] == ["chat-role"]


# ---------------------------------------------------------------------------
# toolsets_for_mode — chat is the only real mode; everything else falls back
# ---------------------------------------------------------------------------


def test_toolsets_for_chat_returns_chat_toolset():
    tools = toolsets_for_mode("chat")
    # Every tool in the explicit chat list must be present.
    assert set(tools) >= set(CHAT_READONLY_TOOLSET), (
        f"chat mode must include the explicit CHAT_READONLY_TOOLSET; "
        f"missing: {set(CHAT_READONLY_TOOLSET) - set(tools)}"
    )


@pytest.mark.parametrize("legacy_mode", [
    "auto", "ask", "architect", "debug", "plan",
    "explore", "batch", "review", "custom",
    "", "unknown", "AUTO", "Chat",
])
def test_unknown_or_legacy_modes_fall_back_to_chat(legacy_mode):
    """Legacy mode names (and any unknown value) must not crash.

    The chat UI may still pass old values from cached tabs. The
    fallback is the chat toolset, not an empty list and not the
    old full-pipeline toolset.
    """
    tools = toolsets_for_mode(legacy_mode)
    chat_tools = set(toolsets_for_mode("chat"))
    assert set(tools) == chat_tools, (
        f"mode={legacy_mode!r} should fall back to the chat toolset"
    )


# ---------------------------------------------------------------------------
# prompt_for_mode — chat is the only real prompt; everything else falls back
# ---------------------------------------------------------------------------


def test_prompt_for_chat_returns_chat_prompt():
    assert prompt_for_mode("chat") == MODES["chat"]["prompt"]


@pytest.mark.parametrize("legacy_mode", ["auto", "ask", "debug", "plan", "", "unknown"])
def test_prompt_for_unknown_mode_falls_back_to_chat(legacy_mode):
    assert prompt_for_mode(legacy_mode) == MODES["chat"]["prompt"]


# ---------------------------------------------------------------------------
# system_prompts_for_mode — same fallback contract
# ---------------------------------------------------------------------------


def test_system_prompts_for_chat_returns_chat_role():
    assert system_prompts_for_mode("chat") == ["chat-role"]


@pytest.mark.parametrize("legacy_mode", ["auto", "ask", "debug", "plan", "", "unknown"])
def test_system_prompts_for_unknown_mode_returns_empty(legacy_mode):
    """Unknown modes get no extra system prompts.

    The chat Role's identity (its `prompt`) is sufficient on its
    own; the orchestrator surface injects its own prompts via the
    goal string, not through this function.
    """
    assert system_prompts_for_mode(legacy_mode) == []


# ---------------------------------------------------------------------------
# The orchestrator's coordinator toolset still resolves
# ---------------------------------------------------------------------------


def test_orchestrator_toolset_resolves_independently():
    """The orchestrator wires the coordinator subagent with
    `toolsets=["orchestrator"]`. This is not a chat mode — it's
    the job-runner surface. Resolving it should not accidentally
    fall back to the chat toolset or vice versa."""
    from harness.tools.toolsets import TOOLSETS, resolve_toolsets

    assert "orchestrator" in TOOLSETS
    resolved = set(resolve_toolsets(["orchestrator"]))
    # The orchestrator toolset includes things the chat toolset does NOT
    # (e.g. bash, write_file, orchestrate, commit_and_open_pr).
    assert "bash" in resolved
    assert "orchestrate" in resolved
    assert "commit_and_open_pr" in resolved
    # And it does NOT include the chat-only tools.
    assert "submit_job" not in resolved, (
        "submit_job is a chat-only tool; the orchestrator's "
        "coordinator should not be able to call it (that would "
        "let a job spawn another job)."
    )
    assert "list_runs" not in resolved, (
        "list_runs is a chat-only introspection tool."
    )


def test_orchestrator_and_chat_toolsets_are_disjoint():
    """The two surfaces must not share mutation tools.

    This is the C1-revised invariant from the architecture review:
    role-gating means the chat surface cannot reach the
    job-runner surface's tools and vice versa.
    """
    from harness.tools.toolsets import resolve_toolsets

    chat_tools = set(resolve_toolsets(["chat"]))
    orch_tools = set(resolve_toolsets(["orchestrator"]))
    overlap = chat_tools & orch_tools
    # The only acceptable shared tools are passive read-only ones
    # (skills_list, skill_view, question). No mutations.
    allowed_overlap = {"skills_list", "skill_view", "question"}
    unexpected = overlap - allowed_overlap
    assert not unexpected, (
        f"chat and orchestrator toolsets share non-trivial tools: "
        f"{sorted(unexpected)}. Role-gating requires no mutation "
        f"tools to cross surfaces."
    )
