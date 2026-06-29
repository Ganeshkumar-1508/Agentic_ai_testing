"""Curator API — skill lifecycle management."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/curator", tags=["curator"])


@router.post("/run")
async def run_curator(request: Request):
    """Manually trigger a curator review pass."""
    db = get_db(request)
    from harness.curator import run_curator_review
    report = await run_curator_review(db)
    return report


@router.get("/status")
async def curator_status(request: Request):
    """Get curator status: last run, skill counts by category."""
    db = get_db(request)
    from harness.curator import _read_curator_state

    last_run = _read_curator_state()
    counts = {"active": 0, "archived": 0, "pinned": 0, "agent_created": 0}

    try:
        rows = await db.fetch(
            "SELECT category, COUNT(*) as cnt, created_by FROM skills_index GROUP BY category, created_by"
        )
        for r in rows:
            cat = r["category"] or "active"
            counts[cat] = counts.get(cat, 0) + r["cnt"]
            if r["created_by"] == "agent":
                counts["agent_created"] += r["cnt"]
    except Exception:
        pass

    return {
        "last_run_at": last_run,
        "skill_counts": counts,
    }


@router.post("/pin/{skill_name}")
async def pin_skill(skill_name: str, request: Request):
    """Pin a skill to prevent auto-archiving."""
    db = get_db(request)
    await db.execute("UPDATE skills_index SET category = 'pinned', updated_at = NOW() WHERE name = $1", skill_name)
    return {"status": "pinned", "name": skill_name}


@router.post("/unpin/{skill_name}")
async def unpin_skill(skill_name: str, request: Request):
    """Unpin a skill, returning it to normal lifecycle."""
    db = get_db(request)
    await db.execute("UPDATE skills_index SET category = 'active', updated_at = NOW() WHERE name = $1", skill_name)
    return {"status": "unpinned", "name": skill_name}


@router.post("/restore/{skill_name}")
async def restore_skill(skill_name: str, request: Request):
    """Restore an archived skill back to active."""
    db = get_db(request)
    from pathlib import Path
    from harness.curator import SKILLS_DIR, ARCHIVE_DIR

    archived_path = ARCHIVE_DIR / skill_name
    restored_path = SKILLS_DIR / skill_name

    if archived_path.exists():
        import shutil
        restored_path.mkdir(parents=True, exist_ok=True)
        for item in archived_path.iterdir():
            shutil.move(str(item), str(restored_path))
        shutil.rmtree(str(archived_path))

    await db.execute(
        "UPDATE skills_index SET category = 'active', path = $1, updated_at = NOW() WHERE name = $2",
        str(restored_path), skill_name,
    )
    return {"status": "restored", "name": skill_name}
