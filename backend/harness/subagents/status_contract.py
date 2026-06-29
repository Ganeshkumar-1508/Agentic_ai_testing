"""Backend-frontend contract for structured subagent status.

Ported from DeerFlow (MIT License, Bytedance Ltd.).
Carries subagent_status in additional_kwargs so the frontend reads a
structured field instead of parsing leading text.
"""

from __future__ import annotations

from typing import Literal

SUBAGENT_STATUS_KEY = "subagent_status"
SUBAGENT_ERROR_KEY = "subagent_error"

SubagentStatusValue = Literal[
    "completed", "failed", "cancelled", "timed_out",
]

SUBAGENT_STATUS_VALUES: tuple[SubagentStatusValue, ...] = (
    "completed", "failed", "cancelled", "timed_out",
)

_PREFIX_TO_STATUS: tuple[tuple[str, SubagentStatusValue], ...] = (
    ("Result:", "completed"),
    ("timed out", "timed_out"),
    ("cancelled", "cancelled"),
    ("Error", "failed"),
    ("failed", "failed"),
)


def extract_subagent_status(content: str) -> SubagentStatusValue | None:
    trimmed = content.strip()
    for prefix, status in _PREFIX_TO_STATUS:
        if trimmed.startswith(prefix):
            return status
    return None


def make_subagent_additional_kwargs(
    status: SubagentStatusValue, *, error: str | None = None,
) -> dict[str, str]:
    if status not in SUBAGENT_STATUS_VALUES:
        raise ValueError(f"invalid subagent status {status!r}")
    payload: dict[str, str] = {SUBAGENT_STATUS_KEY: status}
    if error and error.strip():
        payload[SUBAGENT_ERROR_KEY] = error.strip()
    return payload
