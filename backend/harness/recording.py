"""JSONL session recording — captures every LLM interaction and tool execution.

Each session produces a JSONL file at:
  ~/.testai/sessions/{session_id}/trajectory.jsonl

Failed sessions go to .../trajectory_failed.jsonl
Completed sessions go to .../trajectory_samples.jsonl

Format: one JSON object per line, each with a 'type' field.

The API router (`api/routers/recordings.py`) reads back the same path via
the :data:`SESSION_LOG_DIR` constant. Older callers wrote to
``/app/data/sessions/{session_id}.jsonl``; that env var is still
honored for back-compat reads.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RECORDING_DIR = Path.home() / ".testai" / "sessions"
MAX_RESULT_CHARS = 2000  # Truncate tool results to keep files manageable

# Back-compat: older code and the API router look up recordings here.
# Honors ``SESSION_LOG_DIR`` for ops who run a shared volume; otherwise
# falls back to the canonical per-user ~/.testai path.
SESSION_LOG_DIR = Path(
    os.environ.get("SESSION_LOG_DIR") or str(RECORDING_DIR)
)


def _ensure_dir(session_id: str) -> Path:
    """Create and return the recording directory for a session."""
    path = RECORDING_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_entry(session_id: str, entry: dict[str, Any]):
    """Append one JSON line to the session's trajectory file."""
    try:
        path = _ensure_dir(session_id) / "trajectory.jsonl"
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning("Failed to write trajectory entry: %s", e)


class SessionRecorder:
    """Records a single agent session to a JSONL file."""

    def __init__(self, session_id: str, metadata: dict[str, Any] | None = None):
        self.session_id = session_id
        self._entries: list[dict[str, Any]] = []
        self._start_time = time.time()
        self._total_tokens = 0
        self._total_cost = 0.0
        self._error_count = 0
        self._tool_count = 0

        self.record("session_start", {
            "session_id": session_id,
            "model": (metadata or {}).get("model", ""),
            "system_prompt": (metadata or {}).get("system_prompt", "")[:500],
            "provider": (metadata or {}).get("provider", ""),
        })

    def close(self, *args, reason: str = "completed", **kwargs) -> None:
        """Back-compat alias for finish(). Accepts ``status=`` kwarg."""
        try:
            self.finish(reason=kwargs.get("status", reason))
        except Exception:
            pass

    def record(self, event_type: str, data: dict[str, Any]):
        """Record an event. Writes immediately to file."""
        entry = {"type": event_type, "data": data}
        self._entries.append(entry)
        _write_entry(self.session_id, entry)

    def record_user_message(self, content: str):
        self.record("user_message", {"content": content[:2000]})

    def record_assistant_message(self, content: str, stop_reason: str = "", usage: dict | None = None):
        entry = {"content": content[:2000], "stop_reason": stop_reason}
        if usage:
            entry["usage"] = usage
            self._total_tokens += usage.get("total_tokens", 0)
            self._total_cost += usage.get("estimated_cost_usd", 0)
        self.record("assistant_message", entry)

    def record_tool_call(self, name: str, input_data: dict[str, Any]):
        self._tool_count += 1
        self.record("tool_call", {"name": name, "input": {k: str(v)[:200] for k, v in input_data.items()}})

    def record_tool_result(self, name: str, output: str, success: bool, duration_ms: float):
        self.record("tool_result", {
            "name": name,
            "output": output[:MAX_RESULT_CHARS],
            "success": success,
            "duration_ms": round(duration_ms, 1),
        })

    def record_compaction(self, before_tokens: int, after_tokens: int, trigger: str = "auto"):
        self.record("compaction", {"before_tokens": before_tokens, "after_tokens": after_tokens, "trigger": trigger})

    def record_error(self, error_type: str, message: str, recoverable: bool = True):
        self._error_count += 1
        self.record("error", {"type": error_type, "message": str(message)[:500], "recoverable": recoverable})

    def finish(self, reason: str = "completed"):
        """Finalize the session and move to samples/failed directory."""
        duration = time.time() - self._start_time
        self.record("session_end", {
            "reason": reason,
            "total_tokens": self._total_tokens,
            "total_cost": round(self._total_cost, 6),
            "duration_s": round(duration, 1),
            "tool_count": self._tool_count,
            "error_count": self._error_count,
        })

        # Copy to samples or failed directory
        src = _ensure_dir(self.session_id) / "trajectory.jsonl"
        if src.exists():
            if reason == "completed":
                dst = RECORDING_DIR / "trajectory_samples.jsonl"
            else:
                dst = RECORDING_DIR / "failed_trajectories.jsonl"
            try:
                with open(src, "r") as f_in, open(dst, "a", encoding="utf-8") as f_out:
                    for line in f_in:
                        f_out.write(line)
            except Exception as e:
                logger.warning("Failed to archive trajectory: %s", e)

    def get_summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_events": len(self._entries),
            "total_tokens": self._total_tokens,
            "total_cost": round(self._total_cost, 6),
            "tool_calls": self._tool_count,
            "errors": self._error_count,
            "duration_s": round(time.time() - self._start_time, 1),
        }


def replay_run(session_id: str) -> list[dict[str, Any]]:
    """Load the recorded trajectory for a session and return the events.

    Wire of C00-C-4 (CC4 replayable runs). The pattern from
    Greptile: "trace information so that a reviewer can independently
    verify the run" — and from session_recorder, "useful for
    debugging, replay (SessionReplay component), and fine-tuning data".

    Returns an empty list when the session has no recording (e.g.
    it never finished or was never started). Skips malformed lines
    rather than failing the whole replay.
    """
    path = RECORDING_DIR / session_id / "trajectory.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("replay_run: skipped malformed line for session %s", session_id)
    except OSError as exc:
        logger.warning("replay_run: failed to read %s: %s", path, exc)
    return events
