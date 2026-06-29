"""Skill Evolver — analyzes session data, generates improved skill candidates.

The evolver reads session logs for a skill, identifies patterns (what worked,
what failed), and generates an improved SKILL.md candidate.

Evolution flow:
  1. Read session logs for the skill
  2. Analyze success/failure patterns
  3. Identify improvement opportunities
  4. Generate candidate SKILL.md with improvements
  5. Return candidate for validation

The evolver is designed to be called periodically (like Hermes's curator)
or on-demand via the `skill_evolve` tool.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _skill_meta_dir(skill_name: str) -> Path:
    from harness.testai_constants import get_testai_home
    return get_testai_home() / "skills" / skill_name / ".evo"


def _candidates_dir(skill_name: str) -> Path:
    return _skill_meta_dir(skill_name) / "candidates"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _read_skill_md(skill_name: str) -> str:
    from harness.testai_constants import get_testai_home
    skill_path = get_testai_home() / "skills" / skill_name / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return ""


class SkillEvolver:
    """Analyzes session data and generates improved skill candidates."""

    def __init__(self, min_sessions: int = 3, improvement_threshold: float = 0.3) -> None:
        self.min_sessions = min_sessions
        self.improvement_threshold = improvement_threshold

    def analyze(self, skill_name: str) -> dict[str, Any]:
        """Analyze session data for a skill and return improvement opportunities."""
        from harness.skills.session_tracker import get_tracker
        tracker = get_tracker()

        sessions = tracker.get_sessions(skill_name, limit=100)
        stats = tracker.get_stats(skill_name)

        if len(sessions) < self.min_sessions:
            return {
                "skill_name": skill_name,
                "status": "insufficient_data",
                "session_count": len(sessions),
                "message": f"Need {self.min_sessions}+ sessions to analyze (have {len(sessions)})",
            }

        # Analyze patterns
        failed_sessions = [s for s in sessions if not s.get("success")]
        error_patterns = self._extract_error_patterns(failed_sessions)
        success_patterns = self._extract_success_patterns([s for s in sessions if s.get("success")])

        return {
            "skill_name": skill_name,
            "status": "ready",
            "session_count": len(sessions),
            "stats": stats,
            "error_patterns": error_patterns,
            "success_patterns": success_patterns,
            "improvement_opportunities": self._identify_improvements(error_patterns, success_patterns),
        }

    def evolve(self, skill_name: str) -> dict[str, Any]:
        """Generate an improved SKILL.md candidate based on session analysis."""
        analysis = self.analyze(skill_name)

        if analysis["status"] != "ready":
            return analysis

        current_content = _read_skill_md(skill_name)
        if not current_content:
            return {"skill_name": skill_name, "status": "error", "message": "SKILL.md not found"}

        # Generate improved candidate
        candidate = self._generate_candidate(skill_name, current_content, analysis)

        # Save candidate
        candidate_path = _candidates_dir(skill_name) / f"candidate-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text(candidate, encoding="utf-8")

        # Record evolution attempt
        evolution_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skill_name": skill_name,
            "analysis_summary": {
                "sessions": analysis["session_count"],
                "success_rate": analysis["stats"]["success_rate"],
                "error_count": len(analysis["error_patterns"]),
                "improvements": len(analysis["improvement_opportunities"]),
            },
            "candidate_path": str(candidate_path),
        }

        meta_dir = _skill_meta_dir(skill_name)
        meta_dir.mkdir(parents=True, exist_ok=True)
        evolution_log = meta_dir / "evolution.jsonl"
        line = json.dumps(evolution_record, ensure_ascii=False, default=str) + "\n"
        with open(evolution_log, "a", encoding="utf-8") as f:
            f.write(line)

        return {
            "skill_name": skill_name,
            "status": "candidate_generated",
            "candidate_path": str(candidate_path),
            "analysis": analysis,
        }

    def _extract_error_patterns(self, failed_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract common error patterns from failed sessions."""
        error_counts: dict[str, int] = {}
        for session in failed_sessions:
            for error in session.get("errors", []):
                tool = error.get("tool", "unknown")
                err_msg = error.get("error", "")[:100]
                key = f"{tool}: {err_msg}"
                error_counts[key] = error_counts.get(key, 0) + 1

        return [
            {"pattern": pattern, "count": count}
            for pattern, count in sorted(error_counts.items(), key=lambda x: -x[1])
            if count >= 2
        ][:10]

    def _extract_success_patterns(self, successful_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract patterns from successful sessions."""
        tool_usage: dict[str, int] = {}
        for session in successful_sessions:
            # Count tool calls from errors list (tools that were called successfully)
            for error in session.get("errors", []):
                pass  # Errors are failures, not successes
            # Use task_summary for patterns
            summary = session.get("task_summary", "")
            if summary:
                words = re.findall(r'\b\w{4,}\b', summary.lower())
                for word in words[:5]:
                    tool_usage[word] = tool_usage.get(word, 0) + 1

        return [
            {"pattern": word, "count": count}
            for word, count in sorted(tool_usage.items(), key=lambda x: -x[1])
            if count >= 2
        ][:10]

    def _identify_improvements(
        self,
        error_patterns: list[dict[str, Any]],
        success_patterns: list[dict[str, Any]],
    ) -> list[str]:
        """Identify improvement opportunities from patterns."""
        improvements = []

        for ep in error_patterns[:3]:
            improvements.append(f"Address recurring error: {ep['pattern']}")

        if success_patterns:
            top_tools = [sp["pattern"] for sp in success_patterns[:3]]
            improvements.append(f"Emphasize successful patterns: {', '.join(top_tools)}")

        return improvements

    def _generate_candidate(
        self,
        skill_name: str,
        current_content: str,
        analysis: dict[str, Any],
    ) -> str:
        """Generate an improved SKILL.md candidate."""
        # Add evolution header
        header = f"""---
evolved: true
evolved_at: {datetime.now(timezone.utc).isoformat()}
evolution_sessions: {analysis['session_count']}
evolution_success_rate: {analysis['stats']['success_rate']}
---

"""
        # Add improvement notes section
        improvements = analysis.get("improvement_opportunities", [])
        error_patterns = analysis.get("error_patterns", [])

        if improvements or error_patterns:
            notes_section = "\n## Evolution Notes\n\n"
            if error_patterns:
                notes_section += "### Common Errors to Avoid\n"
                for ep in error_patterns[:5]:
                    notes_section += f"- {ep['pattern']} (occurred {ep['count']} times)\n"
            if improvements:
                notes_section += "\n### Improvements Applied\n"
                for imp in improvements:
                    notes_section += f"- {imp}\n"
            notes_section += "\n"

            # Insert notes after the first heading
            lines = current_content.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("# "):
                    insert_idx = i + 1
                    break
            lines.insert(insert_idx, notes_section)
            current_content = "\n".join(lines)

        return header + current_content

    def list_evolution_history(self, skill_name: str) -> list[dict[str, Any]]:
        """Get evolution history for a skill."""
        meta_dir = _skill_meta_dir(skill_name)
        evolution_log = meta_dir / "evolution.jsonl"
        return _read_jsonl(evolution_log)


# Global singleton
_evolver = SkillEvolver()


def get_evolver() -> SkillEvolver:
    return _evolver
