"""Pluggable task review strategies — OpenHands SecurityAnalyzer pattern.

KanbanService accepts a TaskReviewer as a dependency. Production uses
LLMReviewer. Tests use NoOpReviewer. Adding a new review strategy means
subclassing TaskReviewer — no changes to KanbanService.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ReviewResult:
    approved: bool
    notes: str

    def __init__(self, approved: bool = True, notes: str = ""):
        self.approved = approved
        self.notes = notes


class TaskReviewer(ABC):
    """Pluggable review strategy for completed kanban tasks."""

    @abstractmethod
    async def review(self, title: str, description: str | None, result_summary: str | None) -> ReviewResult:
        ...


class NoOpReviewer(TaskReviewer):
    """Auto-approves everything — for tests and trusted agents."""

    async def review(self, title: str, description: str | None, result_summary: str | None) -> ReviewResult:
        return ReviewResult(approved=True, notes="Auto-approved (no-op reviewer)")


class LLMReviewer(TaskReviewer):
    """LLM-powered review — calls the model to evaluate completed work."""

    def __init__(self, llm_client: Any | None = None):
        self._llm_client = llm_client

    async def review(self, title: str, description: str | None, result_summary: str | None) -> ReviewResult:
        from harness.llm import LLMClient, ChatMessage
        client = self._llm_client or LLMClient()
        prompt = (
            "You are a senior code reviewer. Assess whether this completed task is complete and correct."
            " Reply with ONLY valid JSON: {\"approved\": bool, \"notes\": \"...\"}\n\n"
            f"Title: {title}\nDescription: {description or 'N/A'}\n"
            f"Result: {result_summary or 'N/A'}"
        )
        messages = [ChatMessage(role="user", content=prompt)]
        response = await client.chat(messages)
        content = response.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        verdict = json.loads(content)
        return ReviewResult(
            approved=verdict.get("approved", False),
            notes=verdict.get("notes", ""),
        )


async def run_review_agent_loop(db: Any, svc: Any, reviewer: TaskReviewer, interval: int = 30):
    """Background loop that polls the review column and runs the reviewer.

    Args:
        db: Database connection (for stale claim reaping).
        svc: KanbanService instance.
        reviewer: TaskReviewer implementation.
        interval: Polling interval in seconds.
    """
    await asyncio.sleep(15)
    _stale_counter = 0

    async def _cycle():
        nonlocal _stale_counter
        try:
            _stale_counter += 1
            if _stale_counter % 2 == 0:
                try:
                    from harness.services.kanban_service import _reap_stale_claims
                    await _reap_stale_claims(svc)
                except Exception:
                    pass

            rows = await svc.db.fetch(
                "SELECT * FROM kanban_tasks WHERE column_name='review' AND needs_review=true "
                "AND review_status IS NULL ORDER BY updated_at ASC LIMIT 5"
            )
            for row in rows:
                try:
                    result = await reviewer.review(
                        title=row["title"],
                        description=row.get("description"),
                        result_summary=row.get("result_summary"),
                    )
                    if result.approved:
                        await svc.db.execute(
                            "UPDATE kanban_tasks SET column_name='done', review_status='approved', "
                            "reviewed_by='ai_reviewer', review_notes=$1, reviewed_at=NOW(), updated_at=NOW() "
                            "WHERE id=$2", result.notes, row["id"],
                        )
                        await svc._record_event(row["board_id"], row["id"], "task.approved",
                                                 {"reviewer": "ai_reviewer", "notes": result.notes})
                    else:
                        await svc.db.execute(
                            "UPDATE kanban_tasks SET review_status='rejected', "
                            "reviewed_by='ai_reviewer', review_notes=$1, reviewed_at=NOW(), updated_at=NOW() "
                            "WHERE id=$2", result.notes, row["id"],
                        )
                        await svc._record_event(row["board_id"], row["id"], "task.rejected",
                                                 {"reviewer": "ai_reviewer", "notes": result.notes})
                    logger.info(
                        "Review agent %s task %s: %s",
                        "approved" if result.approved else "rejected", row["id"], result.notes,
                    )
                except Exception as e:
                    logger.warning("Review agent failed for task %s: %s", row["id"], e)
        except Exception as e:
            logger.warning("Review agent cycle error: %s", e)

    while True:
        await _cycle()
        await asyncio.sleep(interval)
