"""team_* tools — coordinator / lead / member team coordination.

C02 (per docs/2026-06-21-architecture-decision-tree.md#c02).

Six tools, gated by role (per Q3 and Q4 of the C02 decision tree):

  Coordinator / Lead:
    - team_create           (Q2) create a new team
    - team_message          (Q3) send a message (broadcast or to a member)
    - team_list_messages    (Q3) read team's message thread
    - team_list_members     (Q3) read team's members
    - team_member_progress  (Q3) view members' statuses
    - team_dissolve         (Q3) explicitly end the team (Q5)

  Member:
    - team_message          send a message to the lead or another member
    - team_list_messages    read messages addressed to me (incl. broadcasts)
    - team_list_members     see who else is on the team

The role gating lives in ``toolsets.py``: ``team_lead`` gets all
six tools, ``team_member`` gets the three-member subset. The
:class:`DelegateTaskTool` auto-selects the right toolset based on
the lead/member role.

Per Q1 (pure coordination), no team-aggregation tool exists —
the per-subagent draft PRs from C01 are the integration surface.
Per Q5 (hybrid lifecycle), explicit dissolve and the
:func:`TeamService.cleanup_completed` cron auto-dissolve are both
implemented.

Public surface (stable):
  TeamCreateTool, TeamMessageTool, TeamListMessagesTool,
  TeamListMembersTool, TeamMemberProgressTool, TeamDissolveTool
"""
from __future__ import annotations

import json
import logging
from typing import Any

from harness.services.team_service import (
    MemberNotFoundError,
    MemberRole,
    MemberStatus,
    MessageKind,
    TeamDissolvedError,
    TeamError,
    TeamNotFoundError,
    TeamService,
    TeamStatus,
    validate_team_name,
)
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service() -> TeamService:
    """Build a :class:`TeamService` against the shared DB.

    The DB is discovered via ``harness.memory.db_context.get_db``
    which is the same seam the kanban + worktree + heartbeat
    services use. Returns ``None`` if the DB isn't connected —
    callers turn that into a structured error.
    """
    from harness.memory.db_context import get_db
    db = get_db()
    if db is None or getattr(db, "_pool", None) is None:
        return None
    return TeamService(db)


def _ok(payload: Any) -> ToolResult:
    return ToolResult(success=True, output=json.dumps(payload, default=str))


def _err(message: str, code: str, **extra: Any) -> ToolResult:
    return ToolResult(
        success=False, output=message, error=code,
        data={"error_code": code, **extra},
    )


# ---------------------------------------------------------------------------
# TeamCreateTool — coordinator + lead-only
# ---------------------------------------------------------------------------


class TeamCreateTool(BaseTool):
    name = "team_create"
    description = (
        "Create a new agent team. Returns a team_id. The caller "
        "becomes the lead. Members are added later by calling "
        "``delegate_task(team_id=<this>)`` — the spawned subagent "
        "is automatically added to the team with role=member. "
        "Use ``team_dissolve`` to end the team explicitly, or the "
        "system auto-dissolves when all members finish."
    )
    default_level = "allow"
    capabilities = ["can_orchestrate"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable team name (validated).",
                    },
                    "goal": {
                        "type": "string",
                        "description": "The team's objective — visible to all members.",
                    },
                    "lead_subagent_id": {
                        "type": "string",
                        "description": "Subagent id of the lead. Defaults to the caller's subagent_id.",
                    },
                },
                "required": ["name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("name", "")
        goal = kwargs.get("goal", "")
        lead_subagent_id = kwargs.get("lead_subagent_id", "") or ""
        try:
            validate_team_name(name)
        except ValueError as exc:
            return _err(str(exc), "invalid_name")

        svc = _service()
        if svc is None:
            return _err("Database not connected", "no_db")

        # Fall back to the caller's subagent_id if not provided.
        if not lead_subagent_id:
            from harness.tools.delegate_task import _active_subagents_lock, _active_subagents
            with _active_subagents_lock:
                # The lead is the currently-running subagent. In a
                # production system this would be the subagent's
                # own ID via a contextvar. For MVP, the caller
                # is expected to pass it.
                for sid, rec in _active_subagents.items():
                    if rec.get("status") == "running":
                        lead_subagent_id = sid
                        break
        if not lead_subagent_id:
            return _err(
                "lead_subagent_id is required (no active subagent found)",
                "no_lead",
            )

        try:
            team = await svc.create_team(
                name, lead_subagent_id=lead_subagent_id, goal=goal,
            )
        except Exception as exc:
            logger.error("team_create failed: %s", exc)
            return _err(f"create_team failed: {exc}", "create_failed")
        return _ok(team.to_dict())


# ---------------------------------------------------------------------------
# TeamMessageTool — lead + member
# ---------------------------------------------------------------------------


class TeamMessageTool(BaseTool):
    name = "team_message"
    description = (
        "Post a message to the team's thread. If ``to_subagent_id`` "
        "is omitted, the message is broadcast to all members. If "
        "set, only that member sees the message. Members can send "
        "to the lead; the lead can send to any member."
    )
    default_level = "allow"
    capabilities = ["can_team_message"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "team_id": {
                        "type": "string",
                        "description": "The team to post to.",
                    },
                    "from_subagent_id": {
                        "type": "string",
                        "description": "Sender. Defaults to the caller's subagent_id.",
                    },
                    "to_subagent_id": {
                        "type": "string",
                        "description": "Recipient. Omit for broadcast (visible to all members).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Message body. Truncated to 10000 chars.",
                    },
                },
                "required": ["team_id", "content"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        team_id = kwargs.get("team_id", "")
        from_subagent_id = kwargs.get("from_subagent_id", "") or None
        to_subagent_id = kwargs.get("to_subagent_id", "") or None
        content = kwargs.get("content", "")
        if not team_id:
            return _err("team_id is required", "missing_team_id")
        if not content:
            return _err("content is required", "missing_content")
        svc = _service()
        if svc is None:
            return _err("Database not connected", "no_db")
        try:
            msg = await svc.send_message(
                team_id, from_subagent_id, to_subagent_id, content,
            )
        except TeamNotFoundError as exc:
            return _err(str(exc), "team_not_found")
        except MemberNotFoundError as exc:
            return _err(str(exc), "member_not_found")
        except Exception as exc:
            logger.error("team_message failed: %s", exc)
            return _err(f"send_message failed: {exc}", "send_failed")
        return _ok(msg.to_dict())


# ---------------------------------------------------------------------------
# TeamListMessagesTool — lead + member
# ---------------------------------------------------------------------------


class TeamListMessagesTool(BaseTool):
    name = "team_list_messages"
    description = (
        "List messages in the team's thread. If the caller is a "
        "member, only messages addressed to them (or broadcasts) "
        "are returned. If the caller is the lead, all messages "
        "are returned."
    )
    default_level = "allow"
    capabilities = ["can_team_read"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                    "subagent_id": {
                        "type": "string",
                        "description": "Defaults to the caller's subagent_id. "
                                       "Set explicitly to read another member's view.",
                    },
                    "limit": {"type": "integer", "default": 200},
                    "since_id": {
                        "type": "integer",
                        "default": 0,
                        "description": "Return only messages with id > since_id (for polling).",
                    },
                },
                "required": ["team_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        team_id = kwargs.get("team_id", "")
        subagent_id = kwargs.get("subagent_id", "") or None
        limit = int(kwargs.get("limit", 200))
        since_id = int(kwargs.get("since_id", 0))
        if not team_id:
            return _err("team_id is required", "missing_team_id")
        svc = _service()
        if svc is None:
            return _err("Database not connected", "no_db")
        try:
            msgs = await svc.list_messages(
                team_id, for_subagent_id=subagent_id,
                limit=limit, since_id=since_id,
            )
        except TeamNotFoundError as exc:
            return _err(str(exc), "team_not_found")
        return _ok({
            "messages": [m.to_dict() for m in msgs],
            "count": len(msgs),
        })


# ---------------------------------------------------------------------------
# TeamListMembersTool — lead + member
# ---------------------------------------------------------------------------


class TeamListMembersTool(BaseTool):
    name = "team_list_members"
    description = "List members of a team with their role and status."
    default_level = "allow"
    capabilities = ["can_team_read"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                },
                "required": ["team_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        team_id = kwargs.get("team_id", "")
        if not team_id:
            return _err("team_id is required", "missing_team_id")
        svc = _service()
        if svc is None:
            return _err("Database not connected", "no_db")
        try:
            team = await svc.get_team(team_id)
            members = await svc.list_members(team_id)
        except TeamNotFoundError as exc:
            return _err(str(exc), "team_not_found")
        return _ok({
            "team": team.to_dict(),
            "members": [m.to_dict() for m in members],
            "active_count": sum(1 for m in members if m.status == MemberStatus.ACTIVE),
        })


# ---------------------------------------------------------------------------
# TeamMemberProgressTool — lead-only
# ---------------------------------------------------------------------------


class TeamMemberProgressTool(BaseTool):
    name = "team_member_progress"
    description = (
        "Lead-only: view each member's status and last activity "
        "(their last message timestamp, if any). Useful for the "
        "lead to see who's stuck."
    )
    default_level = "allow"
    capabilities = ["can_team_lead"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                },
                "required": ["team_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        team_id = kwargs.get("team_id", "")
        if not team_id:
            return _err("team_id is required", "missing_team_id")
        svc = _service()
        if svc is None:
            return _err("Database not connected", "no_db")
        try:
            members = await svc.list_members(team_id)
        except TeamNotFoundError as exc:
            return _err(str(exc), "team_not_found")

        # For each active member, look up their last message
        # timestamp. This is one extra query per member — fine
        # for teams of <20.
        progress: list[dict[str, Any]] = []
        for m in members:
            row = await _db().fetchrow(
                "SELECT MAX(created_at) AS last_msg_at "
                "FROM team_messages "
                "WHERE team_id = $1 "
                "AND (from_subagent_id = $2 "
                "     OR to_subagent_id = $2 "
                "     OR (to_subagent_id IS NULL AND from_subagent_id IS NOT NULL))",
                team_id, m.subagent_id,
            )
            last_msg_at = row["last_msg_at"].timestamp() if row and row["last_msg_at"] else None
            progress.append({
                **m.to_dict(),
                "last_message_at": last_msg_at,
            })
        return _ok({
            "team_id": team_id,
            "progress": progress,
        })


def _db() -> Any:
    from harness.memory.db_context import get_db
    return get_db()


# ---------------------------------------------------------------------------
# TeamDissolveTool — lead-only
# ---------------------------------------------------------------------------


class TeamDissolveTool(BaseTool):
    name = "team_dissolve"
    description = (
        "Lead-only: explicitly end the team. Idempotent — "
        "dissolving an already-dissolved team is a no-op. The "
        "team is also auto-dissolved by the system when all "
        "members finish (or fail)."
    )
    default_level = "allow"
    capabilities = ["can_team_lead"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                },
                "required": ["team_id"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        team_id = kwargs.get("team_id", "")
        if not team_id:
            return _err("team_id is required", "missing_team_id")
        svc = _service()
        if svc is None:
            return _err("Database not connected", "no_db")
        try:
            dissolved = await svc.dissolve(team_id)
        except TeamNotFoundError as exc:
            return _err(str(exc), "team_not_found")
        return _ok({
            "team_id": team_id,
            "newly_dissolved": dissolved,
        })


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


# Two toolsets per Q3/Q4: lead gets full surface, member gets read+reply.
LEAD_TOOLS = [
    TeamCreateTool,
    TeamMessageTool,
    TeamListMessagesTool,
    TeamListMembersTool,
    TeamMemberProgressTool,
    TeamDissolveTool,
]
MEMBER_TOOLS = [
    TeamMessageTool,
    TeamListMessagesTool,
    TeamListMembersTool,
]

# Register in the appropriate toolsets. The set is small enough
# that we wire each tool to the right toolset explicitly.
for _tool_cls in LEAD_TOOLS:
    _set_name = "team_lead" if _tool_cls in (TeamCreateTool, TeamMemberProgressTool, TeamDissolveTool) else "team_shared"
    instance = _tool_cls()
    registry.register(instance, toolset=_set_name)

for _tool_cls in MEMBER_TOOLS:
    instance = _tool_cls()
    # Already registered above (idempotent — registry deduplicates by name)
