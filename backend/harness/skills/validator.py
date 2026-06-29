"""Skill Validator — tests candidate skills against test prompts.

Runs a candidate SKILL.md against a set of test prompts and evaluates
whether the skill improves the agent's output compared to no-skill baseline.

Validation flow:
  1. Load candidate SKILL.md
  2. For each test prompt:
     a. Run with skill disabled → capture baseline output
     b. Run with skill enabled → capture skill output
     c. Compare outputs (did the skill help?)
  3. Aggregate results → pass/fail verdict
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of one test prompt."""
    prompt: str
    baseline_output: str
    skill_output: str
    improved: bool
    score: float  # 0.0 - 1.0
    notes: str = ""


@dataclass
class ValidationResult:
    """Aggregated validation result."""
    skill_name: str
    passed: bool
    test_count: int
    pass_count: int
    avg_score: float
    tests: list[TestResult] = field(default_factory=list)
    timestamp: str = ""
    duration_ms: int = 0


def _skill_meta_dir(skill_name: str) -> Path:
    from harness.testai_constants import get_testai_home
    return get_testai_home() / "skills" / skill_name / ".evo"


def _validation_file(skill_name: str) -> Path:
    return _skill_meta_dir(skill_name) / "validation.jsonl"


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


class SkillValidator:
    """Tests candidate skills against test prompts."""

    def __init__(self, pass_threshold: float = 0.6, min_tests: int = 3) -> None:
        self.pass_threshold = pass_threshold
        self.min_tests = min_tests

    def validate(
        self,
        skill_name: str,
        candidate_content: str,
        test_prompts: list[str],
        current_content: str | None = None,
    ) -> ValidationResult:
        """Validate a candidate skill against test prompts.

        For now, this does structural validation (not LLM-based comparison).
        LLM-based comparison can be added later as an enhancement.
        """
        start = time.time()
        tests: list[TestResult] = []

        for prompt in test_prompts:
            result = self._evaluate_prompt(skill_name, candidate_content, prompt, current_content)
            tests.append(result)

        pass_count = sum(1 for t in tests if t.improved)
        avg_score = sum(t.score for t in tests) / max(len(tests), 1)
        passed = pass_count >= max(1, len(tests) * self.pass_threshold) and len(tests) >= self.min_tests

        duration_ms = int((time.time() - start) * 1000)
        validation = ValidationResult(
            skill_name=skill_name,
            passed=passed,
            test_count=len(tests),
            pass_count=pass_count,
            avg_score=round(avg_score, 2),
            tests=tests,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
        )

        # Persist result
        try:
            _append_jsonl(_validation_file(skill_name), {
                "timestamp": validation.timestamp,
                "passed": passed,
                "test_count": len(tests),
                "pass_count": pass_count,
                "avg_score": avg_score,
                "duration_ms": duration_ms,
            })
        except Exception as e:
            logger.debug("SkillValidator: failed to persist result for %s: %s", skill_name, e)

        return validation

    def _evaluate_prompt(
        self,
        skill_name: str,
        candidate_content: str,
        prompt: str,
        current_content: str | None,
    ) -> TestResult:
        """Evaluate a single prompt. Structural comparison for now."""
        # Check if candidate has relevant keywords for this prompt
        prompt_words = set(prompt.lower().split())
        candidate_words = set(candidate_content.lower().split())
        overlap = len(prompt_words & candidate_words)
        score = min(1.0, overlap / max(len(prompt_words), 1))

        # Check if candidate is better than current
        improved = True
        if current_content:
            current_words = set(current_content.lower().split())
            current_overlap = len(prompt_words & current_words)
            current_score = min(1.0, current_overlap / max(len(prompt_words), 1))
            improved = score > current_score

        return TestResult(
            prompt=prompt,
            baseline_output=f"[structural analysis: {overlap} word overlap]",
            skill_output=f"[structural analysis: {overlap} word overlap]",
            improved=improved,
            score=round(score, 2),
            notes=f"Keyword overlap: {overlap}/{len(prompt_words)}",
        )

    def get_history(self, skill_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get validation history for a skill."""
        path = _validation_file(skill_name)
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
        return entries[-limit:]


# Global singleton
_validator = SkillValidator()


def get_validator() -> SkillValidator:
    return _validator
