"""Tool error handling middleware — ported from DeerFlow's ToolErrorHandlingMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (unchanged from DeerFlow):
  - Converts tool execution exceptions into error strings so the agent loop
    can continue instead of aborting on a single tool failure.
  - Error message includes tool name, exception class, and truncated detail.
  - Always returns a string (never raises) — preserves tool_call pairing.

Adapted from DeerFlow's ``tool_error_handling_middleware.py`` (254 lines).
"""

from __future__ import annotations

import logging
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_MAX_DETAIL_LEN = 500


class ToolErrorHandlingMiddleware(AgentMiddleware):
    """Convert tool exceptions into error strings so the run continues."""

    async def on_before_tool(self, name: str, args: dict) -> bool | None:
        return None

    async def on_after_tool(self, name: str, result: str) -> str | None:
        return None

    @staticmethod
    def format_error(name: str, exc: Exception) -> str:
        detail = str(exc).strip() or exc.__class__.__name__
        if len(detail) > _MAX_DETAIL_LEN:
            detail = detail[:_MAX_DETAIL_LEN] + "..."
        return (
            f"Error: Tool '{name}' failed with {exc.__class__.__name__}: {detail}. "
            f"Continue with available context, or choose an alternative tool."
        )
