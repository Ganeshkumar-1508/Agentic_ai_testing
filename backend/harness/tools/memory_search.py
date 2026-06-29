"""Chat LLM tools for the persistent memory substrate.

Exposes the agent's memory to the chat surface via two tools:
  * ``memory_search`` — full-text recall. The chat LLM uses this
    before answering questions about prior runs, past decisions,
    and recurring conventions.
  * ``memory_add`` — write a new fact. The chat LLM uses this at
    the end of a meaningful turn to commit observations it wants
    future sessions to recall.

The underlying table is ``harness.memory.agent_memory_store``
(Postgres + GIN FTS). The two functions follow the same Mem0
shape as the ``/api/memory/*`` HTTP endpoints; the tools are
thin wrappers that the chat LLM dispatches via the existing
tool registry.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


def _db_or_error() -> Any:
    from harness.tools.chat_read_tools import _db_or_error as _read_db_or_error
    return _read_db_or_error()


class MemorySearchTool(BaseTool):
    name = "memory_search"
    default_level = "allow"
    description = (
        "Search the agent's persistent memory for facts the chat "
        "user previously committed. Returns matching facts with "
        "their source tier (L0=raw observation, L1=inferred, "
        "L2=curated lesson), target entity, confidence, and "
        "metadata. Use before answering questions like 'what did "
        "we say about X last run?' or 'how do we usually handle Y?'"
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Full-text search query against memory content.",
                    },
                    "repo_slug": {
                        "type": "string",
                        "description": (
                            "Restrict to facts about one repo slug. "
                            "When None, searches across all repos."
                        ),
                    },
                    "source": {
                        "type": "string",
                        "enum": ["L0", "L1", "L2", "memory", ""],
                        "default": "",
                        "description": "Restrict to a fact tier.",
                    },
                    "target": {
                        "type": "string",
                        "description": "Restrict to facts about one entity.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["query"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        from harness.memory.agent_memory_store import search as search_facts
        db, err = _db_or_error()
        if err is not None:
            return err
        query = (kwargs.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, output="`query` is required", error="missing_arg")
        try:
            limit = max(1, min(50, int(kwargs.get("limit", 10))))
        except (TypeError, ValueError):
            limit = 10
        repo_slug = (kwargs.get("repo_slug") or "").strip() or None
        target = (kwargs.get("target") or "").strip() or None
        source = (kwargs.get("source") or "").strip() or None
        try:
            facts = await search_facts(
                query=query,
                repo_slug=repo_slug,
                source=source,
                target=target,
                limit=limit,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory_search: query failed: %s", exc)
            return ToolResult(success=False, output=f"Search failed: {exc}", error="db_error")

        if not facts:
            return ToolResult(
                success=True,
                output=f"No memory facts match `{query}`.",
                data={"results": []},
            )

        lines = [f"## {len(facts)} memory fact(s) for `{query}`\n"]
        results = []
        for f in facts:
            meta = f.metadata or {}
            conf = f.confidence if f.confidence is not None else "n/a"
            lines.append(
                f"- `[{f.source}]` **{f.target}** (conf={conf}): {f.content}"
            )
            if meta:
                lines.append(f"  meta: `{json.dumps(meta, default=str)[:200]}`")
            results.append(f.to_dict())
        return ToolResult(success=True, output="\n".join(lines), data={"results": results})


class MemoryAddTool(BaseTool):
    name = "memory_add"
    default_level = "allow"
    description = (
        "Commit a fact to the agent's persistent memory so future "
        "sessions can recall it. Use after a meaningful observation, "
        "decision, or convention is established. Pick the right tier: "
        "L0=raw observation (what just happened), L1=inferred lesson, "
        "L2=curated best practice."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 8_000,
                        "description": "The fact to commit. Free-text, but be specific.",
                    },
                    "repo_slug": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The repo slug this fact relates to.",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["L0", "L1", "L2"],
                        "default": "L0",
                        "description": "Fact tier: L0 (raw), L1 (inferred), L2 (curated).",
                    },
                    "target": {
                        "type": "string",
                        "default": "memory",
                        "description": "Entity the fact is about (e.g. 'auth', 'compaction', 'coordinator').",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "0..1 trust score. Use 0.5+ for verified, <0.5 for speculative.",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Arbitrary structured metadata.",
                    },
                },
                "required": ["content", "repo_slug"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        from harness.memory.agent_memory_store import add as add_fact
        db, err = _db_or_error()
        if err is not None:
            return err
        content = (kwargs.get("content") or "").strip()
        if not content:
            return ToolResult(success=False, output="`content` is required", error="missing_arg")
        repo_slug = (kwargs.get("repo_slug") or "").strip()
        if not repo_slug:
            return ToolResult(success=False, output="`repo_slug` is required", error="missing_arg")
        source = (kwargs.get("source") or "L0").strip()
        target = (kwargs.get("target") or "memory").strip()
        confidence = kwargs.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None
        metadata = kwargs.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"raw": str(metadata)[:200]}
        try:
            fact = await add_fact(
                content=content,
                repo_slug=repo_slug,
                source=source,
                target=target,
                confidence=confidence,
                source_kind="chat_tool",
                metadata=metadata,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory_add: insert failed: %s", exc)
            return ToolResult(success=False, output=f"Add failed: {exc}", error="db_error")

        return ToolResult(
            success=True,
            output=f"Memory fact stored: id={fact.id} [{fact.source}] {fact.target}: {fact.content[:200]}",
            data={"fact": fact.to_dict()},
        )


registry.register(MemorySearchTool(), toolset="read")
registry.register(MemoryAddTool(), toolset="read")


__all__ = ["MemorySearchTool", "MemoryAddTool"]
