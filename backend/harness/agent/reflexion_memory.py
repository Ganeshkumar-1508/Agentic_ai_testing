"""ReflexionMemory — cross-session persistence for self-critique patterns.

Stores `(error_signature → reflection_text)` pairs as newline-delimited
JSON (`.jsonl`) at `harness/memory_store/REFLECTIONS.jsonl`. When the
agent hits a tool error, `lookup()` returns a prior reflection (if any)
so the agent doesn't re-reflect from scratch on recurring failures.
`save()` persists a new reflection (or updates an existing one) after
the agent recovers.

Storage format (JSONL, one record per line):
    {"schema_version": 1, "sig": "abc123def456", "tool": "write",
     "text": "Check ACLs first.", "success": true, "last_used": "2026-06-02T03:00:00"}

Uses the FileSystem Protocol (file_system.py) for all disk I/O, not raw
pathlib calls. This makes it testable without touching the real filesystem.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from harness.store.adapters.file_system import FileSystem, RealFileSystem


__all__ = ["ReflexionMemory"]


logger = logging.getLogger(__name__)


_SCHEMA_VERSION = 1
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "memory_store" / "REFLECTIONS.jsonl"
_MAX_ENTRIES = 500  # cap to prevent unbounded growth
_SNAPSHOT_LIMIT = 20  # how many to include in the system prompt


# Patterns stripped before hashing so the signature is stable across runs.
# These vary per-call but don't change the underlying failure mode.
# Order matters: longer / more specific patterns first.
_NORMALIZE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\w)v?\d+\.\d+\.\d+(?:\.\d+)?\b"), "<ver>"),  # version strings (v1.2.3, 1.2.3)
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"), "<ts>"),  # timestamps (must run before N)
    (re.compile(r"\b[a-f0-9]{7,}[a-f][a-f0-9]*\b"), "<hex>"),  # hex ids/hashes (8+ hex chars, must contain a-f letter)
    (re.compile(r"\b\d{4,}\b"), "<n>"),                         # long numbers (4+ digits, non-hex)
    (re.compile(r"/[^\s]+"), "<path>"),                         # unix paths
    (re.compile(r"[A-Za-z]:\\[^\s]+"), "<path>"),               # windows paths
    (re.compile(r"\s+"), " "),                                  # collapse whitespace
)


def _normalize_error(error: str) -> str:
    """Strip volatile parts (ids, paths, timestamps) so the signature is
    stable across runs of the same underlying failure mode. Lowercases
    the result so case differences don't change the signature."""
    s = (error or "").strip()[:500]
    for pat, repl in _NORMALIZE_PATTERNS:
        s = pat.sub(repl, s)
    return s.strip().lower()


def _now_iso() -> str:
    """ISO-8601 UTC timestamp (no microseconds, no 'Z' suffix) for
    cross-tool compatibility."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class ReflexionMemory:
    """File-backed reflexion store. One instance per Agent.

    Uses FileSystem Protocol for all I/O, so tests can inject a MemoryFileSystem
    and run without touching the real disk.

    Concurrency: last-write-wins per signature. Acceptable because (a) writes
    are infrequent (end of `run()`), (b) the goal is best-effort caching, not
    a strong consistency store.
    """

    def __init__(self, path: Path | str | None = None, *, fs: FileSystem | None = None) -> None:
        self.path = Path(path) if path else _DEFAULT_PATH
        self._fs = fs or RealFileSystem()

    # ------------------------------------------------------------------
    # Signature computation
    # ------------------------------------------------------------------

    @staticmethod
    def signature(tool_name: str, error: str) -> str:
        """Stable 12-char hex hash for a (tool, error) pair."""
        normalized = _normalize_error(error)
        raw = f"{tool_name or ''}:{normalized}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]

    # ------------------------------------------------------------------
    # File I/O — JSONL primitives
    # ------------------------------------------------------------------

    def _read_records(self) -> list[dict[str, Any]]:
        """Read all valid records from the file. Skips malformed lines
        (with a debug log) so a single corrupted entry doesn't poison
        the whole store — this is one of JSONL's key resilience properties."""
        text = self._fs.read_text(self.path)
        if text is None:
            return []
        records: list[dict[str, Any]] = []
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.debug("ReflexionMemory: skipping malformed line %d: %s", lineno, exc)
                continue
            if not isinstance(rec, dict):
                logger.debug("ReflexionMemory: line %d is not a JSON object, skipping", lineno)
                continue
            if "sig" not in rec or "tool" not in rec or "text" not in rec:
                logger.debug("ReflexionMemory: line %d missing required fields, skipping", lineno)
                continue
            records.append(rec)
        return records

    def _atomic_write(self, records: list[dict[str, Any]]) -> None:
        """Write all records atomically via temp-file rename. Delegates
        to the FileSystem adapter for atomicity."""
        lines = "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records)
        if lines:
            lines += "\n"
        try:
            self._fs.atomic_write(self.path, lines)
        except OSError as exc:
            logger.debug("ReflexionMemory.write failed: %s", exc)

    # ------------------------------------------------------------------
    # Lookup — find a prior reflection for this error
    # ------------------------------------------------------------------

    def lookup(self, tool_name: str, error: str) -> str | None:
        """Return a previously-saved reflection, or None if no match."""
        sig = self.signature(tool_name, error)
        for rec in self._read_records():
            if rec.get("sig") == sig and rec.get("tool") == tool_name:
                text = rec.get("text")
                if isinstance(text, str):
                    return text
        return None

    # ------------------------------------------------------------------
    # Save — persist or update a reflection
    # ------------------------------------------------------------------

    def save(
        self,
        tool_name: str,
        error: str,
        reflection: str,
        was_successful: bool,
    ) -> None:
        """Persist a new reflection or update an existing one with the same
        signature. Updates `last_used` and refreshes the reflection text.
        """
        sig = self.signature(tool_name, error)
        ts = _now_iso()
        body = (reflection or "").strip()

        records = self._read_records()
        new_rec = {
            "schema_version": _SCHEMA_VERSION,
            "sig": sig,
            "tool": tool_name,
            "text": body,
            "success": bool(was_successful),
            "last_used": ts,
        }

        # Replace any existing record with this sig, else append
        kept = [r for r in records if r.get("sig") != sig]
        kept.append(new_rec)

        # Cap to last _MAX_ENTRIES (drop oldest)
        if len(kept) > _MAX_ENTRIES:
            kept = kept[-_MAX_ENTRIES:]

        self._atomic_write(kept)

    # ------------------------------------------------------------------
    # Snapshot — markdown-formatted for system prompt injection
    # ------------------------------------------------------------------

    def snapshot(self, limit: int = _SNAPSHOT_LIMIT) -> str:
        """Return the most-recent N reflections, formatted as markdown
        for the LLM system prompt. Empty string if no reflections saved
        yet.

        Storage is JSONL, but the prompt format is markdown (GPT-4
        scores 81.2% on markdown reasoning vs 73.9% on JSON per the
        2024 study). Storage format and prompt format are independent.
        """
        records = self._read_records()
        if not records:
            return ""
        recent = records[-limit:]
        lines = ["## Prior Reflections (avoid repeating known errors)", ""]
        for rec in recent:
            tool = rec.get("tool", "?")
            success = "Y" if rec.get("success") else "N"
            ts = rec.get("last_used", "?")
            text = rec.get("text", "").strip()
            if not text:
                continue
            lines.append(f"### [{tool}] (success={success}, last_used={ts})")
            lines.append(text)
            lines.append("")
        return "\n".join(lines).rstrip()
