"""Curator — background maintenance for agent-created skills.

Tracks skill usage, moves unused skills through active → stale → archived,
and periodically spawns an LLM review to consolidate or patch drift.

Modeled on Hermes' curator pattern:
  - Never touches bundled or hub-installed skills
  - Never auto-deletes (archive is recoverable)
  - Runs on inactivity check, not cron
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from harness.store.adapters.file_system import FileSystem, RealFileSystem

logger = logging.getLogger(__name__)

STALE_AFTER_DAYS = 30
ARCHIVE_AFTER_DAYS = 90
INTERVAL_HOURS = 168  # 7 days
MIN_IDLE_HOURS = 2

_fs: FileSystem = RealFileSystem()


def set_fs(fs: FileSystem) -> None:
    """Override the filesystem adapter (for tests)."""
    global _fs
    _fs = fs


def get_skills_dir() -> Path:
    home = Path(os.environ.get("TESTAI_HOME", Path.home() / ".testai"))
    return home / "skills"


def get_archive_dir() -> Path:
    return get_skills_dir() / ".archive"


def get_usage_path() -> Path:
    return get_skills_dir() / ".usage.json"


def _load_usage() -> dict:
    path = get_usage_path()
    text = _fs.read_text(path)
    if text is not None:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_usage(usage: dict):
    path = get_usage_path()
    _fs.write_text(path, json.dumps(usage, indent=2, default=str))


def track_skill_use(name: str):
    """Record that a skill was used. Called by the skill tool."""
    usage = _load_usage()
    now = datetime.now(timezone.utc).isoformat()
    entry = usage.get(name, {"use_count": 0, "view_count": 0, "created_at": now})
    entry["use_count"] = entry.get("use_count", 0) + 1
    entry["last_used_at"] = now
    usage[name] = entry
    _save_usage(usage)


def track_skill_view(name: str):
    """Record that a skill was viewed."""
    usage = _load_usage()
    now = datetime.now(timezone.utc).isoformat()
    entry = usage.get(name, {"use_count": 0, "view_count": 0, "created_at": now})
    entry["view_count"] = entry.get("view_count", 0) + 1
    entry["last_viewed_at"] = now
    usage[name] = entry
    _save_usage(usage)


async def run_curator(dry_run: bool = False) -> list[dict]:
    """Run one curator pass.

    Returns list of actions taken (or would be taken in dry_run mode).
    """
    actions: list[dict] = []
    skills_dir = get_skills_dir()
    archive_dir = get_archive_dir()
    usage = _load_usage()
    now = datetime.now(timezone.utc)

    if not skills_dir.exists():
        return actions

    # Built-in / bundled skills to never touch
    bundled = {"research", "devops", "autonomous-ai-agents", "creative", "blockchain"}

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        if name.startswith(".") or name in bundled:
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        entry = usage.get(name, {})
        last_used = entry.get("last_used_at")
        last_viewed = entry.get("last_viewed_at")
        last_active = last_used or last_viewed or entry.get("created_at", now.isoformat())

        try:
            last_active_dt = datetime.fromisoformat(last_active)
        except (ValueError, TypeError):
            last_active_dt = now

        days_since_active = (now - last_active_dt).days if last_active_dt.tzinfo else 0

        # Check for archival
        if days_since_active >= ARCHIVE_AFTER_DAYS:
            archive_target = archive_dir / name
            if not dry_run:
                archive_target.mkdir(parents=True, exist_ok=True)
                for f in skill_dir.iterdir():
                    f.rename(archive_target / f.name)
                skill_dir.rmdir()
                logger.info("Archived unused skill: %s (inactive %d days)", name, days_since_active)
            actions.append({"action": "archived", "skill": name, "days_inactive": days_since_active})
            continue

        # Check for staleness
        if days_since_active >= STALE_AFTER_DAYS:
            if not dry_run:
                entry["state"] = "stale"
                logger.info("Marked skill as stale: %s (inactive %d days)", name, days_since_active)
            actions.append({"action": "stale", "skill": name, "days_inactive": days_since_active})

    _save_usage(usage)
    return actions


def should_run() -> bool:
    """Check if enough time has passed since the last curator run."""
    usage = _load_usage()
    last_run = usage.get("_curator_last_run")
    if not last_run:
        return False  # First run seeds last_run_at, defers by one interval

    try:
        last = datetime.fromisoformat(last_run) if isinstance(last_run, str) else datetime.fromisoformat(str(last_run))
        elapsed_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return elapsed_hours >= INTERVAL_HOURS
    except (ValueError, TypeError):
        return True


def mark_run_completed():
    """Record that a curator run completed."""
    usage = _load_usage()
    usage["_curator_last_run"] = datetime.now(timezone.utc).isoformat()
    _save_usage(usage)


# ---------------------------------------------------------------------------
# Phase-8 additions: module-level path constants, async API, and a JSON
# sidecar for the curator's last-run timestamp + archived-skill history.
# These are the symbols imported by `api/main.py`, `api/routers/curator_api.py`
# and `api/routers/ops.py` — they previously did not exist, breaking FastAPI
# startup with ImportError.
# ---------------------------------------------------------------------------

# Pathlib-style module-level constants used by the API routers.
SKILLS_DIR: Path = get_skills_dir()
ARCHIVE_DIR: Path = get_archive_dir()


def _state_file() -> Path:
    """JSON sidecar that persists curator state across runs.

    Lives next to the usage file so the entire curator state (usage,
    last-run, archive history) stays in one directory.
    """
    return get_usage_path().parent / ".curator_state.json"


def _load_state() -> dict:
    """Read the curator state sidecar.  Returns ``{}`` if missing or corrupt."""
    path = _state_file()
    text = _fs.read_text(path)
    if text is not None:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict) -> None:
    """Persist the curator state sidecar (atomic write)."""
    path = _state_file()
    _fs.atomic_write(path, json.dumps(state, indent=2, default=str))


def _read_curator_state() -> dict:
    """Public accessor for the state sidecar (used by ``/api/curator/status``)."""
    return _load_state()


async def maybe_run_curator(db=None) -> dict:
    """Async entry-point used by background loops and the ops router."""
    actions = await run_curator()
    archived = [a for a in actions if a.get("action") == "archived"]
    stale = [a for a in actions if a.get("action") == "stale"]
    return {"archived": archived, "stale": stale, "all": actions}


# ---------------------------------------------------------------------------
# L2 Evolution Loop — SkillClaw-inspired: scrape → summarize → publish
# ---------------------------------------------------------------------------

EVOLUTION_INTERVAL_HOURS = 1  # how often the evolution loop runs
EVOLUTION_SKILLS_DIR = get_skills_dir()


async def run_evolution(db, llm=None) -> list[dict]:
    """L2 Curator — scrape completed kanban tasks, extract reusable patterns,
    publish as skills. SkillClaw-inspired workflow engine.

    Args:
        db: Database connection.
        llm: Configured LLMRouter instance. If None, fetches provider settings
             from the DB and configures a fresh router.
    """
    if not db:
        logger.warning("Evolution: no DB connection")
        return []

    if llm is None:
        # Try to use the shared LLM router first
        from harness.api.state import get_llm
        llm = get_llm()
        if llm is None:
            from harness.llm import LLMRouter
            llm = LLMRouter()
            try:
                from harness.memory.settings_store import SettingsStore
                store = SettingsStore(db)
                providers = await store.get_all_providers()
                if providers:
                    llm.configure(providers)
            except Exception:
                pass

    evolved = []

    # 1. SCRAPE: find completed tasks with structured metadata
    try:
        rows = await db.fetch(
            """SELECT id, title, description, result_summary, tags, created_at
               FROM kanban_tasks
               WHERE column_name = 'done'
                 AND result_summary != ''
                 AND (result_summary LIKE '%changed_files%'
                      OR result_summary LIKE '%verification%'
                      OR result_summary LIKE '%tests_run%')
                 AND updated_at > NOW() - INTERVAL '7 days'
               ORDER BY created_at DESC
               LIMIT 20"""
        )
    except Exception as e:
        logger.warning("Evolution scrape failed: %s", e)
        return []

    if not rows:
        logger.debug("Evolution: no candidate tasks found")
        return []

    for row in rows:
        try:
            summary = row["result_summary"] or ""
            tags = (row["tags"] or "").lower()

            # 2. SUMMARIZE: LLM extracts the pattern
            from harness.llm import ChatMessage
            prompt = (
                "You are a skill evolution engine. Extract a reusable "
                "skill pattern from this completed task. Return ONLY a "
                "JSON object with fields:\n"
                "  name: short skill name (snake_case, 2-4 words)\n"
                "  description: one-line what this skill does\n"
                "  category: 'fix' | 'test' | 'review' | 'setup'\n"
                "  instructions: 3-5 bullet points as a numbered list\n\n"
                f"Task title: {row['title']}\n"
                f"Task description: {row['description'] or 'N/A'}\n"
                f"Task result: {summary[:1000]}\n"
                f"Tags: {tags}\n\n"
                "Return ONLY valid JSON. No explanation."
            )
            response = await llm.chat([ChatMessage(role="user", content=prompt)])
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip().removeprefix("```json").removesuffix("```").strip()

            import json as _json
            parsed = _json.loads(text)
            skill_name = parsed.get("name", "").strip().lower().replace(" ", "_")[:60]
            if not skill_name:
                continue

            # 3. AGGREGATE: check if skill already exists
            skill_path = EVOLUTION_SKILLS_DIR / skill_name / "SKILL.md"
            instructions = parsed.get("instructions", "")
            category = parsed.get("category", "fix")
            description = parsed.get("description", "")[:200]

            if skill_path.exists():
                logger.debug("Skill '%s' already exists, skipping", skill_name)
                continue

            # 4. PUBLISH: write SKILL.md
            skill_content = (
                f"# {skill_name}\n\n"
                f"**Description:** {description}\n"
                f"**Category:** {category}\n"
                f"**Auto-generated from:** {row['title']}\n\n"
                f"## Instructions\n\n{instructions}\n"
            )
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(skill_content, encoding="utf-8")

            # Update skills_index table
            try:
                await db.execute(
                    """INSERT INTO skills_index (name, description, path, source, category, tags)
                       VALUES ($1,$2,$3,$4,$5,$6)
                       ON CONFLICT (name) DO NOTHING""",
                    skill_name, description, str(skill_path),
                    "curator", category, f"evolved,{category}",
                )
            except Exception:
                pass

            evolved.append({"name": skill_name, "category": category})
            logger.info("Evolved new skill: %s (%s)", skill_name, category)

        except Exception as e:
            logger.debug("Evolution skipped task %s: %s", row.get("id", "?"), e)
            continue

    return evolved


async def run_curator_review(db=None) -> dict:
    """Explicit "review" pass — same engine as :func:`maybe_run_curator`.

    Named differently to give ops/UI code a clear semantic call-site; the
    underlying work is identical for now.  A future revision will let
    review-mode do LLM-assisted consolidation while maybe-run stays as a
    pure housekeeping pass.
    """
    return await maybe_run_curator(db=db)
