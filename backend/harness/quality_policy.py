"""Quality Policy — org-wide agent instructions injected into every system prompt.

Pattern: Mabl Agent Instructions. Team quality standards encoded once,
auto-applied to every agent, every test, every failure analysis.

The policy is a YAML document at workspace/org level loaded at startup.
Every spawned agent gets it injected into the system prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityPolicy:
    """Persistent quality standards that apply to all agents in the org.

    Loaded from ``.testai/quality.yaml`` (project) or
    ``~/.testai/quality.yaml`` (global).
    """
    # Free-text guidelines prepended to every agent's system prompt
    guidelines: list[str] = field(default_factory=lambda: [
        "Write tests that match the project's existing test style.",
        "Prefer readable, maintainable tests over clever one-liners.",
        "Verify edge cases: empty states, error states, boundary values.",
        "Follow the existing project conventions for test naming and structure.",
    ])

    # Test standards — language/framework-specific conventions
    test_standards: dict[str, Any] = field(default_factory=lambda: {
        "assertion_style": "explicit",  # "explicit" or "fluent"
        "max_test_length_lines": 100,
        "prefer_parametrized": True,
        "naming_convention": "test_<unit>_<scenario>_<expected>",
    })

    # Recovery preferences — how agents should handle failures
    recovery_preferences: dict[str, Any] = field(default_factory=lambda: {
        "retry_transient": True,
        "max_retries": 2,
        "replan_on_failure": True,
        "escalate_on": ["permission_denied", "budget_exceeded"],
    })

    # Review criteria — checks before marking work complete
    review_criteria: list[str] = field(default_factory=lambda: [
        "All tests pass.",
        "No debug code or print statements.",
        "Secrets and credentials are not committed.",
        "Test files follow project naming conventions.",
    ])

    def build_prompt_block(self) -> str:
        """Build the instruction block injected into agent system prompts."""
        parts = ["## Quality Standards", ""]

        if self.guidelines:
            parts.append("### Guidelines")
            for g in self.guidelines:
                parts.append(f"- {g}")
            parts.append("")

        if self.test_standards:
            parts.append("### Test Standards")
            for k, v in self.test_standards.items():
                parts.append(f"- {k}: {v}")
            parts.append("")

        if self.recovery_preferences:
            parts.append("### Recovery")
            for k, v in self.recovery_preferences.items():
                parts.append(f"- {k}: {v}")
            parts.append("")

        if self.review_criteria:
            parts.append("### Final Review Checklist")
            parts.extend(f"- [ ] {c}" for c in self.review_criteria)
            parts.append("")

        return "\n".join(parts)

    @classmethod
    def load(cls) -> QualityPolicy:
        """Load policy from disk, or return defaults if not configured."""
        import os
        from pathlib import Path

        # Try project-level first
        for base in (Path.cwd(), Path.home()):
            path = base / ".testai" / "quality.yaml"
            if path.exists():
                try:
                    import yaml
                    with open(path) as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return cls(
                            guidelines=data.get("guidelines", cls.guidelines),
                            test_standards=data.get("test_standards", cls.test_standards),
                            recovery_preferences=data.get("recovery_preferences", cls.recovery_preferences),
                            review_criteria=data.get("review_criteria", cls.review_criteria),
                        )
                except Exception as exc:
                    logger.warning("Failed to load quality policy from %s: %s", path, exc)

        return cls()


_policy: QualityPolicy | None = None


def get_quality_policy() -> QualityPolicy:
    """Get the cached quality policy, loading it on first access."""
    global _policy
    if _policy is None:
        _policy = QualityPolicy.load()
    return _policy


def reload_quality_policy() -> None:
    """Force reload the policy from disk (for hot-reload)."""
    global _policy
    _policy = QualityPolicy.load()
