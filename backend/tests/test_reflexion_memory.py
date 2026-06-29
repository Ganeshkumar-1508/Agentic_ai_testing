"""Tests for ReflexionMemory — cross-session persistence of self-critique.

Uses a temp file per test to avoid polluting the real `REFLECTIONS.jsonl`.

Storage format: JSONL (one JSON object per line, see reflexion_memory.py).
Snapshot format: markdown (for LLM system prompt injection).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.agent.reflexion_memory import (
    ReflexionMemory,
    _normalize_error,
)


# ---------------------------------------------------------------------------
# Signature + normalization
# ---------------------------------------------------------------------------


class TestSignature:
    def test_stable_for_same_error(self):
        sig1 = ReflexionMemory.signature("foo", "Error: connection refused")
        sig2 = ReflexionMemory.signature("foo", "Error: connection refused")
        assert sig1 == sig2

    def test_stable_across_volatile_parts(self):
        """Timestamps, hex ids, paths should be stripped before hashing."""
        e1 = "Error: file not found at /home/user/file.txt at 2026-06-02T10:30:00"
        e2 = "Error: file not found at /var/data/other.log at 2026-06-03T15:00:00"
        sig1 = ReflexionMemory.signature("read", e1)
        sig2 = ReflexionMemory.signature("read", e2)
        assert sig1 == sig2, f"volatile parts should not change the signature: {sig1} vs {sig2}"

    def test_differs_per_tool(self):
        sig1 = ReflexionMemory.signature("tool_a", "Error: x")
        sig2 = ReflexionMemory.signature("tool_b", "Error: x")
        assert sig1 != sig2

    def test_differs_per_failure_mode(self):
        sig1 = ReflexionMemory.signature("foo", "Error: connection refused")
        sig2 = ReflexionMemory.signature("foo", "Error: timeout")
        assert sig1 != sig2

    def test_signature_is_12_hex_chars(self):
        sig = ReflexionMemory.signature("t", "e")
        assert len(sig) == 12
        assert all(c in "0123456789abcdef" for c in sig)


class TestNormalize:
    def test_strips_timestamps(self):
        assert "<ts>" in _normalize_error("at 2026-06-02T10:30:00 it failed")
        assert "<ts>" in _normalize_error("at 2026-06-02 10:30:00 it failed")

    def test_strips_paths(self):
        assert "<path>" in _normalize_error("file /home/user/foo.txt missing")
        assert "<path>" in _normalize_error(r"file C:\Users\foo\bar.txt missing")

    def test_strips_hex_ids(self):
        assert "<hex>" in _normalize_error("session=abc123def456 failed")

    def test_strips_long_numbers(self):
        # 8+ digits that aren't all hex (no a-f) → <n>, not <hex>
        assert "<n>" in _normalize_error("offset 12345678 invalid")

    def test_strips_versions(self):
        assert "<ver>" in _normalize_error("requires 1.2.3 or later")
        assert "<ver>" in _normalize_error("requires v1.2.3 or later")

    def test_collapses_whitespace(self):
        assert _normalize_error("a   b\n\nc") == "a b c"

    def test_lowercases(self):
        assert _normalize_error("Error: PERM DENIED") == _normalize_error("error: perm denied")

    def test_empty_input(self):
        assert _normalize_error("") == ""
        assert _normalize_error("   ") == ""


# ---------------------------------------------------------------------------
# Save + lookup roundtrip
# ---------------------------------------------------------------------------


class TestSaveLookup:
    def test_save_then_lookup(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save("write", "Error: permission denied", "Check ACLs first.", True)
        result = mem.lookup("write", "Error: permission denied")
        assert result is not None
        assert "Check ACLs first" in result

    def test_lookup_miss_returns_none(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        assert mem.lookup("never_saved", "any error") is None

    def test_save_overwrites_same_signature(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save("write", "Error: perm denied", "First advice.", True)
        mem.save("write", "Error: perm denied", "Updated advice.", True)
        # Only one entry should exist (same sig → replaced, not appended)
        result = mem.lookup("write", "Error: perm denied")
        assert result is not None
        assert "Updated advice" in result
        assert "First advice" not in result
        text = (tmp_path / "REFLECTIONS.jsonl").read_text("utf-8")
        # Count non-empty lines = number of records
        records = [l for l in text.splitlines() if l.strip()]
        assert len(records) == 1

    def test_save_preserves_different_signatures(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save("write", "Error: perm denied", "ACL advice.", True)
        mem.save("read", "Error: file not found", "Path advice.", True)
        assert mem.lookup("write", "Error: perm denied") is not None
        assert mem.lookup("read", "Error: file not found") is not None
        text = (tmp_path / "REFLECTIONS.jsonl").read_text("utf-8")
        records = [l for l in text.splitlines() if l.strip()]
        assert len(records) == 2

    def test_save_unsuccessful_marked(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save("write", "Error: perm denied", "Didn't help.", False)
        text = (tmp_path / "REFLECTIONS.jsonl").read_text("utf-8")
        rec = json.loads(text.splitlines()[0])
        assert rec["success"] is False

    def test_save_normalizes_volatile_parts(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save(
            "read", "Error at /tmp/file.txt on 2026-06-02T10:30:00",
            "Stable advice.", True,
        )
        result = mem.lookup(
            "read", "Error at /etc/other.log on 2026-06-03T15:00:00",
        )
        assert result is not None
        assert "Stable advice" in result

    def test_lookup_returns_none_when_no_file(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "DOES_NOT_EXIST.jsonl")
        assert mem.lookup("any", "any") is None

    def test_creates_parent_dir(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "REFLECTIONS.jsonl"
        mem = ReflexionMemory(target)
        mem.save("t", "Error: x", "advice", True)
        assert target.exists()

    def test_writes_valid_jsonl(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save("write", "Error: x", "advice 1", True)
        mem.save("read", "Error: y", "advice 2", True)
        text = (tmp_path / "REFLECTIONS.jsonl").read_text("utf-8")
        # Every non-empty line must be a valid JSON object with the schema
        for line in text.splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            assert rec["schema_version"] == 1
            assert "sig" in rec and "tool" in rec and "text" in rec
            assert "success" in rec and "last_used" in rec
        # File should end with newline (wc -l correctness)
        assert text.endswith("\n")

    def test_skips_malformed_lines(self, tmp_path: Path):
        target = tmp_path / "REFLECTIONS.jsonl"
        # Pre-populate with garbage that should be skipped
        target.write_text(
            'not json at all\n'
            '{"sig": "valid1", "tool": "t1", "text": "ok", "success": true, "last_used": "2026-06-02T00:00:00"}\n'
            '{"this": "is missing required fields"}\n'
            '["not", "an", "object"]\n',
            encoding="utf-8",
        )
        mem = ReflexionMemory(target)
        # The valid record should still be found
        assert mem.lookup("t1", "any") is None  # different sig
        # Save a new record — should still work despite garbage
        mem.save("t1", "valid1", "new advice", True)
        result = mem.lookup("t1", "valid1")
        assert result == "new advice"


# ---------------------------------------------------------------------------
# Snapshot for system prompt (markdown format)
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_empty_when_no_file(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        assert mem.snapshot() == ""

    def test_returns_recent_entries_as_markdown(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        for i in range(5):
            mem.save(f"tool_{i}", f"Error: case {i}", f"advice for case {i}", True)
        snap = mem.snapshot(limit=3)
        # Markdown format: header + per-tool sections
        assert "## Prior Reflections" in snap
        assert "case 2" in snap
        assert "case 3" in snap
        assert "case 4" in snap
        assert "case 0" not in snap
        # Each tool gets a `### [tool_name]` header
        assert "### [tool_2]" in snap
        assert "### [tool_3]" in snap
        assert "### [tool_4]" in snap

    def test_snapshot_includes_success_marker(self, tmp_path: Path):
        mem = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        mem.save("write", "Error: x", "advice", True)
        mem.save("read", "Error: y", "advice2", False)
        snap = mem.snapshot()
        assert "success=Y" in snap
        assert "success=N" in snap


# ---------------------------------------------------------------------------
# Integration with Agent — smoke test
# ---------------------------------------------------------------------------


class TestAgentIntegration:
    def test_agent_has_reflexion_memory(self):
        from harness.agent import Agent, AgentDependencies
        from harness.events import EventBus

        deps = AgentDependencies(
            llm=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            store=None,
            permissions=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto")
        assert hasattr(agent, "_reflexion_memory")
        assert agent._reflexion_memory is not None
        assert agent._last_reflection is None
        assert agent._last_reflection_errors == []

    def test_save_reflections_noop_when_no_reflection(self, tmp_path: Path):
        from harness.agent import Agent, AgentDependencies
        from harness.events import EventBus

        deps = AgentDependencies(
            llm=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            store=None,
            permissions=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto")
        agent._reflexion_memory = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        # No _last_reflection set → save is no-op
        agent._save_reflections(was_successful=True)
        assert not (tmp_path / "REFLECTIONS.jsonl").exists()

    def test_save_reflections_writes_when_set(self, tmp_path: Path):
        from harness.agent import Agent, AgentDependencies
        from harness.events import EventBus

        deps = AgentDependencies(
            llm=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            store=None,
            permissions=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            event_bus=EventBus(),
        )
        agent = Agent(deps=deps, mode="auto")
        agent._reflexion_memory = ReflexionMemory(tmp_path / "REFLECTIONS.jsonl")
        agent._last_reflection = "Check the file path before reading."
        agent._last_reflection_errors = [("read_file", "Error: file not found")]
        agent._save_reflections(was_successful=True)
        # File should exist with the reflection
        assert (tmp_path / "REFLECTIONS.jsonl").exists()
        result = agent._reflexion_memory.lookup("read_file", "Error: file not found")
        assert result is not None
        assert "Check the file path" in result
