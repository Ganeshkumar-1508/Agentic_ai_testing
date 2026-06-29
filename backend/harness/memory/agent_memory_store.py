"""Typed wrapper around the ``agent_memory`` Postgres table.

The ``agent_memory`` table is the LLM-readable knowledge substrate
the chat surface uses to recall facts across runs. Schema
(defined in ``harness/memory/schema/schema.sql``):

    id          TEXT PRIMARY KEY
    repo_slug   TEXT NOT NULL
    source      TEXT NOT NULL          -- L0 | L1 | L2 (fact tier)
    target      TEXT NOT NULL DEFAULT 'memory'  -- entity the fact is about
    content     TEXT NOT NULL          -- the fact itself
    confidence  FLOAT                  -- 0..1
    source_kind TEXT                   -- e.g. "chat_observation", "compaction_summary"
    metadata    JSONB                  -- arbitrary structured metadata
    created_at  TIMESTAMPTZ

Indexed by (repo_slug, source, created_at DESC) and a GIN FTS
index on ``content`` (english). Search uses Postgres ``to_tsquery``
against the FTS index for sub-millisecond ranked retrieval.

API shape mirrors Mem0's ``add`` + ``search``:

    add(content, *, repo_slug, source, target, confidence, source_kind, metadata)
    search(query, *, repo_slug=None, source=None, target=None, limit=10, min_confidence=0.0)

Both functions are async; they require a connected ``Database``
(``request.app.state.db`` in a request, ``harness.memory.db_context``
in a chat LLM tool).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from harness.memory.database import Database


VALID_SOURCES: frozenset[str] = frozenset({"L0", "L1", "L2", "memory"})


@dataclass
class MemoryFact:
    """One row from the ``agent_memory`` table."""

    id: str
    repo_slug: str
    source: str
    target: str
    content: str
    confidence: float | None
    source_kind: str | None
    metadata: dict[str, Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo_slug": self.repo_slug,
            "source": self.source,
            "target": self.target,
            "content": self.content,
            "confidence": self.confidence,
            "source_kind": self.source_kind,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


def _resolve_db(db: "Database | None") -> "Database":
    if db is not None:
        return db
    from harness.memory.db_context import get_db
    resolved = get_db()
    if resolved is None:
        raise RuntimeError(
            "Database not connected. Call Database.connect() at startup "
            "or pass an explicit Database."
        )
    return resolved


async def add(
    content: str,
    *,
    repo_slug: str,
    source: str = "L0",
    target: str = "memory",
    confidence: float | None = None,
    source_kind: str | None = None,
    metadata: dict[str, Any] | None = None,
    db: "Database | None" = None,
) -> MemoryFact:
    """Insert a new fact. Returns the persisted row.

    The Mem0 ``add`` shape: caller provides a free-text ``content``
    string plus optional structured ``metadata`` and tier markers
    (``source`` is L0/L1/L2, ``target`` is the entity the fact is
    about, ``confidence`` is a 0..1 trust score).
    """
    if not content or not content.strip():
        raise ValueError("content is required")
    if not repo_slug or not repo_slug.strip():
        raise ValueError("repo_slug is required")
    if source not in VALID_SOURCES:
        raise ValueError(
            f"source must be one of {sorted(VALID_SOURCES)!r}, got {source!r}"
        )
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be 0..1, got {confidence}")

    conn = _resolve_db(db)
    fact_id = str(uuid.uuid4())
    import json as _json
    metadata_json_str = _json.dumps(metadata or {}, ensure_ascii=False, default=str)

    row = await conn.fetchrow(
        """
        INSERT INTO agent_memory
            (id, repo_slug, source, target, content, confidence, source_kind, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        RETURNING id, repo_slug, source, target, content, confidence, source_kind, metadata, created_at
        """,
        fact_id, repo_slug, source, target, content.strip(),
        confidence, source_kind, metadata_json_str,
    )
    return _fact_from_row(row)


async def search(
    query: str,
    *,
    repo_slug: str | None = None,
    source: str | None = None,
    target: str | None = None,
    limit: int = 10,
    min_confidence: float = 0.0,
    db: "Database | None" = None,
) -> list[MemoryFact]:
    """Search facts by FTS over ``content``.

    Mirrors Mem0's ``search`` shape: caller provides a free-text
    ``query`` plus optional filters. Returns up to ``limit`` facts
    ranked by ts_rank. When ``repo_slug`` is None, searches across
    all repos (caller is responsible for scoping at the prompt
    layer).
    """
    if not query or not query.strip():
        return []
    if limit < 1 or limit > 200:
        raise ValueError(f"limit must be 1..200, got {limit}")
    if min_confidence < 0.0 or min_confidence > 1.0:
        raise ValueError(f"min_confidence must be 0..1, got {min_confidence}")
    if source is not None and source not in VALID_SOURCES:
        raise ValueError(
            f"source must be one of {sorted(VALID_SOURCES)!r}, got {source!r}"
        )

    conn = _resolve_db(db)
    clauses: list[str] = [
        "to_tsvector('english', content) @@ plainto_tsquery('english', $1)",
    ]
    params: list[Any] = [query.strip()]
    if repo_slug is not None:
        params.append(repo_slug)
        clauses.append(f"repo_slug = ${len(params)}")
    if source is not None:
        params.append(source)
        clauses.append(f"source = ${len(params)}")
    if target is not None:
        params.append(target)
        clauses.append(f"target = ${len(params)}")
    if min_confidence > 0.0:
        params.append(min_confidence)
        clauses.append(f"(confidence IS NULL OR confidence >= ${len(params)})")
    params.append(limit)
    where = " AND ".join(clauses)
    rows = await conn.fetch(
        f"""
        SELECT id, repo_slug, source, target, content, confidence, source_kind,
               metadata, created_at,
               ts_rank(to_tsvector('english', content), plainto_tsquery('english', $1)) AS rank
        FROM agent_memory
        WHERE {where}
        ORDER BY rank DESC, created_at DESC
        LIMIT ${len(params)}
        """,
        *params,
    )
    return [_fact_from_row(r) for r in rows]


def _fact_from_row(row: Any) -> MemoryFact:
    import json as _json
    raw_meta = row["metadata"]
    if isinstance(raw_meta, str):
        try:
            meta = _json.loads(raw_meta) if raw_meta else {}
        except (ValueError, TypeError):
            meta = {}
    elif isinstance(raw_meta, dict):
        meta = raw_meta
    else:
        meta = {}
    return MemoryFact(
        id=row["id"],
        repo_slug=row["repo_slug"],
        source=row["source"],
        target=row["target"] or "memory",
        content=row["content"],
        confidence=row["confidence"],
        source_kind=row["source_kind"],
        metadata=meta,
        created_at=row["created_at"],
    )


__all__ = [
    "MemoryFact",
    "VALID_SOURCES",
    "add",
    "search",
]
