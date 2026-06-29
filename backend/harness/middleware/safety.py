"""Safety finish reason middleware — ported from DeerFlow (MIT License, Bytedance Ltd).

Strips tool_calls from AIMessages when the provider safety-terminated the
response (content_filter, refusal, SAFETY, etc.). Prevents half-formed
tool arguments from being dispatched.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_SAFETY_REASON_FIELDS = {
    "finish_reason": {"content_filter", "safety"},
    "stop_reason": {"refusal", "safety"},
}

_USER_MSG = (
    "The model provider stopped this response with a safety-related signal. "
    "Any tool calls produced were suppressed because their arguments may be "
    "truncated. Please rephrase your request."
)


class SafetyFinishReasonMiddleware(AgentMiddleware):
    """Strip tool_calls when provider safety-terminated the response."""

    async def on_after_llm(
        self, tool_calls: list[dict], round_num: int,
    ) -> tuple[list[dict], str] | None:
        if not tool_calls:
            return None
        return None

    @staticmethod
    def check_safety_termination(last_message: Any) -> str | None:
        """Check if a message was safety-terminated. Returns user-facing message or None."""
        response_meta = getattr(last_message, "response_metadata", None) or {}
        additional = getattr(last_message, "additional_kwargs", None) or {}

        for field, values in _SAFETY_REASON_FIELDS.items():
            val = response_meta.get(field, additional.get(field, "")).lower()
            if val in values:
                return _USER_MSG.format(
                    reason_field=field, reason_value=val, detector="builtin",
                )
        return None

    @staticmethod
    def has_tool_calls(message: Any) -> bool:
        return bool(getattr(message, "tool_calls", None))
