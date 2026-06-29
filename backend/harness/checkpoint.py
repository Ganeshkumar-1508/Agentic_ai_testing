"""Checkpoint/resume for delegation tree crash recovery.

Saves session state to the checkpoints table at key lifecycle points.
Resume restores the session, subagent registry, and task queue to continue
from where the crash occurred.

Checkpoint types (LangGraph-style per-superstep):
  - before_spawn:     Saved before delegate_task spawns a new subagent
  - after_subagent:   Saved after a subagent completes (result captured)
  - periodic:         Saved every N tool calls (configurable interval)
  - before_shutdown:  Saved on graceful shutdown
  - superstep:        Saved after each complete agent turn (LangGraph pattern)
  - before_action:    Saved before destructive actions (write_file, bash, commit)
  - approval_gate:    Saved when HITL approval is needed
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

CHECKPOINT_INTERVAL_TURNS = 1

# Actions that warrant a checkpoint before execution
DESTRUCTIVE_ACTIONS = {"write_file", "edit_file", "apply_patch", "bash", "commit_and_open_pr"}


class CheckpointManager:
    """Manages checkpoints for a single session.

    Usage in agent.py:
      mgr = CheckpointManager(db, session_id)
      await mgr.checkpoint("before_spawn", {...})
      await mgr.checkpoint("after_subagent", {...}, subagent_id="sa-1")
      await mgr.checkpoint_superstep(messages, turn_count, tool_results)
      await mgr.checkpoint_before_action("write_file", {...})
    """

    def __init__(self, db: Any, session_id: str):
        self.db = db
        self.session_id = session_id
        self._last_turn_checkpoint: int = 0

    async def checkpoint(
        self,
        ckpt_type: str,
        messages_snapshot: list[dict[str, Any]] | None = None,
        state_snapshot: dict[str, Any] | None = None,
        turn_count: int = 0,
        subagent_id: str | None = None,
    ) -> str | None:
        """Save a checkpoint. Returns checkpoint_id or None on failure."""
        if not self.session_id:
            return None
        try:
            # Check if session exists before inserting checkpoint
            session_exists = await self.db.fetchval(
                "SELECT EXISTS(SELECT 1 FROM sessions WHERE id = $1)",
                self.session_id
            )
            if not session_exists:
                logger.debug("Checkpoint skipped: session %s not found", self.session_id)
                return None
            
            ckpt_id = f"{self.session_id}-{ckpt_type}-{int(time.time() * 1000)}"
            await self.db.execute(
                """INSERT INTO checkpoints
                   (id, session_id, checkpoint_type, messages_snapshot,
                    state_snapshot, turn_count)
                   VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)""",
                ckpt_id,
                self.session_id,
                ckpt_type,
                json.dumps(messages_snapshot or []),
                json.dumps(state_snapshot or {}),
                turn_count,
            )
            self._last_turn_checkpoint = turn_count
            return ckpt_id
        except Exception as e:
            logger.warning("Checkpoint %s failed: %s", ckpt_type, e)
            return None

    async def checkpoint_superstep(
        self,
        messages: list[dict[str, Any]],
        turn_count: int,
        tool_results: list[tuple[str, str, str]] | None = None,
        extra_state: dict[str, Any] | None = None,
    ) -> str | None:
        """Save a checkpoint after each complete agent turn (LangGraph pattern).
        
        This is the granular checkpoint that enables:
        - Fault tolerance: Resume from last successful turn
        - Human-in-the-loop: Pause, get approval, resume
        - Time travel: Go back to any previous turn
        """
        state = {
            "turn_count": turn_count,
            "tool_results": [
                {"tool_call_id": tc_id, "tool_name": name, "result": result[:500]}
                for tc_id, name, result in (tool_results or [])
            ],
            "message_count": len(messages),
            **(extra_state or {}),
        }
        return await self.checkpoint(
            ckpt_type="superstep",
            messages_snapshot=messages[-10:],  # Last 10 messages for context
            state_snapshot=state,
            turn_count=turn_count,
        )

    async def checkpoint_before_action(
        self,
        action_type: str,
        messages: list[dict[str, Any]],
        turn_count: int,
        action_args: dict[str, Any] | None = None,
    ) -> str | None:
        """Save a checkpoint before destructive actions.
        
        Used for:
        - write_file: Before overwriting a file
        - bash: Before running a shell command
        - commit_and_open_pr: Before creating a PR
        """
        if action_type not in DESTRUCTIVE_ACTIONS:
            return None
        
        state = {
            "action_type": action_type,
            "action_args": action_args or {},
            "turn_count": turn_count,
        }
        return await self.checkpoint(
            ckpt_type=f"before_{action_type}",
            messages_snapshot=messages[-5:],  # Last 5 messages
            state_snapshot=state,
            turn_count=turn_count,
        )

    async def checkpoint_approval_gate(
        self,
        messages: list[dict[str, Any]],
        turn_count: int,
        pending_action: str,
        reason: str,
    ) -> str | None:
        """Save a checkpoint when HITL approval is needed.
        
        The checkpoint records:
        - What action is pending
        - Why approval is needed
        - Current messages for context
        """
        state = {
            "pending_action": pending_action,
            "reason": reason,
            "turn_count": turn_count,
            "awaiting_approval": True,
        }
        return await self.checkpoint(
            ckpt_type="approval_gate",
            messages_snapshot=messages[-5:],
            state_snapshot=state,
            turn_count=turn_count,
        )

    async def should_checkpoint(self, turn_count: int) -> bool:
        """Returns True if this turn count warrants a periodic checkpoint."""
        return (turn_count - self._last_turn_checkpoint) >= CHECKPOINT_INTERVAL_TURNS

    async def latest_checkpoint(self) -> dict[str, Any] | None:
        """Retrieve the most recent checkpoint for this session."""
        try:
            row = await self.db.fetchrow(
                "SELECT id, checkpoint_type, messages_snapshot, state_snapshot, "
                "turn_count, created_at FROM checkpoints "
                "WHERE session_id = $1 ORDER BY created_at DESC LIMIT 1",
                self.session_id,
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "type": row["checkpoint_type"],
                "messages": json.loads(row["messages_snapshot"]) if row["messages_snapshot"] else [],
                "state": json.loads(row["state_snapshot"]) if row["state_snapshot"] else {},
                "turn_count": row["turn_count"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
        except Exception as e:
            logger.warning("Failed to load checkpoint: %s", e)
            return None

    async def list_checkpoints(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent checkpoints for debugging."""
        try:
            rows = await self.db.fetch(
                "SELECT id, checkpoint_type, turn_count, created_at "
                "FROM checkpoints WHERE session_id = $1 "
                "ORDER BY created_at DESC LIMIT $2",
                self.session_id, limit,
            )
            return [
                {
                    "id": row["id"],
                    "type": row["checkpoint_type"],
                    "turn_count": row["turn_count"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("Failed to list checkpoints: %s", e)
            return []

    async def resume_state(self) -> dict[str, Any] | None:
        """Restore the most recent checkpoint state for crash recovery.

        Returns the state_snapshot dict, or None if no checkpoint exists.
        """
        ckpt = await self.latest_checkpoint()
        if not ckpt:
            return None

        try:
            raw = ckpt.get("state_snapshot", {})
            if isinstance(raw, str):
                return json.loads(raw)
            return raw
        except (json.JSONDecodeError, TypeError):
            return None
