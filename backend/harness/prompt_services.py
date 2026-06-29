"""Prompt services — tool descriptions, data context, reminders, and skills.

Provides structured access to the 300+ prompt files in ``harness/prompts/``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from harness.prompts import load_prompt

logger = logging.getLogger(__name__)

# ── Tool description mapping ──────────────────────────────────────────

TOOL_DESCRIPTION_MAP: dict[str, list[str]] = {
    "web_search": ["tool-description-websearch"],
    "web_fetch": ["tool-description-webfetch"],
    "read_file": ["tool-description-readfile"],
    "skill_view": ["tool-description-skill"],
    "skill_manage": ["tool-description-skill"],
    "delegate_task": [
        "tool-description-agent-simple-usage-notes",
        "tool-description-agent-usage-notes",
    ],
    "cronjob": ["tool-description-croncreate"],
    "todo": ["tool-description-todowrite", "tool-description-taskcreate"],
}


def get_tool_description(tool_name: str) -> str | None:
    """Return extended usage guidance for a tool, or None."""
    prompts = TOOL_DESCRIPTION_MAP.get(tool_name)
    if not prompts:
        return None
    parts: list[str] = []
    for pname in prompts:
        content = load_prompt(pname)
        if content:
            parts.append(content)
    return "\n\n---\n\n".join(parts) if parts else None


def get_all_tool_descriptions() -> dict[str, str]:
    """Return descriptions for all mapped tools."""
    result: dict[str, str] = {}
    for tool_name in TOOL_DESCRIPTION_MAP:
        desc = get_tool_description(tool_name)
        if desc:
            result[tool_name] = desc
    return result


# ── Data context ──────────────────────────────────────────────────────

DATA_CONTEXT_MAP: dict[str, str] = {
    "tool_use": "data-tool-use-concepts",
    "prompt_caching": "data-prompt-caching-design-optimization",
    "streaming": "data-streaming-reference-python",
    "http_errors": "data-http-error-codes-reference",
}


def get_data_context(topic: str) -> str | None:
    """Return reference data for a given topic, or None."""
    pname = DATA_CONTEXT_MAP.get(topic)
    if not pname:
        return None
    return load_prompt(pname)


# ── Reminders ─────────────────────────────────────────────────────────

_REMINDER_MAP: dict[str, str] = {
    "file_modified": "system-reminder-file-modified-by-user-or-linter",
    "token_usage": "system-reminder-token-usage",
    "plan_active": "system-reminder-plan-mode-is-active-5-phase",
    "plan_file": "system-reminder-plan-file-reference",
    "memory": "system-reminder-memory-file-contents",
    "stopped": "system-reminder-hook-stopped-continuation",
    "diagnostics": "system-reminder-new-diagnostics-detected",
    "budget": "system-reminder-usd-budget",
    "verify": "system-reminder-verify-plan-reminder",
    "compact": "system-reminder-file-truncated",
    "thread_notes": "system-prompt-agent-thread-notes",
    "scratchpad": "system-prompt-scratchpad-directory",
    "context_compaction": "system-prompt-context-compaction-summary",
}


def build_reminders(active_flags: dict[str, bool] | None = None) -> str:
    """Build contextual reminder block based on active flags.

    Args:
        active_flags: Dict mapping reminder keys to whether they should fire.
            e.g. ``{"plan_active": True, "memory": True}``

    Returns:
        Combined reminder text, or empty string if none are active.
    """
    if not active_flags:
        return ""
    parts: list[str] = []
    for key, active in active_flags.items():
        if not active:
            continue
        pname = _REMINDER_MAP.get(key)
        if not pname:
            continue
        content = load_prompt(pname)
        if content:
            parts.append(content)
    return "\n\n".join(parts) if parts else ""


def reminder_for_event(event_type: str, **kwargs: Any) -> str | None:
    """Return a single reminder for a specific runtime event.

    Args:
        event_type: One of "file_modified", "token_usage", "plan_active",
                    "plan_file", "memory", "stopped", "diagnostics", "budget".

    Returns:
        Reminder text, or None if no reminder matches.
    """
    pname = _REMINDER_MAP.get(event_type)
    if not pname:
        return None
    return load_prompt(pname)


# ── Skills from prompt library ────────────────────────────────────────

def list_prompt_skills() -> list[dict[str, str]]:
    """List all skill files from the prompt library as loadable skills."""
    skills_dir = Path(__file__).resolve().parent / "prompts"
    result: list[dict[str, str]] = []
    for path in sorted(skills_dir.glob("skill-*.md")):
        name = path.stem.replace("skill-", "", 1)
        try:
            content = path.read_text("utf-8").strip()
            first_line = content.split("\n")[0] if content else ""
            desc = first_line.lstrip("#").strip() if first_line.startswith("#") else name
            result.append({"name": name, "description": desc, "content": content})
        except Exception:
            pass
    return result
