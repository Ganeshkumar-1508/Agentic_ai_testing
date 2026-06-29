"""Fan-out tool for explicit parallel subagent spawning."""

from __future__ import annotations

import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class FanOutTasksTool(BaseTool):
    """Spawn multiple subagents in parallel for independent tasks.
    
    This tool provides an explicit interface for fan-out parallelism,
    making it clear when the coordinator wants to spawn multiple workers
    simultaneously rather than sequentially.
    """

    name = "fan_out_tasks"
    description = (
        "Spawn N subagents in parallel for N independent tasks. "
        "Each task gets its own isolated worker. Returns when all complete. "
        "Use this for parallel exploration, testing, or implementation. "
        "Max 10 concurrent workers."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of task descriptions (max 10). Each task spawns one worker.",
                        "maxItems": 10,
                    },
                    "toolsets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Toolsets to grant to each worker (default: ['read'])",
                        "default": ["read"],
                    },
                    "agent": {
                        "type": "string",
                        "description": "Agent definition name for all workers (e.g., 'explore', 'fix')",
                    },
                    "model": {
                        "type": "string",
                        "description": "Model override for all workers (e.g., 'haiku' for cheap tasks)",
                    },
                },
                "required": ["tasks"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        tasks = kwargs.get("tasks", [])
        toolsets = kwargs.get("toolsets", ["read"])
        agent_name = kwargs.get("agent")
        model_override = kwargs.get("model")

        if not tasks:
            return ToolResult(success=False, output="tasks array is required and must not be empty", error="missing_tasks")

        if len(tasks) > 10:
            return ToolResult(success=False, output=f"Max 10 concurrent workers. Got {len(tasks)} tasks.", error="too_many_tasks")

        # Get the delegate_task tool to spawn workers
        from harness.tools.registry import registry
        delegate_tool = registry.get("delegate_task")
        
        if not delegate_tool:
            return ToolResult(success=False, output="delegate_task tool not available", error="no_delegate_tool")

        logger.info("Fan-out: spawning %d parallel workers", len(tasks))

        # Use delegate_task in fan-out mode (tasks parameter)
        try:
            result = await delegate_tool.run(
                tasks=tasks,
                toolsets=toolsets,
                agent=agent_name,
                model=model_override,
            )
            
            # The result should contain outputs from all workers
            if result.success:
                output = result.output or ""
                data = result.data or {}
                count = data.get("count", len(tasks))
                logger.info("Fan-out complete: %d workers returned results", count)
                return ToolResult(
                    success=True,
                    output=f"Fan-out complete. {count} workers executed in parallel.\n\n{output}",
                    data=data,
                )
            else:
                return ToolResult(
                    success=False,
                    output=f"Fan-out failed: {result.output}",
                    error=result.error or "fan_out_failed",
                )
        
        except Exception as e:
            logger.error("Fan-out execution failed: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Fan-out failed: {str(e)}", error="execution_error")


# Register tool at module level
from harness.tools.registry import registry

registry.register(FanOutTasksTool(), toolset="delegate")
