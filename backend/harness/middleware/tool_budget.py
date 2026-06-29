"""Tool output budget middleware — ported from DeerFlow's ToolOutputBudgetMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (unchanged from DeerFlow):
  - Oversized tool results (> config.externalize_min_chars) are persisted
    to disk and replaced with a compact preview + file reference.
  - When disk persistence is unavailable, falls back to head+tail truncation.
  - Exempt tools (config.exempt_tools) skip budgeting.

Adapted from DeerFlow's ``tool_output_budget_middleware.py`` (643 lines).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_VIRTUAL_OUTPUTS_BASE = "/mnt/user-data/outputs"

_EXT_MAP: dict[str, str] = {
    "bash": "log",
    "bash_tool": "log",
    "web_fetch": "log",
}


@dataclass
class ToolBudgetConfig:
    enabled: bool = True
    externalize_min_chars: int = 5000
    fallback_max_chars: int = 8000
    preview_head_chars: int = 2000
    preview_tail_chars: int = 1000
    fallback_head_chars: int = 3000
    fallback_tail_chars: int = 1000
    storage_subdir: str = "tool_outputs"
    exempt_tools: set[str] = field(default_factory=lambda: {"read_file", "grep", "glob", "list_dir"})
    tool_overrides: dict[str, int] = field(default_factory=dict)


def _snap_to_line(text: str, pos: int) -> int:
    if pos <= 0 or pos >= len(text):
        return pos
    half = pos // 2
    nl = text.rfind("\n", half, pos)
    return nl + 1 if nl >= 0 else pos


def _build_preview(
    content: str, *, tool_name: str, virtual_path: str,
    head_chars: int, tail_chars: int,
) -> str:
    total = len(content)
    head_end = _snap_to_line(content, min(head_chars, total))
    tail_start = max(head_end, total - tail_chars)
    tail_start = _snap_to_line(content, tail_start)
    if tail_start > head_end:
        tail_start = tail_start
    else:
        tail_start = head_end

    head = content[:head_end]
    tail = content[tail_start:] if tail_start < total else ""
    omitted = total - len(head) - len(tail)

    ref = (
        f"\n\n[Full {tool_name} output saved to {virtual_path} "
        f"({total} chars, ~{total // 4} tokens). Use read_file to access. "
        f"{omitted} chars omitted.]\n\n"
    )
    parts = [head, ref]
    if tail:
        parts.append(tail)
    return "".join(parts)


def _build_fallback(
    content: str, *, tool_name: str, max_chars: int,
    head_chars: int, tail_chars: int,
) -> str:
    total = len(content)
    if max_chars <= 0 or total <= max_chars:
        return content

    marker = (
        f"\n\n[... {{n}} chars omitted from {tool_name} output. "
        f"Consider narrowing the query.]\n\n"
    )
    marker_overhead = len(marker.format(n=total))

    if marker_overhead >= max_chars:
        return content[:max_chars]

    budget = max_chars - marker_overhead
    eff_head = min(head_chars, budget)
    eff_tail = min(tail_chars, max(0, budget - eff_head))

    head_end = _snap_to_line(content, min(eff_head, total))
    tail_start = max(head_end, total - eff_tail)
    tail_start = _snap_to_line(content, tail_start)
    if tail_start > head_end:
        tail_start = tail_start
    else:
        tail_start = head_end

    head = content[:head_end]
    tail = content[tail_start:] if tail_start < total else ""
    omitted = total - len(head) - len(tail)

    return "".join([head, marker.format(n=omitted), tail])


class ToolBudgetMiddleware(AgentMiddleware):
    """Enforce per-result budget on tool outputs via externalization or truncation."""

    def __init__(self, config: ToolBudgetConfig | None = None) -> None:
        self._config = config or ToolBudgetConfig()
        self._outputs_dir: str = ""

    async def on_before_run(self, user_input: str) -> None:
        self._outputs_dir = os.environ.get("TESTAI_OUTPUTS_DIR", "")

    async def on_after_tool(self, name: str, result: str) -> str | None:
        if not self._config.enabled:
            return None
        if name in self._config.exempt_tools:
            return None

        threshold = self._config.tool_overrides.get(name, self._config.externalize_min_chars)
        if len(result) <= threshold and len(result) <= self._config.fallback_max_chars:
            return None

        if threshold > 0 and len(result) > threshold and self._outputs_dir:
            safe_name = name.replace("..", "").replace("/", "_").replace("\\", "_")
            ext = _EXT_MAP.get(name, "txt")
            short_id = uuid.uuid4().hex[:12]
            filename = f"{safe_name}-{short_id}.{ext}"

            storage_dir = os.path.join(self._outputs_dir, self._config.storage_subdir)
            try:
                os.makedirs(storage_dir, exist_ok=True)
                filepath = os.path.join(storage_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(result)
                virtual_path = f"{_VIRTUAL_OUTPUTS_BASE}/{self._config.storage_subdir}/{filename}"
                logger.info("Externalized %s output (%d chars) to %s", name, len(result), virtual_path)
                return _build_preview(
                    result, tool_name=name, virtual_path=virtual_path,
                    head_chars=self._config.preview_head_chars,
                    tail_chars=self._config.preview_tail_chars,
                )
            except OSError as exc:
                logger.warning("Failed to externalize %s output: %s", name, exc)

        if self._config.fallback_max_chars > 0 and len(result) > self._config.fallback_max_chars:
            logger.warning("Fallback-truncating %s output: %d chars", name, len(result))
            return _build_fallback(
                result, tool_name=name,
                max_chars=self._config.fallback_max_chars,
                head_chars=self._config.fallback_head_chars,
                tail_chars=self._config.fallback_tail_chars,
            )

        return None
