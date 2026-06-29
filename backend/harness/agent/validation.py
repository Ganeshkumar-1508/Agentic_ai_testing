"""Subagent output validation — sanity-check a subagent's output before
passing it back to the parent.

Per Microsoft AI Agent Patterns (2026): "Validate agent output before
passing to next agent — prevent cascading errors." Per AOrchestra (2026):
"output quality variance is a top failure mode for fan-out delegation."

Catches: empty outputs, error markers leaking through, oversized outputs,
control-character garbage. Returns a structured result so the parent
can decide what to do (retry, escalate, or proceed with the issue noted).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["ValidationResult", "validate_subagent_output"]


MAX_OUTPUT_LEN = 50_000


@dataclass
class ValidationResult:
    """Result of validating a subagent's output."""
    valid: bool
    issues: list[str] = field(default_factory=list)
    sanitized: str = ""

    def __bool__(self) -> bool:
        return self.valid


def validate_subagent_output(
    output: Any, expected_kind: str = "text",
) -> ValidationResult:
    """Sanity-check a subagent's output string.

    `output` may be any type — coerced to str. `expected_kind` is reserved
    for future format-specific validation (e.g. "json", "markdown"); only
    "text" is implemented today.

    Returns a `ValidationResult` with the issues found and a sanitized copy
    of the output (truncated if oversized).
    """
    issues: list[str] = []
    text = str(output or "")

    if not text:
        issues.append("empty")
        return ValidationResult(valid=False, issues=issues, sanitized="")

    if text.startswith(("Error:", "Exception:", "Traceback")):
        issues.append("error_prefix")

    if len(text) > MAX_OUTPUT_LEN:
        issues.append("too_long")
        text = text[:MAX_OUTPUT_LEN] + "\n...[truncated]"

    # Reject control-character garbage in the first 1KB (allow \n, \t)
    head = text[:1000]
    if any(ord(c) < 32 and c not in "\n\t" for c in head):
        issues.append("control_chars")

    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
        sanitized=text,
    )
