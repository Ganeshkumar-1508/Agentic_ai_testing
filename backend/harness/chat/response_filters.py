"""Response filtering for agent outputs.

Pattern from Hermes gateway/response_filters.py:
Filters operate at the output boundary — they decide whether a completed
agent turn should be delivered to the user, not what gets persisted.

Key concept: intentional silence. An agent can choose not to reply
(e.g. background monitor with nothing to report) by emitting a silence
marker instead of substantive text.
"""

from __future__ import annotations

from typing import Any

# Markers the agent can emit to intentionally stay silent.
# When the agent's entire response is one of these, it means
# "I have nothing to say" — not an error, not a failure.
SILENT_MARKERS: frozenset[str] = frozenset({
    "NO_REPLY",
    "[SILENT]",
    "SILENT",
    "NO REPLY",
    "[NO_REPLY]",
})


def _normalize(text: str) -> str:
    return " ".join(text.strip().upper().split())


def is_intentional_silence(response: Any) -> bool:
    """True when the agent intentionally chose not to reply.

    A blank response is NOT silence — that's an empty-response failure.
    Substantive prose that merely mentions NO_REPLY is delivered normally.
    """
    if not isinstance(response, str):
        return False
    stripped = response.strip()
    if not stripped:
        return False
    if len(stripped) > 64:
        return False
    return _normalize(stripped) in SILENT_MARKERS


def should_deliver(response: Any, agent_result: dict | None = None) -> bool:
    """True when the response should be delivered to the user.

    Filters out:
    - Intentional silence (agent chose not to reply)
    - Failed agent turns (errors should surface differently)
    """
    if agent_result and agent_result.get("failed"):
        return False
    if is_intentional_silence(response):
        return False
    return True
