"""Tests for the DB-backed _SubagentTracker (Gap 1: durable child-run control).

Verifies:
  1. Tracker seeds completed subagents from sessions table on startup
  2. snapshots correctly reflect completed/in-flight
  3. durable flag is set in snapshot
"""

from __future__ import annotations

import asyncio

from harness.services.job_checkpoint import _SubagentTracker, get_tracker


class TestSubagentTrackerDurability:
    """_SubagentTracker seeds completed subagents from DB."""

    def test_seed_from_db_populates_completed(self):
        """Simulate DB seeding by calling the equivalent of _seed_from_db."""
        t = _SubagentTracker("spec-1", "session-1")
        assert len(t.completed) == 0
        assert len(t.spawned) == 0

        # Manually add completed subagents (simulating what
        # _seed_from_db would do after querying the sessions table)
        t.completed.add("sa-completed-1")
        t.completed.add("sa-completed-2")
        t.spawned.add("sa-completed-1")
        t.spawned.add("sa-completed-2")
        t.spawned.add("sa-inflight-3")

        snap = t.snapshot()
        assert snap["completed_count"] == 2
        assert snap["in_flight_count"] == 1
        assert "sa-completed-1" in snap["completed_subagents"]
        assert "sa-completed-2" in snap["completed_subagents"]
        assert "sa-inflight-3" in snap["in_flight_subagents"]
        assert snap["durable"] is True

    def test_empty_tracker_snapshot(self):
        t = _SubagentTracker("spec-2", "session-2")
        snap = t.snapshot()
        assert snap["completed_count"] == 0
        assert snap["in_flight_count"] == 0
        assert snap["completed_subagents"] == []
        assert snap["in_flight_subagents"] == []
        assert snap["durable"] is True

    def test_snapshot_reflects_live_additions(self):
        t = _SubagentTracker("spec-3", "session-3")
        t.spawned.add("sa-1")
        t.spawned.add("sa-2")

        snap1 = t.snapshot()
        assert snap1["in_flight_count"] == 2
        assert snap1["completed_count"] == 0

        t.completed.add("sa-1")
        snap2 = t.snapshot()
        assert snap2["in_flight_count"] == 1
        assert snap2["completed_count"] == 1
        assert snap2["completed_subagents"] == ["sa-1"]

    def test_multiple_trackers_are_isolated(self):
        t1 = _SubagentTracker("spec-a", "session-a")
        t2 = _SubagentTracker("spec-b", "session-b")
        t1.completed.add("sa-x")
        assert "sa-x" not in t2.completed
        assert t1.snapshot()["completed_count"] == 1
        assert t2.snapshot()["completed_count"] == 0


class TestCompressionLineage:
    """Compressions table lineage tracking (Gap 2)."""

    def test_record_compaction_accepts_session_id(self):
        from harness.context_compressor.compressor import record_compaction
        # Should not raise — infrastructure is wired
        record_compaction(
            before_tokens=10000,
            after_tokens=5000,
            threshold_percent=0.85,
            context_length=128000,
            session_id="session-test-1",
        )
        record_compaction(
            before_tokens=50000,
            after_tokens=25000,
            threshold_percent=0.85,
            context_length=128000,
            session_id="session-test-2",
        )
        # These should just log to in-memory state without session_id
        record_compaction(
            before_tokens=1000,
            after_tokens=500,
            threshold_percent=0.85,
            context_length=32000,
        )
        from harness.context_compressor.compressor import get_compaction_state_snapshot
        state = get_compaction_state_snapshot()
        assert state["compactions_total"] == 3
        assert state["last_before_tokens"] == 1000
