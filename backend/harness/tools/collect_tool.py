"""CollectResults tool — collect background subagent results."""

from __future__ import annotations

from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.subagent import SubagentResult, collect_results

# Default timeout for background subagents
CHILD_TIMEOUT_SECONDS = 1000


class CollectResultsTool(BaseTool):
    """Collect results from background subagents spawned via delegate_task.

    Blocks until all specified subagents complete (or timeout).
    Usage: call collect_results after one or more delegate_task(background=True) calls.
    """
    name = "collect_results"
    description = (
        "Collect results from background subagents. Optionally pass subagent_ids "
        "returned by delegate_task(run_in_background=True). If no IDs are provided, "
        "collects all pending background subagent results. "
        "Waits for all to complete or until timeout."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "subagent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of subagent_ids to wait for (auto-collects all pending if omitted)",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Max seconds to wait (default 600)",
                        "default": CHILD_TIMEOUT_SECONDS,
                    },
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        subagent_ids = kwargs.get("subagent_ids", None) or []
        timeout_val = kwargs.get("timeout", CHILD_TIMEOUT_SECONDS)

        # If no IDs provided, auto-collect all pending background subagents.
        # This makes the tool easier for LLMs to use — they don't need to
        # parse subagent IDs from delegate_task output.
        if not subagent_ids:
            from harness.tools.subagent import Subagent
            subagent_ids = Subagent().pending_subagent_ids()
            if not subagent_ids:
                return ToolResult(success=False, output="No background subagents to collect", error="nothing_pending")

        results = await collect_results(subagent_ids, timeout=timeout_val)
        summary_lines = [f"  {sid}: {res[:100]}" for sid, res in results.items()]
        summary = "\n".join(summary_lines)
        return ToolResult(success=True, output=f"Background results:\n{summary}", data={"results": results})
