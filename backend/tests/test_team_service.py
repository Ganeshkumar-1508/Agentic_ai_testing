"""Tests for C02: TeamService — Postgres-backed team coordination.

C02 (per docs/2026-06-21-architecture-decision-tree.md#c02) tests
the data layer (TeamService) end-to-end via a mock DB. The mock
captures SQL calls + provides a tiny in-memory table so we can
exercise the full lifecycle: create → add member → send messages
→ mark member done → auto-dissolve.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.services.team_service import (
    MemberNotFoundError,
    MemberRole,
    MemberStatus,
    MessageKind,
    TeamDissolvedError,
    TeamMember,
    TeamMessage,
    TeamNotFoundError,
    TeamService,
    TeamStatus,
    validate_team_name,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# In-memory DB mock
# ---------------------------------------------------------------------------


class _FakeDB:
    """In-memory DB that supports the TeamService operations.

    Implements the subset of Database that TeamService needs:
    ``fetchrow``, ``fetch``, ``execute``. Stores rows in plain
    dicts keyed by table name.
    """

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            "teams": [],
            "team_members": [],
            "team_messages": [],
        }
        self._next_message_id = 1

    async def execute(self, sql: str, *args: Any) -> None:
        # Very small SQL parser — just enough to dispatch on the
        # verbs TeamService uses. NB: "insert into teams" must be
        # checked AFTER "insert into team_members" because the
        # latter starts with "insert into team" (shorter prefix).
        s = sql.strip().lower()
        if s.startswith("insert into team_members"):
            # Two shapes:
            #   - "add_member": 4 params (team_id, subagent_id,
            #     role, role_name) — role + role_name are $N
            #   - "create_team lead": 2 params (team_id,
            #     subagent_id) — role + role_name are hardcoded
            #     as SQL literals
            if len(args) >= 4:
                team_id, subagent_id, role, role_name = args[0], args[1], args[2], args[3]
            else:
                team_id, subagent_id = args[0], args[1]
                role = "lead"
                role_name = ""
            self._upsert_member(team_id, subagent_id, role, role_name)
            return
        if s.startswith("insert into team_messages"):
            # Two shapes:
            #   - "send_message": 5 params (team_id, from, to,
            #     content, kind)
            #   - "_post_system_message": 2 params (team_id,
            #     content) — from/to/kind are SQL literals
            if len(args) >= 4:
                team_id = args[0]
                from_sa = args[1]
                to_sa = args[2]
                content = args[3]
                kind = args[4] if len(args) >= 5 else "message"
            else:
                team_id = args[0]
                content = args[1]
                from_sa = None
                to_sa = None
                kind = "system"
            mid = self._next_message_id
            self._next_message_id += 1
            self._tables["team_messages"].append({
                "id": mid,
                "team_id": team_id,
                "from_subagent_id": from_sa,
                "to_subagent_id": to_sa,
                "content": content,
                "kind": kind,
                "created_at": _Now(),
            })
            return
        if s.startswith("insert into teams"):
            self._tables["teams"].append({
                "team_id": args[0],
                "name": args[1],
                "lead_subagent_id": args[2],
                "lead_session_id": args[3],
                "goal": args[4] or "",
                "status": "active",
                "created_at": _Now(),
                "dissolved_at": None,
                "config": _Json.loads(args[5]) if args[5] else {},
            })
            return
        if s.startswith("update team_members"):
            if "left_at is null" in s and "returning" not in s:
                # The "dissolve all" form: only team_id is bound.
                if len(args) == 1:
                    team_id = args[0]
                    for m in self._tables["team_members"]:
                        if m["team_id"] == team_id and m["left_at"] is None:
                            m["status"] = "done"
                            m["left_at"] = _Now()
                    return
                # The "remove one member" form (with RETURNING).
                if len(args) >= 2:
                    team_id, subagent_id = args[0], args[1]
                    for m in self._tables["team_members"]:
                        if m["team_id"] == team_id and m["subagent_id"] == subagent_id and m["left_at"] is None:
                            m["status"] = "done"
                            m["left_at"] = _Now()
                            return
                return
            # Generic status update
            status, team_id, subagent_id = args
            for m in self._tables["team_members"]:
                if m["team_id"] == team_id and m["subagent_id"] == subagent_id:
                    m["status"] = status
                    return
            return
        if s.startswith("update teams set status = 'dissolved'"):
            team_id = args[0]
            for t in self._tables["teams"]:
                if t["team_id"] == team_id:
                    t["status"] = "dissolved"
                    t["dissolved_at"] = _Now()
                    return
            return
        # Unhandled SQL — fail loudly in tests.
        raise NotImplementedError(f"FakeDB.execute: {sql!r}")

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        s = sql.strip().lower()
        if s.startswith("insert into team_messages") and "returning" in s:
            # INSERT ... RETURNING — needs to return the new id + ts.
            team_id = args[0]
            from_sa = args[1]
            to_sa = args[2]
            content = args[3]
            kind = args[4] if len(args) >= 5 else "message"
            mid = self._next_message_id
            self._next_message_id += 1
            now = _Now()
            self._tables["team_messages"].append({
                "id": mid,
                "team_id": team_id,
                "from_subagent_id": from_sa,
                "to_subagent_id": to_sa,
                "content": content,
                "kind": kind,
                "created_at": now,
            })
            return {"id": mid, "created_at": now}
        if s.startswith("select") and "from teams" in s and "team_id = $1" in s:
            team_id = args[0]
            for t in self._tables["teams"]:
                if t["team_id"] == team_id:
                    # ``get_team`` filters by status='active';
                    # ``get_team_including_dissolved`` does not.
                    if "status = 'active'" in s and t["status"] != "active":
                        continue
                    return dict(t)
            return None
        if s.startswith("select") and "from team_members" in s and "limit 1" in s:
            team_id, subagent_id = args
            for m in self._tables["team_members"]:
                if m["team_id"] == team_id and m["subagent_id"] == subagent_id:
                    return {"ok": 1}
            return None
        if s.startswith("select") and "from team_members" in s and "team_id = $1" in s and "subagent_id = $2" in s:
            team_id, subagent_id = args
            for m in self._tables["team_members"]:
                if m["team_id"] == team_id and m["subagent_id"] == subagent_id:
                    return dict(m)
            return None
        if s.startswith("select max(created_at)"):
            # Member progress query.
            team_id, subagent_id = args
            latest = None
            for msg in self._tables["team_messages"]:
                if msg["team_id"] != team_id:
                    continue
                if (
                    msg["from_subagent_id"] == subagent_id
                    or msg["to_subagent_id"] == subagent_id
                    or (msg["to_subagent_id"] is None and msg["from_subagent_id"] is not None)
                ):
                    if latest is None or msg["created_at"].ts > latest.ts:
                        latest = msg["created_at"]
            return {"last_msg_at": latest} if latest else {"last_msg_at": None}
        if s.startswith("update team_members") and "returning" in s:
            team_id, subagent_id = args
            for m in self._tables["team_members"]:
                if m["team_id"] == team_id and m["subagent_id"] == subagent_id and m["left_at"] is None:
                    m["status"] = "done"
                    m["left_at"] = _Now()
                    return {"subagent_id": subagent_id}
            return None
        raise NotImplementedError(f"FakeDB.fetchrow: {sql!r}")

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        s = sql.strip().lower()
        if "from team_messages" in s:
            return self._select_messages(s, args)
        if "from team_members" in s:
            return self._select_members(s, args)
        if "from teams" in s and "team_members" not in s:
            return self._select_teams(s, args)
        if "select t.team_id" in s and "team_members" in s:
            # cleanup_completed aggregate.
            return self._select_cleanup()
        raise NotImplementedError(f"FakeDB.fetch: {sql!r}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upsert_member(self, team_id: str, subagent_id: str, role: str, role_name: str) -> None:
        # Idempotent insert (ON CONFLICT DO UPDATE).
        for m in self._tables["team_members"]:
            if m["team_id"] == team_id and m["subagent_id"] == subagent_id:
                m["role"] = role
                m["role_name"] = role_name
                m["status"] = "active"
                m["left_at"] = None
                return
        self._tables["team_members"].append({
            "team_id": team_id,
            "subagent_id": subagent_id,
            "role": role,
            "role_name": role_name,
            "status": "active",
            "joined_at": _Now(),
            "left_at": None,
        })

    def _select_messages(self, sql: str, args: tuple) -> list[dict[str, Any]]:
        # Two query shapes:
        #   WHERE team_id=$1 AND id>$2 AND (to_subagent_id IS NULL OR to_subagent_id=$3 OR from_subagent_id=$3) ORDER BY id LIMIT $4
        #   WHERE team_id=$1 AND id>$2 ORDER BY id LIMIT $3
        if "to_subagent_id is null" in sql or "to_subagent_id is null or" in sql:
            team_id, since_id, subagent_id, limit = args
            results = [
                dict(m) for m in self._tables["team_messages"]
                if m["team_id"] == team_id
                and int(m["id"]) > int(since_id)
                and (m["to_subagent_id"] is None
                     or m["to_subagent_id"] == subagent_id
                     or m["from_subagent_id"] == subagent_id)
            ]
        else:
            team_id, since_id, limit = args
            results = [
                dict(m) for m in self._tables["team_messages"]
                if m["team_id"] == team_id and int(m["id"]) > int(since_id)
            ]
        results.sort(key=lambda r: r["id"])
        return results[:limit]

    def _select_members(self, sql: str, args: tuple) -> list[dict[str, Any]]:
        team_id = args[0]
        return [dict(m) for m in self._tables["team_members"] if m["team_id"] == team_id]

    def _select_teams(self, sql: str, args: tuple) -> list[dict[str, Any]]:
        # list_teams — apply filters
        where: list[Any] = []
        limit = 100
        i = 0
        if "status = $" in sql:
            where.append(("status", args[i]))
            i += 1
        if "lead_session_id = $" in sql:
            where.append(("lead_session_id", args[i]))
            i += 1
        if i < len(args):
            try:
                limit = int(args[i])
            except (TypeError, ValueError):
                pass
        results = []
        for t in self._tables["teams"]:
            if all(t.get(k) == v for k, v in where):
                results.append(dict(t))
        results.sort(key=lambda r: r["created_at"].ts, reverse=True)
        return results[:limit]

    def _select_cleanup(self) -> list[dict[str, Any]]:
        # Return teams with no active members.
        out = []
        team_ids = {t["team_id"] for t in self._tables["teams"] if t["status"] == "active"}
        for tid in team_ids:
            members = [m for m in self._tables["team_members"] if m["team_id"] == tid]
            active = [m for m in members if m["status"] == "active"]
            if len(members) > 0 and len(active) == 0:
                out.append({
                    "team_id": tid,
                    "active_members": 0,
                    "total_members": len(members),
                })
        return out


class _Now:
    """A wall-clock-now stand-in that returns a stable timestamp."""
    ts: float = 0.0

    def __init__(self) -> None:
        _Now.ts += 1.0  # monotonic per-_Now
        self.ts = _Now.ts

    def timestamp(self) -> float:
        return self.ts


class _Json:
    """Stand-in for json that round-trips."""
    @staticmethod
    def loads(s: Any) -> Any:
        import json
        if isinstance(s, (dict, list)):
            return s
        return json.loads(s) if s else {}


@pytest.fixture
def db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture
def service(db: _FakeDB) -> TeamService:
    return TeamService(db)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_team_name_accepts_simple() -> None:
    assert validate_team_name("Fix squad") == "Fix squad"
    assert validate_team_name("Q3-2026") == "Q3-2026"
    assert validate_team_name("build_test.team") == "build_test.team"


def test_validate_team_name_strips_whitespace() -> None:
    assert validate_team_name("  hello  ") == "hello"


def test_validate_team_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_team_name("")
    with pytest.raises(ValueError, match="must not be empty"):
        validate_team_name("   ")


def test_validate_team_name_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="100 characters"):
        validate_team_name("a" * 101)


def test_validate_team_name_rejects_disallowed_chars() -> None:
    with pytest.raises(ValueError, match="only letters"):
        validate_team_name("hello!world")
    with pytest.raises(ValueError, match="only letters"):
        validate_team_name("foo/bar")


# ---------------------------------------------------------------------------
# create_team
# ---------------------------------------------------------------------------


async def test_create_team_returns_active_team(service: TeamService) -> None:
    team = await service.create_team(
        "Sprint 7", lead_subagent_id="sa-lead", goal="ship the feature",
    )
    assert team.name == "Sprint 7"
    assert team.lead_subagent_id == "sa-lead"
    assert team.goal == "ship the feature"
    assert team.status == TeamStatus.ACTIVE
    assert team.dissolved_at is None
    # The lead is auto-added as a member.
    members = await service.list_members(team.team_id)
    assert len(members) == 1
    assert members[0].role == MemberRole.LEAD


async def test_create_team_with_config(service: TeamService) -> None:
    team = await service.create_team(
        "x", lead_subagent_id="sa", config={"key": "value"},
    )
    assert team.config == {"key": "value"}


async def test_create_team_unique_ids(service: TeamService) -> None:
    a = await service.create_team("a", lead_subagent_id="sa1")
    b = await service.create_team("b", lead_subagent_id="sa2")
    assert a.team_id != b.team_id
    assert a.team_id.startswith("team-")


# ---------------------------------------------------------------------------
# get_team / list_teams
# ---------------------------------------------------------------------------


async def test_get_team_returns_it(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa")
    got = await service.get_team(t.team_id)
    assert got.team_id == t.team_id


async def test_get_team_missing_raises(service: TeamService) -> None:
    with pytest.raises(TeamNotFoundError):
        await service.get_team("team-doesnt-exist")


async def test_get_team_excludes_dissolved(service: TeamService) -> None:
    """Dissolved teams are not returned by get_team (use the
    ``_including_dissolved`` variant for history)."""
    t = await service.create_team("x", lead_subagent_id="sa")
    await service.dissolve(t.team_id)
    with pytest.raises(TeamNotFoundError):
        await service.get_team(t.team_id)


async def test_get_team_including_dissolved_returns_dissolved(
    service: TeamService,
) -> None:
    t = await service.create_team("x", lead_subagent_id="sa")
    await service.dissolve(t.team_id)
    got = await service.get_team_including_dissolved(t.team_id)
    assert got.status == TeamStatus.DISSOLVED


async def test_list_teams_filters_by_status(service: TeamService) -> None:
    a = await service.create_team("a", lead_subagent_id="sa1")
    b = await service.create_team("b", lead_subagent_id="sa2")
    await service.dissolve(b.team_id)
    actives = await service.list_teams(status=TeamStatus.ACTIVE)
    assert {t.team_id for t in actives} == {a.team_id}


# ---------------------------------------------------------------------------
# add_member / remove_member
# ---------------------------------------------------------------------------


async def test_add_member(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    m = await service.add_member(t.team_id, "sa-mem", role_name="fix")
    assert m.role == MemberRole.MEMBER
    assert m.role_name == "fix"
    members = await service.list_members(t.team_id)
    assert len(members) == 2  # lead + new member


async def test_add_member_is_idempotent(service: TeamService) -> None:
    """Re-adding a member updates role_name (and re-activates)."""
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem", role_name="fix")
    await service.add_member(t.team_id, "sa-mem", role_name="verify")
    members = await service.list_members(t.team_id)
    assert len(members) == 2  # lead + one member, not duplicated
    assert any(m.role_name == "verify" for m in members)


async def test_remove_member_marks_done(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    ok = await service.remove_member(t.team_id, "sa-mem")
    assert ok is True
    m = await service.get_member(t.team_id, "sa-mem")
    assert m.status == MemberStatus.DONE


async def test_remove_member_returns_false_when_absent(
    service: TeamService,
) -> None:
    t = await service.create_team("x", lead_subagent_id="sa")
    ok = await service.remove_member(t.team_id, "never-joined")
    assert ok is False


async def test_get_member_missing_raises(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa")
    with pytest.raises(MemberNotFoundError):
        await service.get_member(t.team_id, "sa-not-here")


# ---------------------------------------------------------------------------
# send_message / list_messages
# ---------------------------------------------------------------------------


async def test_send_message_broadcast(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    msg = await service.send_message(
        t.team_id, "sa-lead", None, "hello team",
    )
    assert msg.to_subagent_id is None
    assert msg.from_subagent_id == "sa-lead"
    assert msg.content == "hello team"
    assert msg.kind == MessageKind.MESSAGE


async def test_send_message_directed(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    msg = await service.send_message(
        t.team_id, "sa-lead", "sa-mem", "private question",
    )
    assert msg.to_subagent_id == "sa-mem"


async def test_send_message_rejects_non_member_sender(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    with pytest.raises(MemberNotFoundError):
        await service.send_message(
            t.team_id, "sa-outsider", None, "hello",
        )


async def test_send_message_rejects_non_member_recipient(
    service: TeamService,
) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    with pytest.raises(MemberNotFoundError):
        await service.send_message(
            t.team_id, "sa-lead", "sa-outsider", "private",
        )


async def test_send_message_truncates_long_content(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    long = "x" * 20_000
    msg = await service.send_message(t.team_id, "sa-lead", None, long)
    assert len(msg.content) <= 10_001  # 10K + ellipsis
    assert msg.content.endswith("…")


async def test_list_messages_returns_all_for_lead(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    await service.send_message(t.team_id, "sa-lead", None, "broadcast")
    await service.send_message(t.team_id, "sa-lead", "sa-mem", "private")
    msgs = await service.list_messages(t.team_id, for_subagent_id=None)
    assert len(msgs) == 2


async def test_list_messages_filters_by_recipient(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    await service.send_message(t.team_id, "sa-lead", None, "broadcast")
    await service.send_message(t.team_id, "sa-lead", "sa-mem", "to mem")
    await service.send_message(t.team_id, "sa-lead", "sa-lead", "self note")
    # Member view: broadcasts + messages addressed to them, plus
    # their own outbound messages.
    msgs = await service.list_messages(t.team_id, for_subagent_id="sa-mem")
    assert {m.content for m in msgs} == {"broadcast", "to mem"}


async def test_list_messages_since_id(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.send_message(t.team_id, "sa-lead", None, "first")
    await service.send_message(t.team_id, "sa-lead", None, "second")
    msgs = await service.list_messages(t.team_id, since_id=1)
    assert len(msgs) == 1
    assert msgs[0].content == "second"


# ---------------------------------------------------------------------------
# dissolve
# ---------------------------------------------------------------------------


async def test_dissolve_sets_status_and_marks_members(
    service: TeamService,
) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    newly = await service.dissolve(t.team_id)
    assert newly is True
    members = await service.list_members(t.team_id) if False else None
    # list_members filters by status implicitly? No, it returns all
    # rows for the team. We check via get_member.
    lead = await service.get_member(t.team_id, "sa-lead")
    mem = await service.get_member(t.team_id, "sa-mem")
    assert lead.status == MemberStatus.DONE
    assert mem.status == MemberStatus.DONE
    # System message posted.
    msgs = await service.list_messages(t.team_id)
    assert any(m.kind == MessageKind.SYSTEM for m in msgs)


async def test_dissolve_is_idempotent(service: TeamService) -> None:
    t = await service.create_team("x", lead_subagent_id="sa")
    assert (await service.dissolve(t.team_id)) is True
    assert (await service.dissolve(t.team_id)) is False


async def test_dissolve_missing_raises(service: TeamService) -> None:
    with pytest.raises(TeamNotFoundError):
        await service.dissolve("team-missing")


# ---------------------------------------------------------------------------
# cleanup_completed (Q5: auto-dissolve)
# ---------------------------------------------------------------------------


async def test_cleanup_dissolves_teams_with_all_done_members(
    service: TeamService,
) -> None:
    """Per Q5: a team where every member is ``done`` is auto-dissolved."""
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    # Mark the lead + member as done.
    await service.update_member_status(t.team_id, "sa-lead", MemberStatus.DONE)
    await service.update_member_status(t.team_id, "sa-mem", MemberStatus.DONE)
    dissolved = await service.cleanup_completed()
    assert t.team_id in dissolved
    # Team is now dissolved.
    with pytest.raises(TeamNotFoundError):
        await service.get_team(t.team_id)


async def test_cleanup_does_not_dissolve_active_teams(
    service: TeamService,
) -> None:
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    # Lead is still active.
    dissolved = await service.cleanup_completed()
    assert dissolved == []


async def test_cleanup_does_not_dissolve_with_mixed_status(
    service: TeamService,
) -> None:
    """A team with one done and one active member is NOT dissolved."""
    t = await service.create_team("x", lead_subagent_id="sa-lead")
    await service.add_member(t.team_id, "sa-mem")
    await service.update_member_status(t.team_id, "sa-lead", MemberStatus.DONE)
    dissolved = await service.cleanup_completed()
    assert dissolved == []


# ---------------------------------------------------------------------------
# Roundtrip / lifecycle smoke
# ---------------------------------------------------------------------------


async def test_full_lifecycle_roundtrip(service: TeamService) -> None:
    """End-to-end: create → add members → exchange messages →
    mark members done → cleanup → dissolved.
    """
    t = await service.create_team(
        "Sprint", lead_subagent_id="sa-lead", goal="ship the bug fix",
    )
    await service.add_member(t.team_id, "sa-fix", role_name="fix")
    await service.add_member(t.team_id, "sa-test", role_name="verify")

    # Roundtrip messages.
    await service.send_message(t.team_id, "sa-lead", None, "begin work")
    await service.send_message(t.team_id, "sa-fix", "sa-lead", "on it")
    await service.send_message(t.team_id, "sa-test", "sa-lead", "ready to verify")
    await service.send_message(t.team_id, "sa-lead", None, "go team")

    # Mark everyone done.
    await service.update_member_status(t.team_id, "sa-lead", MemberStatus.DONE)
    await service.update_member_status(t.team_id, "sa-fix", MemberStatus.DONE)
    await service.update_member_status(t.team_id, "sa-test", MemberStatus.DONE)

    # Auto-dissolve.
    dissolved = await service.cleanup_completed()
    assert t.team_id in dissolved

    # History still readable.
    hist = await service.get_team_including_dissolved(t.team_id)
    assert hist.status == TeamStatus.DISSOLVED
    assert hist.dissolved_at is not None

    # All messages preserved (4 user messages + 1 system message
    # from the auto-dissolve).
    msgs = await service.list_messages(t.team_id, for_subagent_id=None)
    user_msgs = [m for m in msgs if m.kind == MessageKind.MESSAGE]
    system_msgs = [m for m in msgs if m.kind == MessageKind.SYSTEM]
    assert len(user_msgs) == 4
    assert len(system_msgs) == 1
