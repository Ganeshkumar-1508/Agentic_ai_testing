"""Session Tracker — records skill usage with outcomes per session.

Tracks which skills were used, what happened (success/failure), duration,
and errors. Data is stored as JSONL sidecar per skill directory.

Data model per skill:
  ~/.testai/skills/<name>/.evo/sessions.jsonl
  {"session_id": "...", "timestamp": "...", "success": true, "duration_ms": 1234,
   "tool_calls": 5, "errors": [], "task_summary": "..."}
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _skills_base() -> Path:
    from harness.testai_constants import get_testai_home
    return get_testai_home() / "skills"


def _skill_meta_dir(skill_name: str) -> Path:
    return _skills_base() / skill_name / ".evo"


def _sessions_file(skill_name: str) -> Path:
    return _skill_meta_dir(skill_name) / "sessions.jsonl"


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


class SessionTracker:
    """Records skill usage with outcomes per session."""

    def __init__(self) -> None:
        self._active: dict[str, dict[str, Any]] = {}  # session_id -> {skill_name, start_time, ...}

    def start(self, session_id: str, skill_name: str) -> None:
        """Mark a skill as active for a session."""
        self._active[session_id] = {
            "skill_name": skill_name,
            "start_time": time.time(),
            "tool_calls": 0,
            "errors": [],
        }

    def record_tool_call(self, session_id: str, tool_name: str, success: bool, error: str | None = None) -> None:
        """Record a tool call within an active skill session."""
        if session_id not in self._active:
            return
        entry = self._active[session_id]
        entry["tool_calls"] = entry.get("tool_calls", 0) + 1
        if not success and error:
            entry["errors"].append({"tool": tool_name, "error": error[:200]})

    def end(self, session_id: str, success: bool, task_summary: str = "") -> None:
        """End a skill session and persist the record."""
        if session_id not in self._active:
            return
        entry = self._active.pop(session_id)
        skill_name = entry["skill_name"]
        duration_ms = int((time.time() - entry["start_time"]) * 1000)

        record = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "duration_ms": duration_ms,
            "tool_calls": entry.get("tool_calls", 0),
            "errors": entry.get("errors", []),
            "task_summary": task_summary[:500],
        }

        try:
            _append_jsonl(_sessions_file(skill_name), record)
        except Exception as e:
            logger.debug("SessionTracker.end failed for %s: %s", skill_name, e)

    def get_sessions(self, skill_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent session records for a skill."""
        return _read_jsonl(_sessions_file(skill_name))[-limit:]

    def get_stats(self, skill_name: str) -> dict[str, Any]:
        """Get aggregated stats for a skill."""
        sessions = self.get_sessions(skill_name, limit=200)
        if not sessions:
            return {"total": 0, "success_rate": 0, "avg_duration_ms": 0, "total_errors": 0}

        total = len(sessions)
        successes = sum(1 for s in sessions if s.get("success"))
        total_errors = sum(len(s.get("errors", [])) for s in sessions)
        avg_duration = sum(s.get("duration_ms", 0) for s in sessions) // max(total, 1)

        return {
            "total": total,
            "success_rate": round(successes / max(total, 1), 2),
            "avg_duration_ms": avg_duration,
            "total_errors": total_errors,
            "last_used": sessions[-1].get("timestamp") if sessions else None,
        }


# Global singleton
_tracker = SessionTracker()


def get_tracker() -> SessionTracker:
    return _tracker
