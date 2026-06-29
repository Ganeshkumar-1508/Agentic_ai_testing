"""API routes for multi-repo coordination.

Provides endpoints to initiate and query cross-repo change operations
outside of the pipeline flow.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cross-repo", tags=["cross-repo"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RepoConfigRequest(BaseModel):
    """A single repository configuration for a cross-repo operation."""
    url: str
    token: str | None = None
    branch: str = "main"
    dependencies: list[str] = []


class CrossRepoExecuteRequest(BaseModel):
    """Request body for executing a coordinated multi-repo change."""
    repos: list[RepoConfigRequest]
    requirements: str
    token: str | None = None  # Default token applied to all repos


class CrossRepoStatusResponse(BaseModel):
    """Status response for a cross-repo operation."""
    change_id: str
    status: str
    repo_changes: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# In-memory store for cross-repo operations (MVP)
# ---------------------------------------------------------------------------

_cross_repo_store: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/execute")
async def execute_cross_repo(request: Request, body: CrossRepoExecuteRequest):
    """Execute a coordinated change across multiple repositories.

    Creates a CrossRepoChange and runs the MultiRepoCoordinator.
    Returns immediately with a change_id for status polling.
    """
    from harness.cross_repo import CrossRepoChange, RepoChange, RepoConfig
    from harness.multi_repo_coordinator import MultiRepoCoordinator

    if not body.repos or len(body.repos) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "At least 2 repos are required for cross-repo operations"},
        )

    # Apply default token to any repo without its own token
    if body.token:
        for r in body.repos:
            if not r.token:
                r.token = body.token

    change_id = f"testai-crc-{int(time.time())}"

    # Build RepoConfig from request
    repo_configs = [
        RepoConfig(
            url=r.url,
            token=r.token,
            branch=r.branch,
            dependencies=r.dependencies,
        )
        for r in body.repos
    ]

    crc = CrossRepoChange(
        id=change_id,
        description=body.requirements,
        repo_changes=[RepoChange(repo=rc) for rc in repo_configs],
    )

    # Store for status polling
    _cross_repo_store[change_id] = crc

    # Execute in background if agent available
    agent_factory = getattr(request.app.state, "agent_factory", None)
    if agent_factory:
        coordinator = MultiRepoCoordinator(crc)
        import asyncio
        asyncio.create_task(
            coordinator.execute(agent_factory=agent_factory),
            name=f"cross-repo-exec-{change_id}",
        )

    return {
        "change_id": change_id,
        "status": "started",
        "repos": [r.url for r in body.repos],
        "dependency_order": [rc.repo.url for rc in crc.dependency_order],
        "status_endpoint": f"/api/cross-repo/status/{change_id}",
    }


@router.get("/status/{change_id}")
async def get_cross_repo_status(change_id: str):
    """Get status of a cross-repo change operation.

    Returns the current state of all repo changes, including
    PR URLs and any errors.
    """
    crc = _cross_repo_store.get(change_id)
    if crc is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Cross-repo change {change_id} not found"},
        )

    return crc.to_dict()


@router.get("/list")
async def list_cross_repo_changes():
    """List all recent cross-repo change operations."""
    return {
        "changes": [
            {
                "id": crc.id,
                "status": crc.status,
                "description": crc.description[:100],
                "repo_count": len(crc.repo_changes),
                "created_at": crc.created_at,
            }
            for crc in _cross_repo_store.values()
        ]
    }
