"""Persistent memory tool — cross-run knowledge for agents.

Agents save/recall facts across sessions using a flat file per repo.
Injected into coordinator's context at session start (frozen snapshot).

Design follows the Hermes Tier-1 pattern (see
`reference/hermes-agent/tools/memory_tool.py`): two flat markdown files
(`MEMORY.md`, `USER.md`) with char limits, a single `memory` tool, and
auto-injection at session start. Per the user's "no hardcoding" rule
the entry shape is free-form; the agent decides what to write.

Lightweight metadata: `add` and `replace` accept two optional fields
(`confidence: float`, `source_kind: str`) that, when present, are
written to a sidecar JSONL log (`<TARGET>.history.jsonl`) alongside
the markdown file. A new `history` action reads that sidecar. The
markdown file itself is unchanged — the sidecar is opt-in and lazy.

Industry reference:
  - Hermes: `on_memory_write(metadata=...)` hook on the
    MemoryProvider ABC; the built-in `MemoryStore` is string-typed
    with no schema, and external providers carry optional fields.
  - Mem0: `m.add(content, metadata={...})` — free-form metadata dict.
  - OpenClaude: 4-type frontmatter taxonomy (`user | feedback |
    project | reference`) — not used here because TestAI's
    markdown entries are too small for frontmatter; the JSONL
    sidecar is the equivalent.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.store.adapters.file_system import FileSystem, RealFileSystem
from harness.tools.base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)
from harness.tools.registry import registry

_MEMORY_LIMIT = 3000
_USER_LIMIT = 1375

_fs: FileSystem = RealFileSystem()


def set_fs(fs: FileSystem) -> None:
    """Override the filesystem adapter (for tests)."""
    global _fs
    _fs = fs


def _memories_dir() -> Path:
    from harness.testai_constants import get_testai_home
    return get_testai_home() / "memories"


def _repo_file(repo: str, target: str) -> Path:
    """Get the memory file path for a given repo and target.

    Pattern: ~/.testai/memories/<repo-slug>/MEMORY.md
    or       ~/.testai/memories/_global/MEMORY.md when no repo specified.
    """
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", (repo or "_global"))[:64]
    return _memories_dir() / safe / f"{target.upper()}.md"


def _history_path(file_path: Path) -> Path:
    """Return the JSONL sidecar log path for a memory file.

    `MEMORY.md` -> `MEMORY.history.jsonl`
    `USER.md`   -> `USER.history.jsonl`

    The sidecar is opt-in: created lazily on the first `add` /
    `replace` / `remove` that has metadata. `Path.with_suffix`
    replaces only the LAST suffix, so `with_suffix(".history.jsonl")`
    on `MEMORY.md` correctly yields `MEMORY.history.jsonl`.
    """
    return file_path.with_suffix(".history.jsonl")


def _append_history(file_path: Path, entry: dict[str, Any]) -> None:
    """Append a JSONL entry to the sidecar. Creates the file if missing.

    Uses `_fs.append_text` (atomic append in both RealFileSystem and
    MemoryFileSystem adapters).
    """
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    _fs.append_text(_history_path(file_path), line)


def _read_history(file_path: Path) -> list[dict[str, Any]]:
    """Read all JSONL entries from the sidecar, oldest first.

    Skips blank lines. Returns an empty list if the sidecar does not
    exist (graceful degradation — the sidecar is opt-in).
    """
    text = _fs.read_text(_history_path(file_path))
    if not text:
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # Best-effort: skip malformed lines rather than raise,
            # so a partially-written sidecar does not break reads.
            continue
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _history_text_blob(entry: dict[str, Any]) -> str:
    """Return a single searchable string for a sidecar entry.

    Concatenates the text-bearing fields of the entry so the
    `history` action's substring filter matches regardless of
    whether the action was `add`/`replace` (with `text` or
    `old_text`/`new_text`) or `remove` (with `text`). Non-string
    fields are skipped via `str()` coercion.
    """
    parts: list[str] = []
    for key in ("text", "old_text", "new_text", "source_kind"):
        v = entry.get(key)
        if v is None:
            continue
        parts.append(str(v))
    return " ".join(parts)


def _read_file(path: Path) -> str:
    text = _fs.read_text(path)
    if text is not None:
        return text
    return ""


def _write_file(path: Path, content: str, limit: int) -> None:
    if len(content) > limit:
        content = content[: limit - 50] + "\n\n[truncated]"
    _fs.write_text(path, content)


def get_memory_snapshot(repo: str = "") -> str:
    """Return formatted memory block for injection into coordinator context.

    Loads both MEMORY.md and USER.md for the given repo.
    Returns empty string if no memory exists.
    """
    mem = _read_file(_repo_file(repo, "memory"))
    user = _read_file(_repo_file(repo, "user"))
    parts = []
    if mem:
        chars = len(mem)
        pct = round(chars / _MEMORY_LIMIT * 100)
        parts.append(f"MEMORY (agent notes) [{pct}% — {chars}/{_MEMORY_LIMIT} chars]\n{mem}")
    if user:
        chars = len(user)
        pct = round(chars / _USER_LIMIT * 100)
        parts.append(f"USER (preferences) [{pct}% — {chars}/{_USER_LIMIT} chars]\n{user}")
    return "\n\n".join(parts)


async def add_memory(repo: str, content: str, *, target: str = "memory", metadata: dict | None = None) -> bool:
    """Convenience function to add a memory entry. Used by run_summary and l2_reflection.

    Returns True on success, False on failure.
    """
    if not content or not content.strip():
        return False
    try:
        char_limit = _MEMORY_LIMIT if target == "memory" else _USER_LIMIT
        file_path = _repo_file(repo, target)
        current = _read_file(file_path)
        separator = "\n\n" if current else ""
        if len(current) + len(content) + 2 > char_limit:
            logger.warning("add_memory: %s at %d/%d chars, skipping", target, len(current), char_limit)
            return False
        _write_file(file_path, current + separator + content, char_limit)
        if metadata:
            _append_history(file_path, {
                "at": _now_iso(),
                "action": "add",
                "text": content[:500],
                "source_kind": metadata.get("source_kind", "auto"),
            })
        return True
    except Exception as e:
        logger.debug("add_memory failed: %s", e)
        return False


class MemoryTool(BaseTool):
    default_level = "allow"
    name = "memory"
    description = (
        "Manage persistent memory that survives across sessions. "
        "Target 'memory' for project notes (build commands, conventions, gotchas), "
        "'user' for user preferences. "
        "Actions: add (append entry), replace (update entry), remove (delete entry), "
        "search (find entries matching text), history (read the per-entry sidecar log of past writes). "
        "Optional fields for add/replace: confidence (0.0-1.0, your confidence in this fact) "
        "and source_kind (free-form string, e.g. 'tool_observation', 'user_input', "
        "'agent_reflection' — you choose the vocabulary). When passed, they are written to a "
        "JSONL sidecar log; the markdown file is unchanged. "
        "Memory is automatically loaded at the start of every session."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "replace", "remove", "search", "history"],
                        "description": (
                            "add: append entry. replace: find old_text and replace. "
                            "remove: delete matching entry. search: find entries matching text. "
                            "history: read the sidecar log of past add/replace/remove events."
                        ),
                    },
                    "target": {
                        "type": "string",
                        "enum": ["memory", "user"],
                        "description": "memory: project notes, conventions, gotchas. user: user preferences (default: memory)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Content to add (for add), or substring to search/filter on (for search/history).",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Substring to identify entry for replace/remove",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text (for replace action)",
                    },
                    "confidence": {
                        "type": "number",
                        "description": (
                            "Optional. Your confidence in this fact, 0.0-1.0. "
                            "Default 1.0. Only meaningful for add/replace."
                        ),
                    },
                    "source_kind": {
                        "type": "string",
                        "description": (
                            "Optional. Free-form string naming how this fact was learned. "
                            "Default 'agent_reflection'. Only meaningful for add/replace."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return (for history action). Default 50.",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repo scope. Omit or empty for global memory shared across all repos.",
                    },
                },
                "required": ["action"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        target = kwargs.get("target", "memory")
        text = kwargs.get("text", "")
        old_text = kwargs.get("old_text", "")
        new_text = kwargs.get("new_text", "")
        repo = kwargs.get("repo", "")
        history_limit = kwargs.get("limit", 50)

        # Optional metadata — sidecar is written only when the agent
        # explicitly passes at least one of these. Detection by key
        # membership (not default-equality) so `confidence=1.0` is
        # still a deliberate write.
        confidence_provided = "confidence" in kwargs
        source_kind_provided = "source_kind" in kwargs
        confidence = float(kwargs.get("confidence", 1.0))
        source_kind = kwargs.get("source_kind", "agent_reflection")
        metadata_supplied = confidence_provided or source_kind_provided

        char_limit = _MEMORY_LIMIT if target == "memory" else _USER_LIMIT
        file_path = _repo_file(repo, target)
        current = _read_file(file_path)

        if action == "add":
            if not text:
                return ToolResult(success=False, output="text required for add", error="missing_text")
            if len(current) + len(text) + 2 > char_limit:
                return ToolResult(
                    success=False,
                    output=f"{target} at {len(current)}/{char_limit} chars. Replace or remove entries first.",
                    error="limit_exceeded",
                )
            separator = "\n\n" if current else ""
            _write_file(file_path, current + separator + text, char_limit)
            if metadata_supplied:
                _append_history(file_path, {
                    "at": _now_iso(),
                    "action": "add",
                    "text": text,
                    "confidence": confidence,
                    "source_kind": source_kind,
                })
            return ToolResult(success=True, output=f"{target} entry added ({len(text)} chars)")

        elif action == "replace":
            if not old_text or not new_text:
                return ToolResult(success=False, output="old_text and new_text required", error="missing_params")
            if old_text not in current:
                return ToolResult(success=False, output=f"old_text not found in {target}", error="not_found")
            updated = current.replace(old_text, new_text)
            _write_file(file_path, updated, char_limit)
            if metadata_supplied:
                _append_history(file_path, {
                    "at": _now_iso(),
                    "action": "replace",
                    "old_text": old_text,
                    "new_text": new_text,
                    "confidence": confidence,
                    "source_kind": source_kind,
                })
            return ToolResult(success=True, output=f"{target} entry replaced")

        elif action == "remove":
            if not old_text:
                return ToolResult(success=False, output="old_text required for remove", error="missing_text")
            if old_text not in current:
                return ToolResult(success=False, output=f"old_text not found in {target}", error="not_found")
            updated = current.replace(old_text, "").strip()
            while "\n\n\n" in updated:
                updated = updated.replace("\n\n\n", "\n\n")
            _write_file(file_path, updated, char_limit)
            # `remove` always audits to the sidecar (even without
            # optional fields) so the history view shows the full
            # lifecycle. The agent may still pass confidence /
            # source_kind to annotate the deletion.
            _append_history(file_path, {
                "at": _now_iso(),
                "action": "remove",
                "text": old_text,
            })
            return ToolResult(success=True, output=f"{target} entry removed")

        elif action == "search":
            if not text:
                # Return full listing
                entries = [e.strip() for e in current.split("\n\n") if e.strip()]
                return ToolResult(
                    success=True,
                    output=json.dumps({"target": target, "entries": entries, "count": len(entries)}, indent=2),
                )
            # Case-insensitive search across entries
            q = text.lower()
            entries = [e.strip() for e in current.split("\n\n") if e.strip() and q in e.lower()]
            return ToolResult(
                success=True,
                output=json.dumps({"target": target, "query": text, "entries": entries, "count": len(entries)}, indent=2),
            )

        elif action == "history":
            entries = _read_history(file_path)
            if text:
                q = text.lower()
                entries = [e for e in entries if q in _history_text_blob(e).lower()]
            try:
                cap = int(history_limit)
            except (TypeError, ValueError):
                cap = 50
            if cap < 0:
                cap = 0
            if len(entries) > cap:
                entries = entries[-cap:]
            return ToolResult(
                success=True,
                output=json.dumps(
                    {
                        "target": target,
                        "entries": entries,
                        "count": len(entries),
                        "query": text or None,
                        "limit": cap,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        return ToolResult(success=False, output=f"Unknown action: {action}", error="bad_action")


registry.register(MemoryTool(), toolset="read")
