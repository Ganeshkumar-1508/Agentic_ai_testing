"""Plan mode tools -- OpenHarness-inspired read-only mode toggle.

Allows agents to explicitly switch between read-only (plan/explore) and
read-write (implement) modes. Mirrors enter_plan_mode/exit_plan_mode
from OpenHarness, adapted for TestAI's permission system.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_PLAN_MODE_ACTIVE: bool = False
"""Module-level flag. When True, write/batch tools should reject calls."""


def is_plan_mode() -> bool:
    """Check if plan mode is currently active."""
    return _PLAN_MODE_ACTIVE


class EnterPlanModeTool(BaseTool):
    name = "enter_plan_mode"
    description = (
        "Switch to read-only plan mode. While in plan mode, you can read files, "
        "search the codebase, and explore -- but you CANNOT write, edit, or execute "
        "destructive commands. Use this before planning or analyzing. "
        "Call exit_plan_mode when you are ready to implement."
    )

    async def run(self, **kwargs: Any) -> ToolResult:
        global _PLAN_MODE_ACTIVE
        _PLAN_MODE_ACTIVE = True
        logger.info("Plan mode activated")
        return ToolResult(
            success=True,
            output="Plan mode activated. Read-only. Call exit_plan_mode to resume implementation.",
            data={"plan_mode": True},
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={"type": "object", "properties": {}},
        )


class ExitPlanModeTool(BaseTool):
    name = "exit_plan_mode"
    description = "Exit plan mode and return to read-write mode. Call this when you are ready to implement."

    async def run(self, **kwargs: Any) -> ToolResult:
        global _PLAN_MODE_ACTIVE
        _PLAN_MODE_ACTIVE = False
        logger.info("Plan mode deactivated")
        return ToolResult(
            success=True,
            output="Plan mode deactivated. You can now write code and run commands.",
            data={"plan_mode": False},
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={"type": "object", "properties": {}},
        )


# Register tools at module level so discover_tools picks them up
from harness.tools.registry import register as _register  # noqa: E402
_register(EnterPlanModeTool())
_register(ExitPlanModeTool())
