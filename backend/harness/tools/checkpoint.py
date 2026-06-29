"""Checkpoint tool — wraps harness.checkpoint.CheckpointManager.

Saves a snapshot of the current delegation tree state to the
`checkpoints` table. The orchestrator's coordinator calls this at
key lifecycle moments (`before_spawn`, `after_subagent`, `periodic`,
`before_shutdown`) so a crash can resume from the latest checkpoint.

The `resume` operation restores the most recent snapshot's
`state_snapshot` so the calling agent can re-seed its state.

Module-level state is injected at app startup via `set_checkpoint_db`.
This mirrors the `set_introspection_store` pattern in
`chat_introspection.py`: a closed seam between the tool layer and
infrastructure (Postgres).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


# Module-level dependency. Set once at app startup by api/main.py.
# If unset, the tool returns a clear "not initialized" error.
_deps_ref: dict[str, Any] = {}


def set_checkpoint_db(db: Any) -> None:
    """Inject the Postgres connection pool at app startup.

    `db` is expected to expose `execute(query, *args)` and
    `fetchrow(query, *args)` async methods (asyncpg-style).
    """
    _deps_ref["db"] = db


def _db() -> Any:
    return _deps_ref.get("db")


_VALID_TYPES = frozenset({
    "before_spawn", "after_subagent", "periodic", "before_shutdown",
})


class CheckpointTool(BaseTool):
    name = "checkpoint"
    default_level = "allow"
    description = (
        "Save a snapshot of the current session's delegation tree "
        "state to the checkpoints table. Pass checkpoint_type "
        "(before_spawn, after_subagent, periodic, before_shutdown), "
        "an optional state_snapshot dict, and an optional turn_count. "
        "Returns the new checkpoint_id. Use this to make long-running "
        "orchestration recoverable across process restarts."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "checkpoint_type": {
                        "type": "string",
                        "enum": sorted(_VALID_TYPES),
                        "description": "Lifecycle moment the checkpoint captures",
                    },
                    "state_snapshot": {
                        "type": "object",
                        "description": "JSON-serialisable state to persist",
                    },
                    "messages_snapshot": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional message history snapshot",
                    },
                    "turn_count": {"type": "integer", "default": 0, "minimum": 0},
                    "subagent_id": {"type": "string"},
                },
                "required": ["checkpoint_type"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        ckpt_type = kwargs.get("checkpoint_type")
        if not ckpt_type:
            return ToolResult(success=False, output="`checkpoint_type` is required", error="missing_arg")
        if ckpt_type not in _VALID_TYPES:
            return ToolResult(
                success=False,
                output=f"Invalid checkpoint_type. Must be one of {sorted(_VALID_TYPES)}",
                error="invalid_arg",
            )
        db = _db()
        session_id = kwargs.get("session_id") or ""
        if not db:
            return ToolResult(
                success=False,
                output="Checkpoint DB not initialised. Call `set_checkpoint_db` at startup.",
                error="not_initialised",
            )
        if not session_id:
            return ToolResult(
                success=False, output="`session_id` is required for checkpoint",
                error="missing_arg",
            )
        import time
        state = kwargs.get("state_snapshot") or {}
        messages = kwargs.get("messages_snapshot") or []
        turn = int(kwargs.get("turn_count", 0) or 0)
        try:
            ckpt_id = f"{session_id}-{ckpt_type}-{int(time.time() * 1000)}"
            await db.execute(
                "INSERT INTO checkpoints "
                "(id, session_id, checkpoint_type, messages_snapshot, "
                "state_snapshot, turn_count) "
                "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)",
                ckpt_id, session_id, ckpt_type,
                json.dumps(messages), json.dumps(state), turn,
            )
            return ToolResult(
                success=True,
                output=f"Checkpoint `{ckpt_id}` saved (type={ckpt_type}, turn={turn}).",
                data={"checkpoint_id": ckpt_id, "type": ckpt_type, "turn": turn},
            )
        except Exception as exc:
            logger.warning("Checkpoint failed: %s", exc)
            return ToolResult(
                success=False, output=f"Checkpoint write failed: {exc}",
                error="db_error",
            )


class CheckpointResumeTool(BaseTool):
    name = "checkpoint_resume"
    default_level = "allow"
    description = (
        "Restore the most recent checkpoint for the current session. "
        "Returns the state_snapshot dict from the latest checkpoint, "
        "or None if no checkpoint exists. Use this on process restart "
        "to recover the delegation tree state."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={"type": "object", "properties": {}},
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        db = _db()
        session_id = kwargs.get("session_id") or ""
        if not db:
            return ToolResult(
                success=False,
                output="Checkpoint DB not initialised. Call `set_checkpoint_db` at startup.",
                error="not_initialised",
            )
        if not session_id:
            return ToolResult(success=False, output="`session_id` is required", error="missing_arg")
        try:
            row = await db.fetchrow(
                "SELECT id, checkpoint_type, state_snapshot, messages_snapshot, "
                "turn_count, created_at FROM checkpoints "
                "WHERE session_id = $1 ORDER BY created_at DESC LIMIT 1",
                session_id,
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Resume read failed: {exc}", error="db_error")
        if not row:
            return ToolResult(
                success=True,
                output=f"No checkpoint found for session {session_id}.",
                data={"state": None},
            )
        # asyncpg returns JSONB as Python dict/list, but in case the
        # driver returns a string, normalise.
        raw_state = row.get("state_snapshot", {})
        if isinstance(raw_state, str):
            try:
                state = json.loads(raw_state)
            except (json.JSONDecodeError, TypeError):
                state = {}
        else:
            state = raw_state or {}
        return ToolResult(
            success=True,
            output=(
                f"Resumed checkpoint `{row['id']}` "
                f"(type={row['checkpoint_type']}, turn={row['turn_count']})."
            ),
            data={
                "checkpoint_id": row["id"],
                "type": row["checkpoint_type"],
                "state": state,
                "turn_count": row["turn_count"],
                "created_at": str(row["created_at"]),
            },
        )


registry.register(CheckpointTool(), toolset="read")
registry.register(CheckpointResumeTool(), toolset="read")
