"""Skill Manager — orchestrates the evolution system.

Ties together SessionTracker, SkillEvolver, SkillValidator, and VersionTracker
into a unified interface for the agent.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.skills.session_tracker import get_tracker, SessionTracker
from harness.skills.version_tracker import get_version_tracker, VersionTracker
from harness.skills.evolver import get_evolver, SkillEvolver
from harness.skills.validator import get_validator, SkillValidator

logger = logging.getLogger(__name__)


class SkillManager:
    """Orchestrates skill tracking, evolution, validation, and versioning."""

    def __init__(self) -> None:
        self.tracker: SessionTracker = get_tracker()
        self.versioning: VersionTracker = get_version_tracker()
        self.evolver: SkillEvolver = get_evolver()
        self.validator: SkillValidator = get_validator()

    def get_skill_info(self, skill_name: str) -> dict[str, Any]:
        """Get comprehensive info about a skill."""
        stats = self.tracker.get_stats(skill_name)
        versions = self.versioning.get_versions(skill_name)
        latest_version = self.versioning.get_latest(skill_name)
        validation_history = self.validator.get_history(skill_name, limit=5)
        evolution_history = self.evolver.list_evolution_history(skill_name, )

        return {
            "skill_name": skill_name,
            "usage_stats": stats,
            "version_count": len(versions),
            "latest_version": latest_version,
            "validation_history": validation_history,
            "evolution_count": len(evolution_history),
            "last_evolution": evolution_history[-1] if evolution_history else None,
        }

    def evolve_skill(self, skill_name: str) -> dict[str, Any]:
        """Run the full evolution cycle for a skill."""
        # 1. Analyze
        analysis = self.evolver.analyze(skill_name)
        if analysis["status"] != "ready":
            return analysis

        # 2. Generate candidate
        evolution_result = self.evolver.evolve(skill_name)
        if evolution_result["status"] != "candidate_generated":
            return evolution_result

        # 3. Validate candidate
        candidate_path = evolution_result.get("candidate_path", "")
        if candidate_path:
            from pathlib import Path
            candidate_content = Path(candidate_path).read_text(encoding="utf-8")
            current_content = self._read_current_skill(skill_name)

            # Generate test prompts from error patterns
            error_patterns = analysis.get("error_patterns", [])
            test_prompts = [ep["pattern"] for ep in error_patterns[:5]]
            if not test_prompts:
                test_prompts = [f"How to use {skill_name} effectively"]

            validation = self.validator.validate(
                skill_name=skill_name,
                candidate_content=candidate_content,
                test_prompts=test_prompts,
                current_content=current_content,
            )

            evolution_result["validation"] = {
                "passed": validation.passed,
                "test_count": validation.test_count,
                "pass_count": validation.pass_count,
                "avg_score": validation.avg_score,
            }

        return evolution_result

    def _read_current_skill(self, skill_name: str) -> str:
        from harness.testai_constants import get_testai_home
        skill_path = get_testai_home() / "skills" / skill_name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")
        return ""


# Global singleton
_manager = SkillManager()


def get_skill_manager() -> SkillManager:
    return _manager
