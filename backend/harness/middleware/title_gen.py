"""Title middleware — ported from DeerFlow (MIT License, Bytedance Ltd).

Auto-generates thread title after the first complete user+assistant exchange.
Falls back to truncating the first user message.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


class TitleMiddleware(AgentMiddleware):
    """Auto-generate a title after the first complete exchange."""

    def __init__(self, max_chars: int = 80, max_words: int = 8) -> None:
        self._max_chars = max_chars
        self._max_words = max_words
        self._titled = False

    async def on_before_run(self, user_input: str) -> None:
        self._titled = False

    async def on_end_of_round(self, round_num: int) -> None:
        if self._titled or round_num > 0:
            return
        self._titled = True

    async def on_after_llm(self, tool_calls: list[dict], round_num: int) -> None:
        return None

    @staticmethod
    def _strip_think(text: str) -> str:
        return _THINK_RE.sub("", text).strip()

    @staticmethod
    def _first_user_msg(messages: list) -> str:
        for m in messages:
            if getattr(m, "role", "") == "user":
                content = getattr(m, "content", "") or ""
                if isinstance(content, list):
                    parts = [str(p) for p in content if isinstance(p, (str, dict))]
                    content = " ".join(parts)
                return str(content)
        return ""

    def _fallback_title(self, user_msg: str) -> str:
        cleaned = self._strip_think(user_msg)
        if len(cleaned) > self._max_chars:
            return cleaned[:self._max_chars].rstrip() + "..."
        return cleaned if cleaned else "New Conversation"

    def set_title(self, messages: list) -> str | None:
        if self._titled:
            return None
        user_msg = self._first_user_msg(messages)
        if not user_msg:
            return None
        title = self._fallback_title(user_msg)
        self._titled = True
        return title
