"""Subagent limit middleware — ported from DeerFlow's SubagentLimitMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (adapted from DeerFlow):
  - Limits concurrent 'task' tool calls from a single model response.
  - Excess calls beyond max_concurrent are silently dropped.
  - Default range: 5-8 (TestAI override).

Adapted from DeerFlow's ``subagent_limit_middleware.py`` (76 lines).
"""

from __future__ import annotations

import logging
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

MIN_SUBAGENT_LIMIT = 5
MAX_SUBAGENT_LIMIT = 8


class SubagentLimitMiddleware(AgentMiddleware):
    """Truncates excess 'task' (delegate_task) tool calls from a single response.
    
    Keeps only the first max_concurrent calls; drops the rest silently.
    More reliable than prompt-based limits.
    """

    def __init__(self, max_concurrent: int = MIN_SUBAGENT_LIMIT) -> None:
        self.max_concurrent = max(MIN_SUBAGENT_LIMIT, min(MAX_SUBAGENT_LIMIT, max_concurrent))

    async def on_after_llm(
        self, tool_calls: list[dict], round_num: int,
    ) -> list[dict] | None:
        if not tool_calls:
            return None

        task_indices = [
            i for i, tc in enumerate(tool_calls)
            if tc.get("function", {}).get("name") == "delegate_task"
        ]
        if len(task_indices) <= self.max_concurrent:
            return None

        keep = set(range(len(tool_calls))) - set(task_indices[self.max_concurrent:])
        truncated = [tc for i, tc in enumerate(tool_calls) if i in keep]
        logger.warning(
            "SubagentLimit: truncated %d excess delegate_task calls (limit=%d)",
            len(task_indices) - self.max_concurrent, self.max_concurrent,
        )
        return truncated
