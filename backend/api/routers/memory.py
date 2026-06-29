"""Memory API — Mem0-shape add + search over the agent_memory table.

Endpoints:
  * ``POST /api/memory/add`` — insert a fact. Body matches
    Mem0's ``messages`` shape: a free-text ``content`` string
    plus structured ``metadata`` and tier markers.
  * ``POST /api/memory/search`` — full-text search over
    ``content``. Filters by ``repo_slug``, ``source`` (L0/L1/L2),
    ``target``, and ``min_confidence``.

The chat LLM consumes these via the ``memory_search`` tool
(see ``harness/tools/memory_search.py``).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from harness.memory.agent_memory_store import (
    VALID_SOURCES,
    MemoryFact,
    add as add_fact,
    search as search_facts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


class AddMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8_000)
    repo_slug: str = Field(min_length=1, max_length=200)
    source: str = Field(default="L0", description=f"One of {sorted(VALID_SOURCES)}")
    target: str = Field(default="memory", max_length=200)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_kind: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AddMemoryResponse(BaseModel):
    id: str
    repo_slug: str
    source: str
    target: str
    content: str
    confidence: float | None
    source_kind: str | None
    metadata: dict[str, Any]
    created_at: str


class SearchMemoryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    repo_slug: str | None = None
    source: str | None = Field(default=None, description=f"One of {sorted(VALID_SOURCES)}")
    target: str | None = None
    limit: int = Field(default=10, ge=1, le=200)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchMemoryResponse(BaseModel):
    query: str
    count: int
    results: list[AddMemoryResponse]


@router.post("/add", response_model=AddMemoryResponse, status_code=201)
async def add_memory_endpoint(request: Request, body: AddMemoryRequest) -> AddMemoryResponse:
    """Insert a fact into the agent's persistent memory.

    Mirrors Mem0's ``add`` shape: free-text ``content`` plus
    structured metadata. The fact is stored under ``repo_slug``
    (mandatory) and tier-marked ``source`` (default ``L0`` =
    raw observation, ``L1`` = inferred, ``L2`` = curated lesson).
    """
    db = request.app.state.db
    try:
        fact = await add_fact(
            content=body.content,
            repo_slug=body.repo_slug,
            source=body.source,
            target=body.target,
            confidence=body.confidence,
            source_kind=body.source_kind,
            metadata=body.metadata,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AddMemoryResponse(**fact.to_dict())


@router.post("/search", response_model=SearchMemoryResponse)
async def search_memory_endpoint(request: Request, body: SearchMemoryRequest) -> SearchMemoryResponse:
    """Full-text search over agent memory.

    Mirrors Mem0's ``search`` shape: free-text ``query`` plus
    optional filters. Returns up to ``limit`` facts ranked by
    Postgres ``ts_rank`` against the GIN FTS index.
    """
    db = request.app.state.db
    try:
        facts: list[MemoryFact] = await search_facts(
            query=body.query,
            repo_slug=body.repo_slug,
            source=body.source,
            target=body.target,
            limit=body.limit,
            min_confidence=body.min_confidence,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SearchMemoryResponse(
        query=body.query,
        count=len(facts),
        results=[AddMemoryResponse(**f.to_dict()) for f in facts],
    )


__all__ = ["router", "add_memory_endpoint", "search_memory_endpoint"]
