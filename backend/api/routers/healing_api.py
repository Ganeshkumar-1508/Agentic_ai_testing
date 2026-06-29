"""Self-healing tests API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/healing", tags=["healing"])
logger = logging.getLogger(__name__)


def _empty_healing_stats() -> dict:
    return {
        "active": False,
        "total": 0,
        "healed": 0,
        "failed": 0,
        "success_rate": 0.0,
        "events": [],
    }


@router.post("/analyze")
async def heal_test(request: Request, test_name: str, error: str, run_id: str = "", locator: str = ""):
    """Analyze a test failure and suggest alternative locators."""
    db = get_db(request)
    try:
        from harness.self_healing import attempt_heal
        result = await attempt_heal(db, test_name, error, run_id, locator)
        return result
    except ModuleNotFoundError:
        return {"status": "unavailable", "healed": False, "confidence": 0.0, "rationale": "self_healing module not installed"}
    except Exception as exc:
        logger.warning("healing analyze unavailable: %s", exc)
        return {"status": "failed", "healed": False, "error": str(exc)[:200]}


@router.get("/stats")
async def get_healing_stats(request: Request):
    """Get self-healing statistics."""
    db = get_db(request)
    try:
        from harness.self_healing import get_healing_stats
        return await get_healing_stats(db)
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        logger.warning("self_healing stats helper unavailable: %s", exc)

    try:
        counts = await db.fetchrow(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN passed = true THEN 1 ELSE 0 END) AS healed, "
            "SUM(CASE WHEN passed = false THEN 1 ELSE 0 END) AS failed "
            "FROM healing_log"
        )
        rows = await db.fetch(
            "SELECT test_name, old_locator, new_locator, confidence, passed, created_at "
            "FROM healing_log ORDER BY created_at DESC LIMIT 20"
        )
        total = (counts or {}).get("total", 0) or 0
        healed = (counts or {}).get("healed", 0) or 0
        failed = (counts or {}).get("failed", 0) or 0
        return {
            "active": total > 0,
            "total": total,
            "healed": healed,
            "failed": failed,
            "success_rate": round((healed / max(total, 1)) * 100, 1),
            "events": [dict(r) for r in rows],
        }
    except Exception as exc:
        logger.warning("healing stats fallback unavailable: %s", exc)
        return _empty_healing_stats()
