"""TestPlan HTTP router — C2.1 surface for the frontend.

The TestPlan artifact lives in `harness/test_plan.py`:
  - `TestPlan` dataclass (id, run_id, spec_id, repo_url, repo_sha,
    framework, invariants, files, risk, requires_browser, intent_hash,
    created_at)
  - `Invariant` (id, description, target, category, risk)
  - `TestPlanStore` Protocol (save, get_by_id, get_by_intent_hash,
    list_for_spec)
  - `InMemoryTestPlanStore` — the test-friendly adapter

The Postgres adapter is a follow-up (per `test_plan.py:25-28`). For
now the store is wired as a module-level `InMemoryTestPlanStore`
singleton on `app.state.test_plan_store`, mirroring the "one store
per domain" convention used by `settings_store`, `kanban_store`, etc.

Routes:
  POST   /api/test-plans                  — create / upsert a plan
  GET    /api/test-plans/{plan_id}        — fetch by id
  GET    /api/test-plans?intent_hash=...  — cache lookup
  GET    /api/test-plans?spec_id=...      — list for spec
  GET    /api/test-plans                  — list all (admin/debug)
  GET    /api/test-plans/prompt           — load the test-planner role body
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from harness.test_plan import (
    INVARIANT_CATEGORIES,
    RISKS,
    Invariant,
    TestPlan,
    new_invariant_id,
    new_plan_id,
)

router = APIRouter(prefix="/api", tags=["test-plans"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvariantIn(BaseModel):
    id: str | None = None
    description: str
    target: str
    category: str = "happy-path"
    risk: str = "medium"


class TestPlanIn(BaseModel):
    plan_id: str | None = None
    run_id: str = ""
    spec_id: str = ""
    repo_url: str
    repo_sha: str
    framework: str
    invariants: list[InvariantIn] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    risk: str = "medium"
    requires_browser: bool = False


def _invariant_to_dict(inv: Invariant) -> dict[str, Any]:
    return {
        "id": inv.id,
        "description": inv.description,
        "target": inv.target,
        "category": inv.category,
        "risk": inv.risk,
    }


def _plan_to_dict(plan: TestPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "run_id": plan.run_id,
        "spec_id": plan.spec_id,
        "repo_url": plan.repo_url,
        "repo_sha": plan.repo_sha,
        "framework": plan.framework,
        "invariants": [_invariant_to_dict(i) for i in plan.invariants],
        "files": list(plan.files),
        "risk": plan.risk,
        "requires_browser": plan.requires_browser,
        "intent_hash": plan.intent_hash,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def _plan_from_request(body: TestPlanIn) -> TestPlan:
    """Build a TestPlan from a request body, defaulting new ids.

    `plan_id` is reused if provided (idempotent upsert), else a fresh
    uuid. Same for `invariants[].id`. Free-form fields (framework,
    repo_sha) are NOT validated — the agent / planner picks them.
    """
    invariants = [
        Invariant(
            id=inv.id or new_invariant_id(),
            description=inv.description,
            target=inv.target,
            category=inv.category if inv.category in INVARIANT_CATEGORIES else "happy-path",
            risk=inv.risk if inv.risk in RISKS else "medium",
        )
        for inv in body.invariants
    ]
    risk = body.risk if body.risk in RISKS else "medium"
    return TestPlan(
        plan_id=body.plan_id or new_plan_id(),
        run_id=body.run_id,
        spec_id=body.spec_id,
        repo_url=body.repo_url,
        repo_sha=body.repo_sha,
        framework=body.framework,
        invariants=invariants,
        files=list(body.files),
        risk=risk,
        requires_browser=body.requires_browser,
    )


def _store(request: Request):
    """Pull the test-plan store off `app.state`.

    The store is created by the lifespan in `api/main.py` (one
    `InMemoryTestPlanStore` per process). Returns a 503 if the app
    wasn't initialized correctly.
    """
    store = getattr(request.app.state, "test_plan_store", None)
    if store is None:
        raise RuntimeError("TestPlan store not initialized")
    return store


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/test-plans")
async def create_or_upsert_test_plan(request: Request):
    """Save (insert or update) a TestPlan.

    Idempotent on `plan_id`. The store indexes by `plan_id` AND
    `intent_hash`, so subsequent cache lookups by intent will
    short-circuit regeneration.
    """
    try:
        body = TestPlanIn.model_validate(await request.json())
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid TestPlan body: {e}"},
        )
    try:
        plan = _plan_from_request(body)
        await _store(request).save(plan)
        return {"status": "saved", "plan": _plan_to_dict(plan)}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/test-plans/prompt")
async def get_test_planner_prompt_route():
    """Return the test-planner role body.

    The frontend can show this in a "Why is the planner doing X?" view,
    or a kanban card with the role pinned. The body is loaded from
    `.testai/prompts/agents/test-planner.txt` via
    `harness.test_plan.get_test_planner_prompt` — same loader
    convention as the other 25+ role files.

    Registered BEFORE the dynamic `/{plan_id}` route so the literal
    "prompt" path segment is not captured as a plan_id. FastAPI
    matches routes in registration order (first match wins).
    """
    try:
        from harness.test_plan import get_test_planner_prompt
        body = get_test_planner_prompt()
        return {"prompt": body, "chars": len(body)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/test-plans/{plan_id}")
async def get_test_plan_by_id(request: Request, plan_id: str):
    """Fetch a plan by primary key."""
    try:
        plan = await _store(request).get_by_id(plan_id)
        if plan is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"No TestPlan with plan_id={plan_id!r}"},
            )
        return {"plan": _plan_to_dict(plan)}
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/test-plans")
async def list_or_lookup_test_plans(
    request: Request,
    intent_hash: str | None = None,
    spec_id: str | None = None,
    limit: int = 50,
):
    """Three read paths, disambiguated by query params.

    - `?intent_hash=...`  -> cache lookup, single plan
    - `?spec_id=...`      -> list plans attached to a JobSpec (newest first)
    - (neither)           -> list all plans (debug / admin; capped at `limit`)
    """
    try:
        store = _store(request)
        if intent_hash:
            plan = await store.get_by_intent_hash(intent_hash)
            if plan is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"No TestPlan with intent_hash={intent_hash!r}"},
                )
            return {"plan": _plan_to_dict(plan), "match": "intent_hash"}
        if spec_id:
            plans = await store.list_for_spec(spec_id)
            return {
                "spec_id": spec_id,
                "plans": [_plan_to_dict(p) for p in plans],
                "count": len(plans),
            }
        # Fallback: full list (debug). Cap aggressively.
        if hasattr(store, "_by_id"):
            all_plans = list(store._by_id.values())  # type: ignore[attr-defined]
        else:
            all_plans = []
        all_plans.sort(key=lambda p: p.created_at, reverse=True)
        cap = max(1, min(int(limit), 500))
        return {
            "plans": [_plan_to_dict(p) for p in all_plans[:cap]],
            "count": len(all_plans),
            "truncated": len(all_plans) > cap,
        }
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
