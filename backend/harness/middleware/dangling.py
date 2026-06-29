"""Dangling tool call middleware — ported from DeerFlow's DanglingToolCallMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (unchanged from DeerFlow):
  - Scans message history for AIMessages with tool_calls that have no
    corresponding ToolMessage responses.
  - Injects synthetic error ToolMessages for each dangling call.
  - Preserves correct message ordering (tool_calls → tool_results).

Adapted from DeerFlow's ``dangling_tool_call_middleware.py``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_MAX_RECOVERY_DETAIL_LEN = 500
_DANGLING_ERROR = "Tool call was interrupted or cancelled before execution."


class DanglingToolCallMiddleware(AgentMiddleware):
    """Injects placeholder ToolMessages for dangling tool calls before LLM calls."""

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        patches: list[tuple[int, dict]] = []
        for i, msg in enumerate(messages):
            role = getattr(msg, "role", None)
            tool_calls = self._get_tool_calls(msg)
            if role != "assistant" or not tool_calls:
                continue

            following = messages[i + 1:i + len(tool_calls) + 1]
            responding_ids = {
                getattr(m, "tool_call_id", None)
                for m in following if getattr(m, "role", None) == "tool"
            }
            tool_call_ids = {
                tc.get("id", "") for tc in tool_calls
            }

            missing = tool_call_ids - responding_ids
            for tc in tool_calls:
                tid = tc.get("id", "")
                if tid not in missing:
                    continue
                patches.append((i + 1, {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": f"Error: {_DANGLING_ERROR}",
                }))

        if not patches:
            return None

        new_messages = list(messages)
        offset = 0
        for insert_after, patch in patches:
            new_messages.insert(insert_after + offset, self._make_message(**patch))
            offset += 1

        logger.warning("DanglingToolCall: injected %d placeholder ToolMessage(s)", len(patches))
        return new_messages

    @staticmethod
    def _get_tool_calls(msg: Any) -> list[dict]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return list(msg.tool_calls)
        return []

    @staticmethod
    def _make_message(**kwargs: Any) -> Any:
        from harness.core.events import ChatMessage
        return ChatMessage(**kwargs)
