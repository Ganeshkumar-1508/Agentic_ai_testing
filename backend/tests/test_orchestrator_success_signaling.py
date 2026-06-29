"""Tests for OrchestratorEngine._derive_run_success.

The earlier bug: when the agent's tool loop hit `max_tool_rounds`
(`backend/harness/agent/agent.py:600`), the delegate_task return was
the literal string `"Max tool rounds reached without final response."`
The previous inline check (`getattr(result, "success", True) is not
False`) defaulted to `True` for that string, so the orchestrator
reported `success=True` on runs that produced no final answer. This
file pins down the corrected detection — string-with-max-rounds is
always failure; object-with-success=False is always failure; everything
else is success.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.orchestrator import OrchestratorEngine


@pytest.mark.parametrize(
    "result,expected_success,expected_reason",
    [
        # ── The headline bug: max-rounds as a literal string ──
        (
            "Max tool rounds reached without final response.",
            False,
            "max_tool_rounds_reached",
        ),
        # ── Case-insensitive: even with weird casing, detect it ──
        (
            "MAX TOOL ROUNDS REACHED WITHOUT FINAL RESPONSE.",
            False,
            "max_tool_rounds_reached",
        ),
        # ── Object form: success=True, no max-rounds → success ──
        (
            SimpleNamespace(success=True, output="All done. PR opened at #42"),
            True,
            "ok",
        ),
        # ── Object form: success=False → failure (coordinator) ──
        (
            SimpleNamespace(success=False, output=""),
            False,
            "coordinator_failed",
        ),
        # ── Object form: success=None (not set) but no max-rounds → success ──
        (
            SimpleNamespace(output="Some free-form output"),
            True,
            "ok",
        ),
        # ── Object form: output contains max-rounds → failure (max-rounds wins) ──
        (
            SimpleNamespace(success=True, output="Hit max tool rounds. Bailing."),
            False,
            "max_tool_rounds_reached",
        ),
        # ── Edge: empty string (not a max-rounds message) → success ──
        ("", True, "ok"),
        # ── Edge: success=False wins over a benign-looking string ──
        # (delegate_task return is the object, not a string; the
        # "max tool rounds" substring in the object-form object would
        # still trigger max_tool_rounds_reached — but explicit False
        # comes first in the detector.)
        (
            SimpleNamespace(success=False, output="max tool rounds reached"),
            False,
            "coordinator_failed",
        ),
        # ── Object form: success missing entirely → success (defaults to ok) ──
        (
            SimpleNamespace(output="Just some text"),
            True,
            "ok",
        ),
    ],
)
def test_derive_run_success(result, expected_success, expected_reason):
    succeeded, reason = OrchestratorEngine._derive_run_success(result)
    assert succeeded is expected_success
    assert reason == expected_reason


def test_derive_run_success_does_not_crash_on_arbitrary_object():
    """Sanity: a bare object with no .success / .output should default to ok."""

    class BareObj:
        pass

    succeeded, reason = OrchestratorEngine._derive_run_success(BareObj())
    assert succeeded is True
    assert reason == "ok"


def test_derive_run_success_distinguishes_max_rounds_from_other_errors():
    """Regression: a string containing 'error' but not 'max tool rounds' is not
    misclassified as max_tool_rounds_reached."""

    succeeded, reason = OrchestratorEngine._derive_run_success(
        "Error: connection refused"
    )
    assert succeeded is True
    assert reason == "ok"
