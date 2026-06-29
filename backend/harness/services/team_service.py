"""TeamService — Postgres-backed coordination for agent teams.

C02 (per docs/2026-06-21-architecture-decision-tree.md#c02):
  Q1: Team scope = pure coordination (no aggregation; per-subagent
      PRs from C01 are the integration surface)
  Q2: Creation model = dynamic via ``team_create`` tool
  Q3: Lead's toolset = full ``team_*`` surface
  Q4: Member's toolset = read + reply (no broadcast, no management)
  Q5: Lifecycle = hybrid (explicit dissolve OR auto when all members
      done)
  Q6: State storage = Postgres (cross-process visibility, matches
      TestAI's existing patterns; OpenHarness uses filesystem)

The TeamService is a thin data-access layer over the ``teams``,
``team_members``, and ``team_messages`` tables. It is purely
stateful — coordination logic (e.g. auto-dissolve, broadcast
routing) lives in the tool layer or the ``TeamCoordinator`` which
is the seam for future cron / event-driven sweeps.

Public surface (stable):
  TeamService, Team, TeamMember, TeamMessage, TeamStatus, MemberStatus,
  MessageKind, TeamNotFoundError, MemberNotFoundError, TeamDissolvedError
"""
from __future__ import annotations

import enum
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TeamStatus(str, enum.Enum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"


class MemberStatus(str, enum.Enum):
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


class MemberRole(str, enum.Enum):
    LEAD = "lead"
    MEMBER = "member"


class MessageKind(str, enum.Enum):
    MESSAGE = "message"
    STATUS = "status"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TeamError(Exception):
    """Base class for team-related errors."""


class TeamNotFoundError(TeamError):
    """Raised when ``team_id`` doesn't exist (or was dissolved)."""


class TeamDissolvedError(TeamError):
    """Raised when an operation targets a dissolved team."""


class MemberNotFoundError(TeamError):
    """Raised when ``subagent_id`` isn't a member of the team."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Team:
    """A coordination team."""
    team_id: str
    name: str
    lead_subagent_id: str
    lead_session_id: str
    goal: str
    status: TeamStatus
    created_at: float
    dissolved_at: float | None
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "lead_subagent_id": self.lead_subagent_id,
            "lead_session_id": self.lead_session_id,
            "goal": self.goal,
            "status": self.status.value,
            "created_at": self.created_at,
            "dissolved_at": self.dissolved_at,
            "config": dict(self.config),
        }


@dataclass(frozen=True)
class TeamMember:
    """A member (lead or worker) of a team."""
    team_id: str
    subagent_id: str
    role: MemberRole
    role_name: str
    status: MemberStatus
    joined_at: float
    left_at: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "subagent_id": self.subagent_id,
            "role": self.role.value,
            "role_name": self.role_name,
            "status": self.status.value,
            "joined_at": self.joined_at,
            "left_at": self.left_at,
        }


@dataclass(frozen=True)
class TeamMessage:
    """A message in a team's conversation thread."""
    id: int
    team_id: str
    from_subagent_id: str | None
    to_subagent_id: str | None  # None = broadcast
    content: str
    kind: MessageKind
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "from_subagent_id": self.from_subagent_id,
            "to_subagent_id": self.to_subagent_id,
            "content": self.content,
            "kind": self.kind.value,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


_VALID_TEAM_NAME = re.compile(r"^[A-Za-z0-9 ._:\-]+$")
_MAX_NAME_LENGTH = 100
_MAX_CONTENT_LENGTH = 10_000


def validate_team_name(name: str) -> str:
    """Validate a team name.

    Rules:
      - Non-empty, max 100 chars
      - Allows letters, digits, spaces, ``. _ : -``
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Team name must not be empty")
    if len(name) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"Team name must be {_MAX_NAME_LENGTH} characters or fewer (got {len(name)})"
        )
    if not _VALID_TEAM_NAME.match(name):
        raise ValueError(
            f"Team name {name!r}: only letters, digits, spaces, and . _ : - are allowed"
        )
    return name


# ---------------------------------------------------------------------------
# TeamService
# ---------------------------------------------------------------------------


class TeamService:
    """Postgres-backed team coordination.

    The service is intentionally thin — it owns the data, not the
    coordination logic. The auto-dissolve rule (Q5) is exposed as
    :meth:`cleanup_completed` for callers to invoke from a cron
    or event loop. The team tools (``backend/harness/tools/team_tools.py``)
    wrap this service with role-gated dispatch.

    Args:
      db: An async Postgres connection pool, matching the shape of
        ``harness.memory.database.Database``. The service doesn't
        typecheck the pool — it just calls ``fetch``/``execute``
        and assumes the caller knows what they're doing.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------

    async def create_team(
        self,
        name: str,
        *,
        lead_subagent_id: str,
        lead_session_id: str = "",
        goal: str = "",
        config: dict[str, Any] | None = None,
    ) -> Team:
        """Create a new team.

        Args:
          name: Human-readable team name (validated).
          lead_subagent_id: Subagent id of the lead (typically the
            subagent that called ``team_create``).
          lead_session_id: Session id of the lead (for dashboard
            correlation).
          goal: Free-form team objective (visible to all members).
          config: Optional JSONB config blob for future extensions.

        Returns:
          The new :class:`Team` (with ``status=ACTIVE``).
        """
        validated_name = validate_team_name(name)
        team_id = f"team-{uuid.uuid4().hex[:8]}"
        now = time.time()
        cfg = dict(config or {})
        try:
            await self._db.execute(
                "INSERT INTO teams "
                "(team_id, name, lead_subagent_id, lead_session_id, "
                "goal, status, created_at, config) "
                "VALUES ($1, $2, $3, $4, $5, 'active', NOW(), $6::jsonb)",
                team_id, validated_name, lead_subagent_id, lead_session_id,
                goal, json.dumps(cfg),
            )
            # Lead is also a member (with role='lead') so the
            # lead can read team messages like any other member.
            await self._db.execute(
                "INSERT INTO team_members "
                "(team_id, subagent_id, role, role_name, status, joined_at) "
                "VALUES ($1, $2, 'lead', '', 'active', NOW())",
                team_id, lead_subagent_id,
            )
        except Exception as exc:
            logger.error("create_team failed: %s", exc)
            raise

        logger.info(
            "team created: team_id=%s name=%r lead=%s",
            team_id, validated_name, lead_subagent_id,
        )
        return Team(
            team_id=team_id,
            name=validated_name,
            lead_subagent_id=lead_subagent_id,
            lead_session_id=lead_session_id,
            goal=goal,
            status=TeamStatus.ACTIVE,
            created_at=now,
            dissolved_at=None,
            config=cfg,
        )

    async def get_team(self, team_id: str) -> Team:
        """Fetch a team by id. Raises :class:`TeamNotFoundError` if
        the team doesn't exist OR is dissolved — dissolved teams
        are filtered out at the query level so callers can't
        operate on dead state.
        """
        row = await self._db.fetchrow(
            "SELECT team_id, name, lead_subagent_id, lead_session_id, "
            "goal, status, created_at, dissolved_at, config "
            "FROM teams WHERE team_id = $1 AND status = 'active'",
            team_id,
        )
        if row is None:
            raise TeamNotFoundError(f"Team {team_id!r} not found")
        return _team_from_row(row)

    async def get_team_including_dissolved(self, team_id: str) -> Team:
        """Like :meth:`get_team` but returns dissolved teams too.
        Useful for the dashboard's "team history" view."""
        row = await self._db.fetchrow(
            "SELECT team_id, name, lead_subagent_id, lead_session_id, "
            "goal, status, created_at, dissolved_at, config "
            "FROM teams WHERE team_id = $1",
            team_id,
        )
        if row is None:
            raise TeamNotFoundError(f"Team {team_id!r} not found")
        return _team_from_row(row)

    async def list_teams(
        self,
        *,
        status: TeamStatus | None = None,
        lead_session_id: str | None = None,
        limit: int = 100,
    ) -> list[Team]:
        """List teams with optional filters."""
        where: list[str] = []
        args: list[Any] = []
        if status is not None:
            args.append(status.value)
            where.append(f"status = ${len(args)}")
        if lead_session_id is not None:
            args.append(lead_session_id)
            where.append(f"lead_session_id = ${len(args)}")
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        args.append(limit)
        sql = (
            f"SELECT team_id, name, lead_subagent_id, lead_session_id, "
            f"goal, status, created_at, dissolved_at, config "
            f"FROM teams {where_clause} "
            f"ORDER BY created_at DESC LIMIT ${len(args)}"
        )
        rows = await self._db.fetch(sql, *args)
        return [_team_from_row(r) for r in rows]

    async def dissolve(self, team_id: str) -> bool:
        """Dissolve a team.

        Idempotent — dissolving an already-dissolved team is a
        no-op. Returns ``True`` if the team was newly dissolved,
        ``False`` if it was already dissolved.
        """
        existing = await self.get_team_including_dissolved(team_id)
        if existing.status == TeamStatus.DISSOLVED:
            return False
        await self._db.execute(
            "UPDATE teams SET status = 'dissolved', dissolved_at = NOW() "
            "WHERE team_id = $1",
            team_id,
        )
        # Mark all members as left.
        await self._db.execute(
            "UPDATE team_members SET status = 'done', left_at = NOW() "
            "WHERE team_id = $1 AND left_at IS NULL",
            team_id,
        )
        # Post a system message so the timeline shows the dissolve.
        await self._post_system_message(
            team_id, f"Team dissolved at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        )
        logger.info("team dissolved: team_id=%s", team_id)
        return True

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def add_member(
        self,
        team_id: str,
        subagent_id: str,
        *,
        role: MemberRole = MemberRole.MEMBER,
        role_name: str = "",
    ) -> TeamMember:
        """Add a member to the team. Idempotent — re-adding a member
        updates the existing row (e.g. changes role_name).
        """
        team = await self.get_team(team_id)  # raises if missing/dissolved
        now = time.time()
        try:
            await self._db.execute(
                "INSERT INTO team_members "
                "(team_id, subagent_id, role, role_name, status, joined_at) "
                "VALUES ($1, $2, $3, $4, 'active', NOW()) "
                "ON CONFLICT (team_id, subagent_id) DO UPDATE "
                "SET role = EXCLUDED.role, role_name = EXCLUDED.role_name, "
                "    left_at = NULL, status = 'active'",
                team.team_id, subagent_id, role.value, role_name,
            )
        except Exception as exc:
            logger.error(
                "add_member failed: team_id=%s subagent_id=%s err=%s",
                team_id, subagent_id, exc,
            )
            raise
        return TeamMember(
            team_id=team_id,
            subagent_id=subagent_id,
            role=role,
            role_name=role_name,
            status=MemberStatus.ACTIVE,
            joined_at=now,
            left_at=None,
        )

    async def remove_member(self, team_id: str, subagent_id: str) -> bool:
        """Mark a member as left. Returns ``True`` if the member was
        present and is now left; ``False`` if the member wasn't in
        the team.
        """
        row = await self._db.fetchrow(
            "UPDATE team_members SET status = 'done', left_at = NOW() "
            "WHERE team_id = $1 AND subagent_id = $2 AND left_at IS NULL "
            "RETURNING subagent_id",
            team_id, subagent_id,
        )
        return row is not None

    async def update_member_status(
        self,
        team_id: str,
        subagent_id: str,
        status: MemberStatus,
    ) -> bool:
        """Update a member's status (active/done/failed)."""
        if not await self._is_member(team_id, subagent_id):
            raise MemberNotFoundError(
                f"{subagent_id!r} is not a member of {team_id!r}"
            )
        await self._db.execute(
            "UPDATE team_members SET status = $1 "
            "WHERE team_id = $2 AND subagent_id = $3",
            status.value, team_id, subagent_id,
        )
        return True

    async def list_members(self, team_id: str) -> list[TeamMember]:
        """List members of a team."""
        rows = await self._db.fetch(
            "SELECT team_id, subagent_id, role, role_name, status, "
            "joined_at, left_at "
            "FROM team_members WHERE team_id = $1 "
            "ORDER BY joined_at ASC",
            team_id,
        )
        return [_member_from_row(r) for r in rows]

    async def get_member(
        self, team_id: str, subagent_id: str,
    ) -> TeamMember:
        """Fetch a specific team member."""
        row = await self._db.fetchrow(
            "SELECT team_id, subagent_id, role, role_name, status, "
            "joined_at, left_at "
            "FROM team_members WHERE team_id = $1 AND subagent_id = $2",
            team_id, subagent_id,
        )
        if row is None:
            raise MemberNotFoundError(
                f"{subagent_id!r} is not a member of {team_id!r}"
            )
        return _member_from_row(row)

    async def _is_member(self, team_id: str, subagent_id: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT 1 FROM team_members "
            "WHERE team_id = $1 AND subagent_id = $2 LIMIT 1",
            team_id, subagent_id,
        )
        return row is not None

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def send_message(
        self,
        team_id: str,
        from_subagent_id: str | None,
        to_subagent_id: str | None,
        content: str,
        *,
        kind: MessageKind = MessageKind.MESSAGE,
    ) -> TeamMessage:
        """Post a message to the team's thread.

        Args:
          team_id: Target team.
          from_subagent_id: Sender. ``None`` for system messages.
          to_subagent_id: Recipient. ``None`` for broadcast (visible
            to all members).
          content: Message body (truncated to 10K chars).
          kind: ``message`` (default) / ``status`` / ``system``.
        """
        # Defensive: ensure the team exists + sender is a member
        # (for non-system messages).
        team = await self.get_team(team_id)  # raises if missing
        if from_subagent_id is not None and kind != MessageKind.SYSTEM:
            if not await self._is_member(team_id, from_subagent_id):
                raise MemberNotFoundError(
                    f"{from_subagent_id!r} is not a member of {team_id!r}"
                )
        # If ``to`` is set, recipient must be a member.
        if to_subagent_id is not None and not await self._is_member(
            team_id, to_subagent_id,
        ):
            raise MemberNotFoundError(
                f"{to_subagent_id!r} is not a member of {team_id!r}"
            )
        # Truncate content to keep the table tidy.
        if len(content) > _MAX_CONTENT_LENGTH:
            content = content[:_MAX_CONTENT_LENGTH] + "…"
        row = await self._db.fetchrow(
            "INSERT INTO team_messages "
            "(team_id, from_subagent_id, to_subagent_id, content, kind, created_at) "
            "VALUES ($1, $2, $3, $4, $5, NOW()) "
            "RETURNING id, created_at",
            team_id, from_subagent_id, to_subagent_id, content, kind.value,
        )
        msg_id = int(row["id"])
        created_at_ts = float(row["created_at"].timestamp())
        logger.debug(
            "team_message: team_id=%s id=%d from=%s to=%s kind=%s",
            team_id, msg_id, from_subagent_id, to_subagent_id, kind.value,
        )
        return TeamMessage(
            id=msg_id,
            team_id=team_id,
            from_subagent_id=from_subagent_id,
            to_subagent_id=to_subagent_id,
            content=content,
            kind=kind,
            created_at=created_at_ts,
        )

    async def list_messages(
        self,
        team_id: str,
        *,
        for_subagent_id: str | None = None,
        limit: int = 200,
        since_id: int = 0,
    ) -> list[TeamMessage]:
        """List messages for a team.

        If ``for_subagent_id`` is set, the result includes
        broadcasts (``to_subagent_id IS NULL``) AND direct messages
        to that subagent. Otherwise all messages are returned.
        """
        if for_subagent_id is not None:
            sql = (
                "SELECT id, team_id, from_subagent_id, to_subagent_id, "
                "content, kind, created_at "
                "FROM team_messages "
                "WHERE team_id = $1 AND id > $2 "
                "AND (to_subagent_id IS NULL OR to_subagent_id = $3 "
                "     OR from_subagent_id = $3) "
                "ORDER BY id ASC LIMIT $4"
            )
            rows = await self._db.fetch(
                sql, team_id, since_id, for_subagent_id, limit,
            )
        else:
            sql = (
                "SELECT id, team_id, from_subagent_id, to_subagent_id, "
                "content, kind, created_at "
                "FROM team_messages "
                "WHERE team_id = $1 AND id > $2 "
                "ORDER BY id ASC LIMIT $3"
            )
            rows = await self._db.fetch(sql, team_id, since_id, limit)
        return [_message_from_row(r) for r in rows]

    async def _post_system_message(self, team_id: str, content: str) -> None:
        """Internal: post a system message (no sender, broadcast)."""
        if len(content) > _MAX_CONTENT_LENGTH:
            content = content[:_MAX_CONTENT_LENGTH] + "…"
        await self._db.execute(
            "INSERT INTO team_messages "
            "(team_id, from_subagent_id, to_subagent_id, content, kind, created_at) "
            "VALUES ($1, NULL, NULL, $2, 'system', NOW())",
            team_id, content,
        )

    # ------------------------------------------------------------------
    # Lifecycle (Q5: hybrid — explicit OR auto-dissolve)
    # ------------------------------------------------------------------

    async def cleanup_completed(self) -> list[str]:
        """Auto-dissolve teams where every member is ``done`` or
        ``failed`` and the lead hasn't explicitly kept the team
        alive.

        Returns the list of team_ids that were auto-dissolved.
        Designed to be called from a cron or event loop (e.g. after
        a subagent completion event).
        """
        rows = await self._db.fetch(
            "SELECT t.team_id, "
            "  COUNT(*) FILTER (WHERE m.status = 'active')::int AS active_members, "
            "  COUNT(*)::int AS total_members "
            "FROM teams t "
            "JOIN team_members m ON m.team_id = t.team_id "
            "WHERE t.status = 'active' "
            "GROUP BY t.team_id "
            "HAVING COUNT(*) FILTER (WHERE m.status = 'active') = 0",
        )
        dissolved: list[str] = []
        for row in rows:
            team_id = row["team_id"]
            try:
                if await self.dissolve(team_id):
                    dissolved.append(team_id)
            except Exception as exc:
                logger.warning(
                    "cleanup_completed: dissolve %s failed: %s",
                    team_id, exc,
                )
        if dissolved:
            logger.info(
                "cleanup_completed: auto-dissolved %d teams: %s",
                len(dissolved), dissolved,
            )
        return dissolved


# ---------------------------------------------------------------------------
# Row → dataclass helpers
# ---------------------------------------------------------------------------


def _team_from_row(row: Any) -> Team:
    cfg = row["config"]
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (TypeError, ValueError):
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    return Team(
        team_id=row["team_id"],
        name=row["name"],
        lead_subagent_id=row["lead_subagent_id"] or "",
        lead_session_id=row["lead_session_id"] or "",
        goal=row["goal"] or "",
        status=TeamStatus(row["status"]),
        created_at=float(row["created_at"].timestamp()),
        dissolved_at=(
            float(row["dissolved_at"].timestamp())
            if row["dissolved_at"] is not None else None
        ),
        config=cfg,
    )


def _member_from_row(row: Any) -> TeamMember:
    return TeamMember(
        team_id=row["team_id"],
        subagent_id=row["subagent_id"],
        role=MemberRole(row["role"]),
        role_name=row["role_name"] or "",
        status=MemberStatus(row["status"]),
        joined_at=float(row["joined_at"].timestamp()),
        left_at=(
            float(row["left_at"].timestamp())
            if row["left_at"] is not None else None
        ),
    )


def _message_from_row(row: Any) -> TeamMessage:
    return TeamMessage(
        id=int(row["id"]),
        team_id=row["team_id"],
        from_subagent_id=row["from_subagent_id"],
        to_subagent_id=row["to_subagent_id"],
        content=row["content"],
        kind=MessageKind(row["kind"]),
        created_at=float(row["created_at"].timestamp()),
    )
