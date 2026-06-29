"""Input sanitization middleware — ported from DeerFlow's InputSanitizationMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (unchanged from DeerFlow):
  - Blocked system-reserved tags (<system>, <memory>, <instruction>, etc.)
    are HTML-escaped (<system> → &lt;system&gt;) so they render as literal
    text instead of structured-context markers (de-identify-don't-reject).
  - Clean input is wrapped in OWASP plain-text boundary markers.
  - Normal HTML/XML tags (<div>, <span>) pass through untouched.

Adapted from DeerFlow's ``input_sanitization_middleware.py`` (280 lines).
"""

from __future__ import annotations

import logging
import re

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_BLOCKED_TAG_NAMES: frozenset[str] = frozenset({
    "system-reminder",
    "memory",
    "current_date",
    "think",
    "analysis",
    "subagent_system",
    "skill_system",
    "uploaded_files",
    "system",
    "instruction",
    "role",
    "important",
    "override",
    "ignore",
    "prompt",
})

_BLOCKED_TAG_PATTERN = re.compile(
    r"<\s*/?\s*(?:" + "|".join(re.escape(t) for t in sorted(_BLOCKED_TAG_NAMES)) + r")\b[^>]*>?",
    re.IGNORECASE,
)

_USER_INPUT_BEGIN = "--- BEGIN USER INPUT ---"
_USER_INPUT_END = "--- END USER INPUT ---"
_NEUTRALIZED_BEGIN = "[BEGIN USER INPUT]"
_NEUTRALIZED_END = "[END USER INPUT]"

_BOUNDARY_TOKEN_RE = re.compile(
    re.escape(_USER_INPUT_BEGIN) + r"|" + re.escape(_USER_INPUT_END),
)


def _escape_tag_match(match: re.Match) -> str:
    return match.group(0).replace("<", "&lt;").replace(">", "&gt;")


def sanitize_user_content(text: str) -> str:
    """Sanitize user content: escape blocked tags, wrap in boundary markers."""
    if not text.strip():
        return text

    text = _BLOCKED_TAG_PATTERN.sub(_escape_tag_match, text)

    if text.startswith(_USER_INPUT_BEGIN) and text.endswith(_USER_INPUT_END):
        inner = text[len(_USER_INPUT_BEGIN):-len(_USER_INPUT_END)]
        neutralized_inner = _BOUNDARY_TOKEN_RE.sub(
            lambda m: _NEUTRALIZED_BEGIN if m.group(0) == _USER_INPUT_BEGIN else _NEUTRALIZED_END,
            inner,
        )
        if neutralized_inner == inner:
            return text
        return f"{_USER_INPUT_BEGIN}{neutralized_inner}{_USER_INPUT_END}"

    text = _BOUNDARY_TOKEN_RE.sub(
        lambda m: _NEUTRALIZED_BEGIN if m.group(0) == _USER_INPUT_BEGIN else _NEUTRALIZED_END,
        text,
    )
    return f"{_USER_INPUT_BEGIN}\n{text}\n{_USER_INPUT_END}"


class InputSanitizeMiddleware(AgentMiddleware):
    """Escape prompt-injection tags in user input before LLM call."""

    def __init__(self) -> None:
        self._user_input: str = ""

    async def on_before_run(self, user_input: str) -> None:
        self._user_input = user_input

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        if round_num > 0:
            return None
        if not self._user_input:
            return None

        sanitized = sanitize_user_content(self._user_input)
        if sanitized == self._user_input:
            return None

        for i, msg in enumerate(messages):
            if getattr(msg, "role", "") == "user":
                from harness.core.events import ChatMessage
                messages[i] = ChatMessage(role="user", content=sanitized)
                return messages
        return None
