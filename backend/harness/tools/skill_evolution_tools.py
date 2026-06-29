"""Skill evolution tools — agent-facing interface for the evolution system.

Tools:
  - skill_info: Get comprehensive info about a skill (usage, versions, validation)
  - skill_evolve: Run evolution cycle for a skill (analyze → candidate → validate)
  - skill_versions: List version history for a skill
  - skill_stats: Get usage statistics for a skill
"""

from __future__ import annotations

import json
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


class SkillInfoTool(BaseTool):
    """Get comprehensive info about a skill."""

    name = "skill_info"
    description = (
        "Get comprehensive info about a skill: usage stats, version history, "
        "validation results, and evolution history."
    )
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to inspect",
                    },
                },
                "required": ["skill_name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        skill_name = kwargs.get("skill_name", "")
        if not skill_name:
            return ToolResult(success=False, output="skill_name is required", error="missing_arg")

        try:
            from harness.skills.manager import get_skill_manager
            manager = get_skill_manager()
            info = manager.get_skill_info(skill_name)
            return ToolResult(success=True, output=json.dumps(info, indent=2, default=str))
        except Exception as e:
            logger.error("skill_info failed: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to get skill info: {e}", error="internal_error")


class SkillEvolveTool(BaseTool):
    """Run evolution cycle for a skill."""

    name = "skill_evolve"
    description = (
        "Run the full evolution cycle for a skill: analyze session data, "
        "generate improvement candidate, validate against test prompts. "
        "The candidate is saved but not automatically applied — review it first."
    )
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to evolve",
                    },
                },
                "required": ["skill_name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        skill_name = kwargs.get("skill_name", "")
        if not skill_name:
            return ToolResult(success=False, output="skill_name is required", error="missing_arg")

        try:
            from harness.skills.manager import get_skill_manager
            manager = get_skill_manager()
            result = manager.evolve_skill(skill_name)
            return ToolResult(success=True, output=json.dumps(result, indent=2, default=str))
        except Exception as e:
            logger.error("skill_evolve failed: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Failed to evolve skill: {e}", error="internal_error")


class SkillVersionsTool(BaseTool):
    """List version history for a skill."""

    name = "skill_versions"
    description = "List version history for a skill, showing when it was last changed and by whom."
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill",
                    },
                },
                "required": ["skill_name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        skill_name = kwargs.get("skill_name", "")
        if not skill_name:
            return ToolResult(success=False, output="skill_name is required", error="missing_arg")

        try:
            from harness.skills.version_tracker import get_version_tracker
            tracker = get_version_tracker()
            versions = tracker.get_versions(skill_name)
            if not versions:
                return ToolResult(success=True, output=f"No version history for '{skill_name}'")
            lines = [f"## {len(versions)} version(s) for '{skill_name}'\n"]
            for v in versions:
                lines.append(
                    f"  v{v['version']} — {v['timestamp'][:16]} "
                    f"({v.get('source', 'unknown')}) "
                    f"[{v.get('lines', '?')} lines]"
                )
                if v.get("summary"):
                    lines.append(f"    {v['summary']}")
            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to get versions: {e}", error="internal_error")


class SkillStatsTool(BaseTool):
    """Get usage statistics for a skill."""

    name = "skill_stats"
    description = "Get usage statistics: success rate, avg duration, error count, last used."
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill",
                    },
                },
                "required": ["skill_name"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        skill_name = kwargs.get("skill_name", "")
        if not skill_name:
            return ToolResult(success=False, output="skill_name is required", error="missing_arg")

        try:
            from harness.skills.session_tracker import get_tracker
            tracker = get_tracker()
            stats = tracker.get_stats(skill_name)
            sessions = tracker.get_sessions(skill_name, limit=5)
            lines = [f"## Stats for '{skill_name}'\n"]
            lines.append(f"  Total sessions: {stats['total']}")
            lines.append(f"  Success rate: {stats['success_rate']:.0%}")
            lines.append(f"  Avg duration: {stats['avg_duration_ms']}ms")
            lines.append(f"  Total errors: {stats['total_errors']}")
            if stats.get("last_used"):
                lines.append(f"  Last used: {stats['last_used'][:16]}")
            if sessions:
                lines.append(f"\n## Recent sessions (last {len(sessions)})")
                for s in sessions:
                    icon = "✓" if s.get("success") else "✗"
                    lines.append(
                        f"  {icon} {s['timestamp'][:16]} — "
                        f"{s.get('duration_ms', 0)}ms, "
                        f"{s.get('tool_calls', 0)} tools, "
                        f"{len(s.get('errors', []))} errors"
                    )
            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to get stats: {e}", error="internal_error")


# Register tools
registry.register(SkillInfoTool(), toolset="read")
registry.register(SkillEvolveTool(), toolset="read")
registry.register(SkillVersionsTool(), toolset="read")
registry.register(SkillStatsTool(), toolset="read")
