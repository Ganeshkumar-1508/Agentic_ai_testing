"""Context compaction — manages LLM context window to prevent overflow.

Three strategies:
  1. Micro-compact (free): Strip old tool outputs before every turn.
  2. Auto-compact (LLM): Summarize old messages when context exceeds threshold.
  3. Reactive compact (last resort): On prompt_too_long API error, truncate + retry.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Context overflow detection patterns (from OpenHarness)
PROMPT_TOO_LONG_PATTERNS = [
    "prompt too long",
    "context_length_exceeded",
    "context length",
    "maximum context length",
    "context window",
    "input tokens exceed",
    "messages resulted in",
    "reduce the length of the messages",
    "configured limit",
    "too many tokens",
    "too large for the model",
    "exceed_context",
    "exceeds the available context size",
    "available context size",
]


def is_prompt_too_long_error(error: Exception | str) -> bool:
    """Check if an error is a context overflow."""
    text = str(error).lower()
    return any(needle in text for needle in PROMPT_TOO_LONG_PATTERNS)


def micro_compact(messages: list[dict], max_turns: int = 20) -> list[dict]:
    """Cheap pre-pass: remove old tool outputs, keep system + recent N turns.

    This is free (no LLM call). Just drops old tool_result messages
    that are no longer needed.
    """
    if len(messages) <= max_turns:
        return messages

    # Keep system prompt and the most recent `max_turns` messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    kept = non_system[-max_turns:]

    logger.info("Micro-compact: %d → %d messages", len(messages), len(system_msgs) + len(kept))
    return system_msgs + kept


def reactive_compact(messages: list[dict], error: Exception | str) -> list[dict] | None:
    """React to a prompt_too_long error by truncating oldest message groups.

    Returns the compacted messages, or None if the error is not a context overflow.
    """
    if not is_prompt_too_long_error(error):
        return None

    # Remove oldest non-system messages in groups of 5
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    # Drop 30% of oldest messages
    drop_count = max(5, len(non_system) // 3)
    kept = non_system[drop_count:]

    result = system_msgs + kept
    logger.info("Reactive compact: %d → %d messages (dropped %d oldest)", len(messages), len(result), drop_count)
    return result


def estimate_tokens(text: str) -> int:
    """Rough token estimation (chars / 4)."""
    return len(text) // 4
