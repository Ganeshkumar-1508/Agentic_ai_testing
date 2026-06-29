"""Tests for the lightweight memory deepening on `memory_tool.MemoryTool`.

Pattern (per the architecture review's C5.1 follow-up + reference
research on Hermes and OpenClaude): TestAI's built-in memory is
already a Hermes Tier-1 design (two flat markdown files, char
limits, frozen snapshot at session start). The lightweight
deepening adds:

  1. Two optional metadata fields on `add` and `replace`:
       - `confidence: float` (default 1.0)
       - `source_kind: str` (default "agent_reflection"; free-form)
     When the agent passes at least one, a JSONL entry is appended
     to a sidecar log (`<TARGET>.history.jsonl`). The markdown file
     is unchanged. Detection is by key membership, not default-
     equality, so an explicit `confidence=1.0` is still a deliberate
     write.

  2. A new `history` action that reads the sidecar, with an
     optional substring filter (`text`) and a cap (`limit`,
     default 50).

Industry pattern check (see `reference/hermes-agent/agent/
memory_provider.py` and `reference/openclaude/src/memdir/`):
  - Hermes: `on_memory_write(metadata=...)` hook on the
    `MemoryProvider` ABC; the built-in is string-typed and carries
    no schema. TestAI's optional fields are the equivalent for
    the built-in.
  - Mem0: `m.add(content, metadata={...})` — free-form dict.
    TestAI exposes 2 named fields for clarity but the agent
    chooses values.
  - OpenClaude: 4-type frontmatter taxonomy
    (`user | feedback | project | reference`). TestAI's source_kind
    is free-form (no enum) per the user's "no hardcoding" rule.

These tests assert:
  - backward compatibility (no sidecar written when optional
    fields are absent)
  - optional fields round-trip through the sidecar
  - `history` returns entries with substring filter + limit
  - `remove` always audits to the sidecar (full lifecycle)
  - MEMORY and USER sidecars are independent
  - the spec/description mentions the new fields and the new action
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.testai_constants import (
    reset_testai_home_override,
    set_testai_home_override,
)
from harness.tools.memory_tool import (
    MemoryTool,
    _append_history,
    _fs as _default_fs,
    _history_path,
    _history_text_blob,
    _now_iso,
    _read_history,
    set_fs,
)
from harness.store.adapters.file_system import MemoryFileSystem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path):
    """Redirect TESTAI_HOME to a tmp_path-scoped directory and give
    the memory tool a `MemoryFileSystem` so writes go to a clean
    in-memory store instead of the real disk. Each test gets a
    fresh in-memory FS.

    Saves and restores the module-level `_fs` reference so that
    sibling tests are unaffected.
    """
    token = set_testai_home_override(tmp_path / "testai")
    fs = MemoryFileSystem()
    set_fs(fs)
    try:
        yield {"tmp_path": tmp_path, "fs": fs}
    finally:
        set_fs(_default_fs)
        reset_testai_home_override(token)


def _run(tool: MemoryTool, **kwargs):
    """Run the async MemoryTool.run synchronously.

    Uses `asyncio.run` (not `get_event_loop().run_until_complete()`)
    so each call gets a fresh event loop. After `pytest-asyncio`
    closes the main-thread loop, `get_event_loop()` raises
    `RuntimeError: There is no current event loop` instead of
    creating one — `asyncio.run` sidesteps that entirely.
    """
    import asyncio
    return asyncio.run(tool.run(**kwargs))


# ---------------------------------------------------------------------------
# Sidecar helpers
# ---------------------------------------------------------------------------


class TestSidecarHelpers:
    """Unit tests for the low-level helpers introduced with the
    lightweight deepening."""

    def test_history_path_for_memory(self):
        assert _history_path(Path("/x/MEMORY.md")) == Path("/x/MEMORY.history.jsonl")

    def test_history_path_for_user(self):
        assert _history_path(Path("/x/USER.md")) == Path("/x/USER.history.jsonl")

    def test_history_path_preserves_directory(self, isolated_home):
        p = _history_path(Path("/a/b/MEMORY.md"))
        assert p.parent == Path("/a/b")

    def test_append_then_read_roundtrip(self, isolated_home):
        fs = isolated_home["fs"]
        file_path = Path("/a/MEMORY.md")
        _append_history(file_path, {"at": _now_iso(), "action": "add", "text": "hello"})
        _append_history(file_path, {"at": _now_iso(), "action": "add", "text": "world"})
        entries = _read_history(file_path)
        assert len(entries) == 2
        assert entries[0]["text"] == "hello"
        assert entries[1]["text"] == "world"

    def test_read_history_with_no_sidecar_returns_empty(self, isolated_home):
        entries = _read_history(Path("/nonexistent/MEMORY.md"))
        assert entries == []

    def test_read_history_skips_blank_and_malformed_lines(self, isolated_home):
        fs = isolated_home["fs"]
        file_path = Path("/a/MEMORY.md")
        # Write a deliberately messy sidecar.
        good = json.dumps({"at": "2026-01-01T00:00:00Z", "action": "add", "text": "x"})
        fs.write_text(
            _history_path(file_path),
            f"{good}\n\n{good}\nNOT_JSON\n   \n{good}\n",
        )
        entries = _read_history(file_path)
        # 3 valid lines, blanks and "NOT_JSON" silently skipped.
        assert len(entries) == 3
        assert all(e["text"] == "x" for e in entries)

    def test_history_text_blob_concatenates_text_fields(self):
        blob = _history_text_blob(
            {"action": "add", "text": "t1", "confidence": 0.9, "source_kind": "sk"}
        )
        assert "t1" in blob and "sk" in blob

    def test_history_text_blob_for_replace(self):
        blob = _history_text_blob(
            {"action": "replace", "old_text": "old", "new_text": "new"}
        )
        assert "old" in blob and "new" in blob

    def test_history_text_blob_for_remove(self):
        blob = _history_text_blob({"action": "remove", "text": "deleted text"})
        assert "deleted text" in blob

    def test_history_text_blob_skips_none(self):
        blob = _history_text_blob(
            {"action": "add", "text": None, "old_text": "old", "new_text": None}
        )
        assert blob.strip() == "old"


# ---------------------------------------------------------------------------
# Optional metadata fields
# ---------------------------------------------------------------------------


class TestOptionalMetadataFields:
    """`add` and `replace` accept `confidence` and `source_kind`. When
    at least one is passed, a JSONL entry is appended to the sidecar.
    """

    def test_add_without_optional_fields_creates_no_sidecar(self, isolated_home):
        tool = MemoryTool()
        result = _run(tool, action="add", text="plain fact")
        assert result.success
        # No sidecar should exist for this (repo, target).
        sidecar = _history_path(_memory_file(isolated_home, repo="", target="memory"))
        assert not isolated_home["fs"].exists(sidecar), (
            "sidecar should NOT be created when no optional fields are passed"
        )

    def test_add_with_confidence_creates_sidecar(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="fact", confidence=0.7)
        sidecar = _history_path(_memory_file(isolated_home, repo="", target="memory"))
        assert isolated_home["fs"].exists(sidecar)
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert len(entries) == 1
        assert entries[0]["action"] == "add"
        assert entries[0]["text"] == "fact"
        assert entries[0]["confidence"] == 0.7
        assert entries[0]["source_kind"] == "agent_reflection"  # default

    def test_add_with_source_kind_creates_sidecar(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="fact", source_kind="tool_observation")
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert entries[0]["source_kind"] == "tool_observation"
        assert entries[0]["confidence"] == 1.0  # default

    def test_add_with_both_fields(self, isolated_home):
        tool = MemoryTool()
        _run(
            tool,
            action="add",
            text="fact",
            confidence=0.42,
            source_kind="user_input",
        )
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert entries[0]["confidence"] == 0.42
        assert entries[0]["source_kind"] == "user_input"

    def test_add_with_explicit_default_still_writes_sidecar(self, isolated_home):
        """Key-membership detection (not default-equality) means an
        explicit `confidence=1.0` is treated as a deliberate write."""
        tool = MemoryTool()
        _run(tool, action="add", text="x", confidence=1.0)
        sidecar = _history_path(_memory_file(isolated_home, repo="", target="memory"))
        assert isolated_home["fs"].exists(sidecar)

    def test_replace_with_metadata(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="the old fact", confidence=0.5)
        _run(
            tool,
            action="replace",
            old_text="old",
            new_text="new",
            confidence=0.95,
            source_kind="agent_reflection",
        )
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert len(entries) == 2
        assert entries[1]["action"] == "replace"
        assert entries[1]["old_text"] == "old"
        assert entries[1]["new_text"] == "new"
        assert entries[1]["confidence"] == 0.95

    def test_replace_without_metadata_writes_no_sidecar(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="abc def")
        _run(tool, action="replace", old_text="abc", new_text="xyz")
        # `add` (no metadata) + `replace` (no metadata) → 0 sidecar lines.
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert entries == []


# ---------------------------------------------------------------------------
# History action
# ---------------------------------------------------------------------------


class TestHistoryAction:
    """The new `history` action reads the sidecar."""

    def test_history_with_no_sidecar_returns_empty(self, isolated_home):
        tool = MemoryTool()
        result = _run(tool, action="history")
        assert result.success
        payload = json.loads(result.output)
        assert payload == {
            "target": "memory",
            "entries": [],
            "count": 0,
            "query": None,
            "limit": 50,
        }

    def test_history_returns_all_entries_oldest_first(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="alpha", confidence=0.9)
        _run(tool, action="add", text="beta", confidence=0.5)
        _run(tool, action="add", text="gamma", confidence=0.1)
        result = _run(tool, action="history")
        payload = json.loads(result.output)
        assert payload["count"] == 3
        assert [e["text"] for e in payload["entries"]] == ["alpha", "beta", "gamma"]

    def test_history_filters_by_text(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="python is great", confidence=0.9)
        _run(tool, action="add", text="rust is great too", confidence=0.9)
        _run(tool, action="add", text="nothing matches here", confidence=0.1)
        result = _run(tool, action="history", text="rust")
        payload = json.loads(result.output)
        assert payload["count"] == 1
        assert payload["query"] == "rust"
        assert payload["entries"][0]["text"] == "rust is great too"

    def test_history_filter_is_case_insensitive(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="Python is great", confidence=0.9)
        result = _run(tool, action="history", text="python")
        payload = json.loads(result.output)
        assert payload["count"] == 1

    def test_history_respects_limit(self, isolated_home):
        tool = MemoryTool()
        for i in range(5):
            _run(tool, action="add", text=f"fact {i}", confidence=0.5)
        result = _run(tool, action="history", limit=2)
        payload = json.loads(result.output)
        # Most recent 2.
        assert payload["count"] == 2
        assert [e["text"] for e in payload["entries"]] == ["fact 3", "fact 4"]
        assert payload["limit"] == 2

    def test_history_filter_combines_with_limit(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="python 1", confidence=0.9)
        _run(tool, action="add", text="rust 1", confidence=0.9)
        _run(tool, action="add", text="python 2", confidence=0.9)
        result = _run(tool, action="history", text="python", limit=1)
        payload = json.loads(result.output)
        # Filter to 2, then take last 1 → "python 2"
        assert payload["count"] == 1
        assert payload["entries"][0]["text"] == "python 2"

    def test_history_with_invalid_limit_falls_back_to_50(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="x", confidence=0.5)
        result = _run(tool, action="history", limit="not-a-number")
        payload = json.loads(result.output)
        assert payload["limit"] == 50
        assert payload["count"] == 1

    def test_history_action_is_in_schema_enum(self):
        tool = MemoryTool()
        spec = tool.spec()
        assert "history" in spec.input_schema["properties"]["action"]["enum"]

    def test_history_limit_param_is_in_schema(self):
        tool = MemoryTool()
        spec = tool.spec()
        assert "limit" in spec.input_schema["properties"]

    def test_history_target_switches_sidecar(self, isolated_home):
        """The history action must read the sidecar for the target
        the agent asked for, not for 'memory' by accident."""
        tool = MemoryTool()
        _run(tool, action="add", target="memory", text="m1", confidence=0.5)
        _run(tool, action="add", target="user", text="u1", confidence=0.5)

        mem_result = _run(tool, action="history", target="memory")
        user_result = _run(tool, action="history", target="user")

        assert json.loads(mem_result.output)["entries"][0]["text"] == "m1"
        assert json.loads(user_result.output)["entries"][0]["text"] == "u1"

    def test_history_unicode_round_trip(self, isolated_home):
        """Non-ASCII characters survive JSONL round-trip."""
        tool = MemoryTool()
        _run(tool, action="add", text="em-dash: — and emoji: ", confidence=0.5)
        result = _run(tool, action="history")
        payload = json.loads(result.output)
        assert payload["entries"][0]["text"] == "em-dash: — and emoji: "


# ---------------------------------------------------------------------------
# Sidecar per target / per repo
# ---------------------------------------------------------------------------


class TestSidecarPerTarget:
    """MEMORY and USER sidecars are independent. Per-repo sidecars
    are independent too."""

    def test_memory_and_user_sidecars_are_separate_files(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", target="memory", text="m1", confidence=0.5)
        _run(tool, action="add", target="user", text="u1", confidence=0.5)
        mem_side = _history_path(_memory_file(isolated_home, repo="", target="memory"))
        usr_side = _history_path(_memory_file(isolated_home, repo="", target="user"))
        assert mem_side != usr_side
        assert isolated_home["fs"].exists(mem_side)
        assert isolated_home["fs"].exists(usr_side)

    def test_per_repo_sidecars_are_separate_files(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", repo="repoA", text="a1", confidence=0.5)
        _run(tool, action="add", repo="repoB", text="b1", confidence=0.5)
        a_side = _history_path(_memory_file(isolated_home, repo="repoA", target="memory"))
        b_side = _history_path(_memory_file(isolated_home, repo="repoB", target="memory"))
        assert a_side != b_side
        a_entries = _read_history(_memory_file(isolated_home, repo="repoA", target="memory"))
        b_entries = _read_history(_memory_file(isolated_home, repo="repoB", target="memory"))
        assert [e["text"] for e in a_entries] == ["a1"]
        assert [e["text"] for e in b_entries] == ["b1"]


# ---------------------------------------------------------------------------
# Remove audits to the sidecar
# ---------------------------------------------------------------------------


class TestRemoveAudits:
    """`remove` always writes to the sidecar so the history view
    shows the full lifecycle (add → replace → remove)."""

    def test_remove_writes_sidecar_entry(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="the fact")
        _run(tool, action="remove", old_text="the fact")
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert len(entries) == 1
        assert entries[0]["action"] == "remove"
        assert entries[0]["text"] == "the fact"

    def test_remove_does_not_include_confidence_or_source_kind(self, isolated_home):
        """`remove` is a deletion, not a positive fact. Optional
        fields are not included in the sidecar entry."""
        tool = MemoryTool()
        _run(tool, action="add", text="abc")
        _run(tool, action="remove", old_text="abc")
        entries = _read_history(_memory_file(isolated_home, repo="", target="memory"))
        assert "confidence" not in entries[0]
        assert "source_kind" not in entries[0]

    def test_full_lifecycle_appears_in_history(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="v1", confidence=0.3)
        _run(
            tool,
            action="replace",
            old_text="v1",
            new_text="v2",
            confidence=0.7,
        )
        _run(tool, action="remove", old_text="v2")
        result = _run(tool, action="history")
        payload = json.loads(result.output)
        assert [e["action"] for e in payload["entries"]] == ["add", "replace", "remove"]


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """The existing `add` / `search` / `replace` / `remove` /
    `get_memory_snapshot` behavior must be unchanged when no
    optional fields are passed."""

    def test_existing_add_still_works(self, isolated_home):
        tool = MemoryTool()
        result = _run(tool, action="add", text="plain fact")
        assert result.success
        # Same tool message as before the deepening.
        assert "entry added" in result.output

    def test_existing_search_still_works(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="python")
        _run(tool, action="add", text="rust")
        result = _run(tool, action="search", text="python")
        payload = json.loads(result.output)
        assert payload["count"] == 1

    def test_existing_replace_still_works(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="abc def")
        result = _run(tool, action="replace", old_text="abc", new_text="xyz")
        assert result.success
        assert "replaced" in result.output

    def test_existing_remove_still_works(self, isolated_home):
        tool = MemoryTool()
        _run(tool, action="add", text="abc def")
        result = _run(tool, action="remove", old_text="abc")
        assert result.success
        assert "removed" in result.output

    def test_add_with_text_too_large_still_fails(self, isolated_home):
        """Char limit enforcement is unchanged."""
        tool = MemoryTool()
        # _MEMORY_LIMIT is 3000; pushing 3500 chars should fail.
        big = "x" * 3500
        result = _run(tool, action="add", text=big)
        assert not result.success
        assert result.error == "limit_exceeded"

    def test_existing_add_does_not_create_sidecar(self, isolated_home):
        """Backward compatibility: no sidecar written when no
        optional fields are passed. This is the entire point."""
        tool = MemoryTool()
        _run(tool, action="add", text="a")
        _run(tool, action="add", text="b")
        _run(tool, action="search")  # also a non-write action
        sidecar = _history_path(_memory_file(isolated_home, repo="", target="memory"))
        assert not isolated_home["fs"].exists(sidecar)


# ---------------------------------------------------------------------------
# Spec / schema
# ---------------------------------------------------------------------------


class TestSpecExposesNewFields:
    """The tool spec exposed to the LLM must mention the new
    fields and the new action, otherwise the agent will never
    know it can use them."""

    def test_spec_description_mentions_history(self):
        tool = MemoryTool()
        spec = tool.spec()
        assert "history" in spec.description

    def test_spec_description_mentions_optional_fields(self):
        tool = MemoryTool()
        spec = tool.spec()
        assert "confidence" in spec.description
        assert "source_kind" in spec.description

    def test_spec_input_schema_has_confidence(self):
        tool = MemoryTool()
        props = tool.spec().input_schema["properties"]
        assert "confidence" in props
        assert props["confidence"]["type"] == "number"

    def test_spec_input_schema_has_source_kind(self):
        tool = MemoryTool()
        props = tool.spec().input_schema["properties"]
        assert "source_kind" in props
        assert props["source_kind"]["type"] == "string"

    def test_spec_input_schema_has_limit(self):
        tool = MemoryTool()
        props = tool.spec().input_schema["properties"]
        assert "limit" in props


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _memory_file(isolated: dict, repo: str, target: str) -> Path:
    """Compute the same path the tool uses for a given (repo, target)."""
    import re
    tmp = isolated["tmp_path"] / "testai" / "memories"
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", (repo or "_global"))[:64]
    return tmp / safe / f"{target.upper()}.md"
