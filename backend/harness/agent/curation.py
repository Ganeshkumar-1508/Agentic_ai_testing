"""Subagent context curation — extract task-relevant context for a subagent.

Per AOrchestra (2026): "context filtering — only pass task-relevant history."
Passing the full parent conversation to a subagent hurts accuracy (O(N²)
token cost, off-topic noise) and was flagged by Neel Mishra as the #1
cost driver. This module produces a short, relevant context string from
the parent's recent messages.

Strategy: take the most recent N non-system messages, trim to `max_chars`.
Skips system prompts (subagent gets its own system prompt via `delegate_task`).
"""
from __future__ import annotations

from typing import Any, Iterable


__all__ = ["curate_subagent_context"]


MAX_CONTEXT_CHARS = 4000


def curate_subagent_context(
    goal: str,
    parent_messages: Iterable[Any],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Build a relevant context string for a subagent from the parent's history.

    Walks messages in reverse (most recent first), skips system prompts and
    empty messages, trims each message to 500 chars, and stops when the
    budget is hit. Returns "No prior context." if nothing remains.
    """
    relevant: list[str] = []
    char_count = 0
    prefix = (goal or "").strip() or "Subtask"

    for msg in reversed(list(parent_messages)):
        if msg.role == "system":
            continue
        content = (getattr(msg, "content", "") or "").strip()
        if not content:
            continue
        snippet = f"[{msg.role}] {content[:500]}"
        if char_count + len(snippet) > max_chars:
            break
        relevant.insert(0, snippet)
        char_count += len(snippet)

    if not relevant:
        return "No prior context."

    return f"## Relevant context for: {prefix}\n\n" + "\n".join(relevant)
