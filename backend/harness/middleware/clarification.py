"""Clarification middleware — ported from DeerFlow (MIT License, Bytedance Ltd).

Intercepts ask_clarification tool calls and interrupts execution, returning
a formatted question to the user instead of continuing the agent loop.
"""

from __future__ import annotations

import json
import logging
from hashlib import sha256

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_CLARIFICATION_TOOL = "ask_clarification"


class ClarificationMiddleware(AgentMiddleware):
    """Intercept ask_clarification tool calls and return the question to the user."""

    async def on_before_tool(self, name: str, args: dict) -> bool | None:
        if name != _CLARIFICATION_TOOL:
            return None

        question = args.get("question", "")
        context = args.get("context", "")
        options = args.get("options", [])
        ctype = args.get("clarification_type", "missing_info")

        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [options]
        if options is None:
            options = []
        elif not isinstance(options, list):
            options = [options]

        parts = []
        if context:
            parts.append(f"[{ctype}] {context}")
        parts.append(f"Question: {question}")
        if options:
            for i, opt in enumerate(options, 1):
                parts.append(f"  {i}. {opt}")

        msg = "\n".join(parts)
        logger.info("Clarification requested: %s", msg[:200])
        return False

    async def on_after_tool(self, name: str, result: str) -> str | None:
        return None
