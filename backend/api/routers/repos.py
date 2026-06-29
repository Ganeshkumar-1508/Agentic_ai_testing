"""Repo summary endpoint.

``POST /api/repos/{owner}/{repo}/summarize`` — returns a quick
overview of a repo's structure (file counts, languages, entry
points, framework hints, README/LICENSE presence, test dirs).

The endpoint is **read-only** and only summarizes repos that are
already cached on disk. It does NOT clone new repos. The chat
LLM uses this for a quick check before deciding whether to
``submit_job`` for a deeper analysis.

Cache locations probed (in order):
  1. ``$AGENT_WORKSPACE_MOUNT/{owner}/{repo}``
  2. ``$AGENT_WORKSPACE_MOUNT/{owner}_{repo}``
  3. ``$AGENT_WORKSPACE_MOUNT/{owner}-{repo}``
  4. ``$AGENT_WORKSPACE_MOUNT/repos/{owner}/{repo}``

If no cached repo is found, the endpoint returns 404 with a
``hint`` field explaining how to clone the repo (via ``submit_job``
or a manual ``git clone`` into the workspace).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/repos", tags=["repos"])


class RepoSummaryResponse(BaseModel):
    owner: str
    repo: str
    path: str
    total_files: int
    total_size_bytes: int
    languages: dict[str, int]
    entry_points: list[str]
    frameworks: list[str]
    manifests: list[str]
    has_readme: bool
    has_license: bool
    test_dirs: list[str]


def _agent_workspace() -> str:
    return os.environ.get("AGENT_WORKSPACE_MOUNT", "/app/agent_workspace")


def _candidate_paths(owner: str, repo: str) -> list[Path]:
    base = Path(_agent_workspace())
    return [
        base / owner / repo,
        base / f"{owner}_{repo}",
        base / f"{owner}-{repo}",
        base / "repos" / owner / repo,
    ]


def _resolve_repo(owner: str, repo: str) -> Path | None:
    for p in _candidate_paths(owner, repo):
        if p.exists() and p.is_dir():
            return p
    return None


@router.post("/{owner}/{repo}/summarize", response_model=RepoSummaryResponse)
async def summarize_repo(
    owner: str,
    repo: str,
    max_files: int = Query(default=5000, ge=100, le=100_000),
) -> RepoSummaryResponse:
    """Summarize a cached repo.

    Returns the structure summary if the repo is already on disk in
    the agent workspace. Returns 404 with a ``hint`` if not found
    — caller should ``submit_job`` to clone + analyze.
    """
    repo_path = _resolve_repo(owner, repo)
    if repo_path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "repo_not_cached",
                "owner": owner,
                "repo": repo,
                "searched": [str(p) for p in _candidate_paths(owner, repo)],
                "hint": (
                    "Submit a job to clone the repo first: "
                    "POST /api/jobs with prompt='clone and analyze "
                    f"{owner}/{repo}' and repo_url set. The cached "
                    "path is then readable by this endpoint."
                ),
            },
        )

    from harness.tools.repo_analyzer import RepoAnalyzerTool
    tool = RepoAnalyzerTool()
    result = await tool.run(repo_path=str(repo_path), max_files=max_files)
    if not result.success:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "analysis_failed",
                "owner": owner,
                "repo": repo,
                "path": str(repo_path),
                "tool_error": result.error,
                "tool_output": result.output,
            },
        )
    data: dict[str, Any] = result.data or {}
    return RepoSummaryResponse(
        owner=owner,
        repo=repo,
        path=str(repo_path),
        total_files=int(data.get("total_files", 0)),
        total_size_bytes=int(data.get("total_size", 0)),
        languages={str(k): int(v) for k, v in (data.get("extensions") or {}).items()},
        entry_points=list(data.get("entry_points") or []),
        frameworks=list(data.get("frameworks") or []),
        manifests=list(data.get("manifests") or []),
        has_readme=bool(data.get("has_readme", False)),
        has_license=bool(data.get("has_license", False)),
        test_dirs=list(data.get("test_dirs") or []),
    )


__all__ = ["router", "summarize_repo"]
