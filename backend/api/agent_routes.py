"""Agent execution pipeline — pipeline, delegation, runs, events, sandbox."""

from .routers.agent import router as agent_router
from .routers.pipeline import router as pipeline_router
from .routers.delegate import router as delegate_router
from .routers.recordings import router as recordings_router
from .routers.runs import router as runs_router
from .routers.events import router as events_router
from .routers.sandbox import router as sandbox_router
from .routers.triage_api import router as triage_router
from .routers.jobs import router as jobs_router

# NOTE: `recordings_router` MUST be registered before `runs_router`. The runs
# router owns `GET /sessions/{session_id}` and would otherwise shadow
# `GET /sessions/recordings`, making the recordings list unreachable.

agent_routers = [
    agent_router,
    pipeline_router,
    delegate_router,
    recordings_router,
    runs_router,
    events_router,
    sandbox_router,
    triage_router,
    jobs_router,
]
