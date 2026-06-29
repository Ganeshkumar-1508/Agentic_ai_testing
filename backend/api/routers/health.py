from fastapi import APIRouter, Request

from harness.tools.toolsets import MODES
from ..deps import get_db
from harness.services.health_service import HealthService

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/")
async def root():
    return {"name": "TestAI Harness", "status": "ok", "docs": "/docs"}


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/modes")
async def get_modes():
    return {
        "modes": [
            {"name": name, "description": cfg["description"], "toolsets": cfg["toolsets"]}
            for name, cfg in MODES.items()
        ]
    }


system_router = APIRouter(prefix="/api/system", tags=["system"])


@system_router.get("/health")
async def system_health(request: Request):
    svc = HealthService(get_db(request))
    return await svc.get_system_health()


@system_router.get("/provider-health")
async def provider_health(request: Request):
    """Return per-provider health metrics: circuit breaker state, quality scores, event rings.

    Lets operators monitor provider reliability without grepping logs.
    """
    try:
        from harness.api.state import get_llm
        llm = get_llm()
    except Exception:
        return {"status": "unavailable"}
    if llm is None:
        return {"status": "unavailable"}
    return {
        "circuit_breakers": llm.get_circuit_breakers(),
        "quality": llm.get_provider_health(),
        "events": llm.get_events(limit=20),
        "status": "ok",
    }


@system_router.get("/agent/status")
async def agent_status(request: Request):
    """Return the active agent's runtime metrics for monitoring.

    Surfaces agent loop health: current tool, API call count,
    iteration budget, and last activity description. Returns
    a 200 with status data when the agent exists, 503 when
    not initialized.
    """
    try:
        from harness.api.state import get_agent
        agent = get_agent()
    except Exception:
        return {"status": "unavailable", "agent": None}
    if agent is None:
        return {"status": "unavailable", "agent": None}
    summary = agent.get_activity_summary()
    return {
        "status": "running" if summary.get("current_tool") else "idle",
        "agent": {
            "current_tool": summary.get("current_tool"),
            "api_call_count": summary.get("api_call_count", 0),
            "max_iterations": summary.get("max_iterations", 0),
            "last_activity": summary.get("last_activity_desc", ""),
        },
    }
