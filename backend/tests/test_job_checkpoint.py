"""Tests for the JobCheckpoint module.

JobCheckpoint stores per-spec pause state so the orchestrator
can audit what was paused, when, and by whom. The MVP keeps
checkpoints in-memory; a future sprint can persist them via
``harness.checkpoint.CheckpointManager``.

Public surface tested:
  - JobCheckpoint dataclass + to_dict()
  - save_checkpoint(spec_id, run_id, last_result, paused_by, subagent_state)
  - get_checkpoint(spec_id) -> JobCheckpoint | None
  - pop_checkpoint(spec_id) -> JobCheckpoint | None
  - list_checkpoints() -> list[JobCheckpoint]
  - clear_checkpoints()  (test-only)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from harness.services.job_checkpoint import (
    JobCheckpoint,
    clear_checkpoints,
    get_checkpoint,
    list_checkpoints,
    pop_checkpoint,
    save_checkpoint,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_checkpoints()
    yield
    clear_checkpoints()


def _make_checkpoint(**overrides):
    defaults = dict(
        spec_id="spec-1",
        run_id="run-1",
        last_result={"phase": "post_run_single"},
        paused_by="sess-1",
    )
    defaults.update(overrides)
    return save_checkpoint(**defaults)


def test_save_and_get():
    ckpt = _make_checkpoint()
    fetched = get_checkpoint("spec-1")
    assert fetched is not None
    assert fetched.spec_id == "spec-1"
    assert fetched.run_id == "run-1"
    assert fetched.last_result == {"phase": "post_run_single"}
    assert fetched.paused_by == "sess-1"


def test_save_overwrites_previous():
    _make_checkpoint(run_id="run-old")
    _make_checkpoint(run_id="run-new")
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.run_id == "run-new"


def test_paused_at_is_iso_timestamp():
    _make_checkpoint()
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    # Should parse as a valid ISO 8601 timestamp.
    parsed = datetime.fromisoformat(ckpt.paused_at)
    assert isinstance(parsed, datetime)
    # And should be recent (within 5 seconds of now).
    now = datetime.now(timezone.utc)
    delta = abs((now - parsed).total_seconds())
    assert delta < 5.0


def test_paused_by_recorded():
    _make_checkpoint(paused_by="sess-abc")
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.paused_by == "sess-abc"


def test_subagent_state_optional():
    _make_checkpoint()  # no subagent_state
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.subagent_state is None

    _make_checkpoint(subagent_state={"completed": ["sa-1"], "in_flight": []})
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.subagent_state == {"completed": ["sa-1"], "in_flight": []}


def test_last_result_is_copied():
    """Mutating the original dict after save doesn't affect the
    checkpoint (we copy on save).
    """
    result = {"phase": "post_run_single"}
    save_checkpoint(
        spec_id="spec-1", run_id="run-1",
        last_result=result, paused_by="sess-1",
    )
    result["mutated"] = True
    ckpt = get_checkpoint("spec-1")
    assert ckpt is not None
    assert "mutated" not in ckpt.last_result


def test_pop_returns_and_removes():
    _make_checkpoint()
    ckpt = pop_checkpoint("spec-1")
    assert ckpt is not None
    assert ckpt.spec_id == "spec-1"
    assert get_checkpoint("spec-1") is None


def test_pop_unknown_returns_none():
    assert pop_checkpoint("spec-never-set") is None


def test_get_unknown_returns_none():
    assert get_checkpoint("spec-never-set") is None


def test_list_checkpoints_returns_all():
    _make_checkpoint(spec_id="spec-1")
    _make_checkpoint(spec_id="spec-2")
    _make_checkpoint(spec_id="spec-3")
    all_ckpts = list_checkpoints()
    assert len(all_ckpts) == 3
    spec_ids = {c.spec_id for c in all_ckpts}
    assert spec_ids == {"spec-1", "spec-2", "spec-3"}


def test_to_dict_round_trip():
    ckpt = _make_checkpoint(
        subagent_state={"completed": ["sa-1"]},
    )
    d = ckpt.to_dict()
    assert d["spec_id"] == "spec-1"
    assert d["run_id"] == "run-1"
    assert d["last_result"] == {"phase": "post_run_single"}
    assert d["paused_by"] == "sess-1"
    assert d["subagent_state"] == {"completed": ["sa-1"]}
    assert "paused_at" in d


def test_repr_includes_key_fields():
    ckpt = _make_checkpoint()
    r = repr(ckpt)
    assert "spec-1" in r
    assert "run-1" in r


def test_clear_checkpoints_removes_all():
    _make_checkpoint(spec_id="spec-1")
    _make_checkpoint(spec_id="spec-2")
    clear_checkpoints()
    assert get_checkpoint("spec-1") is None
    assert get_checkpoint("spec-2") is None
    assert list_checkpoints() == []
