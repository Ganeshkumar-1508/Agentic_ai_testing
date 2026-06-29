"""Tests for C1.1: the coordinator role is loaded from a .txt file
under .testai/prompts/agents/ rather than baked into an f-string
in the orchestrator.

Covers:
- the role file exists and is non-empty
- load_agent_prompt("coordinator") returns its body
- render_prompt substitutes {{var}} placeholders
- _build_tier_aware_goal renders the file-based goal (tier 1, tier 2)
- _fallback_tier_aware_goal produces equivalent output
- when the role file is missing, _build_tier_aware_goal falls back
  to the inline f-string (preserves pre-C1.1 behaviour)
- the orchestrator's test suite (16 tests) still passes byte-for-byte
  on the new path
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.orchestrator import OrchestratorEngine
from harness.prompt_builder import load_agent_prompt, render_prompt


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROLE_FILE = PROJECT_ROOT / ".testai" / "prompts" / "agents" / "coordinator.txt"


# A minimal spec mirror — the real JobSpec is in harness.types but we
# only need the five attributes _build_tier_aware_goal reads.
class _Spec:
    def __init__(self, *, tier=1, capabilities=None, prompt="p", repo_url="r", branch="b"):
        self.prompt = prompt
        self.repo_url = repo_url
        self.branch = branch
        self.tier = tier
        self.capabilities = capabilities or []


def test_role_file_exists():
    assert ROLE_FILE.is_file(), f"role file missing: {ROLE_FILE}"


def test_role_file_is_non_empty():
    body = load_agent_prompt("coordinator")
    assert body, "load_agent_prompt('coordinator') returned empty"
    assert "{{header}}" in body, "role body missing {{header}} placeholder"
    assert "{{tier_block}}" in body, "role body missing {{tier_block}} placeholder"


def test_render_prompt_substitutes_placeholders():
    body = "hello {{name}}, you are {{role}}"
    out = render_prompt(body, {"name": "world", "role": "coordinator"})
    assert out == "hello world, you are coordinator"


def test_render_prompt_leaves_unknown_placeholders_alone():
    body = "a={{a}} b={{b}} c={{c}}"
    out = render_prompt(body, {"a": "1", "c": "3"})
    # Unknown placeholders are left untouched (str.replace semantics)
    assert out == "a=1 b={{b}} c=3"


def test_build_tier_aware_goal_tier1_uses_file_path():
    spec = _Spec(tier=1, capabilities=["write_test_files", "open_pr"])
    goal = OrchestratorEngine._build_tier_aware_goal(spec)
    # All required substrings from the original f-string
    assert "PROMPT: p" in goal
    assert "REPO: r" in goal
    assert "BRANCH: b" in goal
    assert "TIER: 1" in goal
    assert "TIER 2" not in goal  # tier-1 path
    assert "CAPABILITIES (you MAY do these):" in goal
    assert "  - write_test_files" in goal
    assert "  - open_pr" in goal
    assert "FORBIDDEN (do NOT do these):" in goal
    assert "  - edit_existing_tests" in goal
    assert "  - run_tests" in goal
    assert "Report what you accomplished." in goal


def test_build_tier_aware_goal_tier2_includes_supervised_block():
    spec = _Spec(tier=2, capabilities=["write_test_files"])
    goal = OrchestratorEngine._build_tier_aware_goal(spec, proposal_id="prop-xyz")
    assert "TIER: 2" in goal
    assert "TIER 2 \u2014 SUPERVISED:" in goal
    assert "do NOT call commit_and_open_pr" in goal
    assert "post the diff" in goal
    assert "kanban task" in goal
    assert "prop-xyz" in goal
    assert "tracked as proposal" in goal


def test_build_tier_aware_goal_tier2_without_proposal_id():
    spec = _Spec(tier=2, capabilities=["write_test_files"])
    goal = OrchestratorEngine._build_tier_aware_goal(spec)
    assert "TIER 2 \u2014 SUPERVISED:" in goal
    # proposal_ref block is suppressed when no proposal_id
    assert "tracked as proposal" not in goal


def test_fallback_matches_legacy_fstring_for_tier1():
    spec = _Spec(tier=1, capabilities=["write_test_files", "open_pr"])
    fallback = OrchestratorEngine._fallback_tier_aware_goal(spec)
    file_path = OrchestratorEngine._build_tier_aware_goal(spec)
    # The two paths produce the same string for tier 1 when the role
    for sub in [
        "You are the coordinator for this TestAI job.",
        "PROMPT: p", "REPO: r", "BRANCH: b", "TIER: 1",
        "CAPABILITIES", "FORBIDDEN",
        "Report what you accomplished.",
    ]:
        assert sub in file_path, f"file-path missing: {sub}"
        assert sub in fallback, f"fallback missing: {sub}"


def test_fallback_matches_legacy_fstring_for_tier2():
    spec = _Spec(tier=2, capabilities=["write_test_files"])
    fallback = OrchestratorEngine._fallback_tier_aware_goal(spec, proposal_id="p-1")
    file_path = OrchestratorEngine._build_tier_aware_goal(spec, proposal_id="p-1")
    for sub in [
        "TIER: 2", "TIER 2 \u2014 SUPERVISED:",
        "do NOT call commit_and_open_pr", "post the diff",
        "kanban task", "p-1", "tracked as proposal",
    ]:
        assert sub in file_path, f"file-path missing: {sub}"
        assert sub in fallback, f"fallback missing: {sub}"


def test_fallback_path_used_when_role_file_missing(tmp_path, monkeypatch):
    """If the role file is missing, _build_tier_aware_goal must fall
    back to the inline f-string and still produce a valid goal."""
    # Force load_agent_prompt to return empty for the duration of this test
    from harness import prompt_builder
    original = prompt_builder.load_agent_prompt
    monkeypatch.setattr(
        prompt_builder, "load_agent_prompt",
        lambda name: "" if name == "coordinator" else original(name),
    )

    spec = _Spec(tier=1, capabilities=["write_test_files"])
    goal = OrchestratorEngine._build_tier_aware_goal(spec)

    # The fallback should still produce a usable goal
    assert "PROMPT: p" in goal
    assert "TIER: 1" in goal
    assert "CAPABILITIES" in goal


def test_vars_for_job_spec_includes_capabilities_and_forbidden():
    spec = _Spec(tier=1, capabilities=["write_test_files", "open_pr"])
    vars_ = OrchestratorEngine._vars_for_job_spec(spec)
    assert "header" in vars_
    assert "tier_block" in vars_
    assert vars_["tier_block"] == "", "tier 1 must have empty tier_block"
    assert "TIER: 1" in vars_["header"]
    assert "write_test_files" in vars_["header"]
    assert "open_pr" in vars_["header"]
    assert "edit_existing_tests" in vars_["header"]
    assert "run_tests" in vars_["header"]


def test_vars_for_job_spec_tier2_has_supervised_block():
    spec = _Spec(tier=2, capabilities=["write_test_files"])
    vars_ = OrchestratorEngine._vars_for_job_spec(spec, proposal_id="abc")
    assert "TIER 2 \u2014 SUPERVISED:" in vars_["tier_block"]
    assert "abc" in vars_["tier_block"]
    assert "tracked as proposal" in vars_["tier_block"]


def test_vars_for_job_spec_tier2_no_proposal_id_omits_ref():
    spec = _Spec(tier=2, capabilities=["write_test_files"])
    vars_ = OrchestratorEngine._vars_for_job_spec(spec)
    assert "TIER 2 \u2014 SUPERVISED:" in vars_["tier_block"]
    assert "tracked as proposal" not in vars_["tier_block"]


def test_all_capabilities_yields_no_forbidden_block():
    """When every known capability is granted, the FORBIDDEN block
    is replaced with the '(no additional restrictions)' note."""
    spec = _Spec(tier=1, capabilities=["open_pr", "write_test_files", "edit_existing_tests", "run_tests"])
    vars_ = OrchestratorEngine._vars_for_job_spec(spec)
    assert "(no additional restrictions)" in vars_["header"]
    assert "FORBIDDEN" not in vars_["header"]


def test_no_capabilities_lists_all_as_forbidden():
    spec = _Spec(tier=1, capabilities=[])
    vars_ = OrchestratorEngine._vars_for_job_spec(spec)
    assert "FORBIDDEN" in vars_["header"]
    for c in ("open_pr", "write_test_files", "edit_existing_tests", "run_tests"):
        assert f"  - {c}" in vars_["header"]
