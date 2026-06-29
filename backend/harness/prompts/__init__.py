"""System prompt library — reusable prompt components.

All prompt files are in this directory. Use ``load_prompt()`` to retrieve
by name, or ``load_category()`` to get all prompts in a category.

Categories (file prefix convention):
  - ``system-prompt-*`` — core system identity and communication rules
  - ``agent-prompt-*`` — sub-agent and slash command prompts
  - ``system-reminder-*`` — contextual reminders injected mid-conversation
  - ``tool-description-*`` — detailed tool usage instructions
  - ``data-*`` — reference data (API docs, model catalogs)
  - ``skill-*`` — reusable workflow skill definitions
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str | None:
    """Load a single prompt by filename (with or without .md extension).

    Args:
        name: Filename like ``"system-prompt-auto-mode"`` or ``"system-prompt-auto-mode.md"``

    Returns:
        File content as string, or None if not found.
    """
    if not name.endswith(".md"):
        name += ".md"
    path = PROMPTS_DIR / name
    if not path.exists():
        return None
    try:
        return path.read_text("utf-8").strip()
    except Exception as e:
        logger.warning("Failed to load prompt %s: %s", name, e)
        return None


def load_category(prefix: str) -> dict[str, str]:
    """Load all prompts whose filename starts with ``prefix``.

    Args:
        prefix: e.g. ``"system-prompt"``, ``"agent-prompt"``, ``"system-reminder"``

    Returns:
        Dict of ``{filename_without_ext: content}``.
    """
    result: dict[str, str] = {}
    for path in sorted(PROMPTS_DIR.glob(f"{prefix}*.md")):
        try:
            content = path.read_text("utf-8").strip()
            if content:
                key = path.stem  # filename without .md
                result[key] = content
        except Exception as e:
            logger.warning("Failed to load %s: %s", path.name, e)
    return result


def load_all() -> dict[str, str]:
    """Load ALL prompt files.

    Returns:
        Dict of ``{filename_without_ext: content}``.
    """
    result: dict[str, str] = {}
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        try:
            content = path.read_text("utf-8").strip()
            if content:
                result[path.stem] = content
        except Exception as e:
            logger.warning("Failed to load %s: %s", path.name, e)
    return result


def build_system_prompt_from_parts(
    mode: str = "auto",
    extra_parts: list[str] | None = None,
) -> str:
    """Build a system prompt from Claude Code prompt parts.

    Assembles relevant system prompts for the given mode.
    """
    parts: list[str] = []

    # Core identity
    identity = load_prompt("system-prompt-communication-style")
    if identity:
        parts.append(identity)

    # Mode-specific
    mode_prompts: dict[str, list[str]] = {
        "auto": ["system-prompt-auto-mode"],
        "plan": ["agent-prompt-plan-mode-enhanced", "system-prompt-phase-four-of-plan-mode"],
        "explore": ["agent-prompt-explore"],
        "batch": ["agent-prompt-batch-slash-command"],
    }
    for pname in mode_prompts.get(mode, []):
        content = load_prompt(pname)
        if content:
            parts.append(content)

    # Core rules
    for rule in [
        "system-prompt-doing-tasks-ambitious-tasks",
        "system-prompt-doing-tasks-software-engineering-focus",
        "system-prompt-doing-tasks-security",
        "system-prompt-doing-tasks-help-and-feedback",
        "system-prompt-doing-tasks-no-compatibility-hacks",
        "system-prompt-doing-tasks-no-unnecessary-error-handling",
        "system-prompt-executing-actions-with-care",
        "system-prompt-action-safety-and-truthful-reporting",
        "system-prompt-parallel-tool-call-note-part-of-tool-usage-policy",
    ]:
        content = load_prompt(rule)
        if content:
            parts.append(content)

    # Extra parts
    if extra_parts:
        for pname in extra_parts:
            content = load_prompt(pname)
            if content:
                parts.append(content)

    return "\n\n---\n\n".join(parts)
