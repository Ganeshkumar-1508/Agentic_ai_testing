"""Dynamic context middleware — ported from DeerFlow (MIT License, Bytedance Ltd).

Injects current date (+ optional memory) as a system-reminder before the first
user message. Keeps system prompt static for prefix-cache reuse. Detects
midnight crossings and injects a lightweight date update.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"<current_date>([^<]+)</current_date>")
_REMINDER_CONTENT_KEY = "dynamic_context"


class DynamicContextMiddleware(AgentMiddleware):
    """Inject current date as a system-reminder before the first user message."""

    def __init__(self, memory_provider: Any | None = None) -> None:
        self._memory_provider = memory_provider
        self._injected_date: str = ""

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d, %A")

    def _has_existing_reminder(self, messages: list) -> str | None:
        for msg in messages:
            if getattr(msg, "additional_kwargs", {}).get(_REMINDER_CONTENT_KEY):
                content = getattr(msg, "content", "") or ""
                m = _DATE_RE.search(str(content))
                if m:
                    return m.group(1)
        return None

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        existing = self._has_existing_reminder(messages)
        today = self._today()

        if existing is None:
            reminder = (
                f"<system-reminder>\n<current_date>{today}</current_date>\n</system-reminder>"
            )
            from harness.core.events import ChatMessage
            new_msgs = list(messages)
            new_msgs.insert(0, ChatMessage(
                role="system", content=reminder,
                additional_kwargs={_REMINDER_CONTENT_KEY: True},
            ))
            self._injected_date = today
            logger.debug("DynamicContext: injected date reminder %s", today)
            return new_msgs

        if existing != today:
            update = (
                f"<system-reminder>\n<current_date>{today}</current_date>\n</system-reminder>"
            )
            from harness.core.events import ChatMessage
            new_msgs = list(messages) + [
                ChatMessage(role="system", content=update,
                            additional_kwargs={_REMINDER_CONTENT_KEY: True})
            ]
            logger.info("DynamicContext: midnight crossing detected %s -> %s", existing, today)
            return new_msgs

        return None
