"""Auto-discover and load agent definitions from filesystem directories.

Scans built-in agents directory first, then an optional single override
directory. Each .md file with YAML frontmatter is a complete agent
definition (config + system prompt).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from harness.agent_config import AgentConfig, AgentStore

logger = logging.getLogger(__name__)

DEFAULT_AGENT = "general-purpose"

_AGENTS_DIR = Path(__file__).resolve().parent / "agents"
_OVERRIDE_DIR = Path(".testai") / "agents"

# Registered tool names in the tool registry. Used to warn when an agent
# YAML references a name that doesn't match (common pitfall: "read" vs
# "read_file", "list" vs "list_files", "write" vs "write_file",
# "edit" vs "edit_file").
_KNOWN_TOOLS: set[str] | None = None


def _get_known_tools() -> set[str]:
    global _KNOWN_TOOLS
    if _KNOWN_TOOLS is None:
        try:
            from harness.tools.registry import registry
            _KNOWN_TOOLS = {e.name for e in registry.list_entries()}
        except Exception:
            _KNOWN_TOOLS = set()
    return _KNOWN_TOOLS


def discover_agents() -> dict[str, AgentConfig]:
    """Scan built-in + override directories. Override wins on name conflict."""
    agents: dict[str, AgentConfig] = {}

    for agents_dir in [_AGENTS_DIR, _OVERRIDE_DIR]:
        resolved = agents_dir.resolve()
        if not resolved.exists():
            continue
        store = AgentStore(agents_dir=resolved)
        for agent in store.list_agents():
            if agent.disabled:
                agents.pop(agent.name, None)
                continue
            if agent.name in agents:
                logger.warning(
                    "Agent '%s' overrides built-in — source=%s (override wins)",
                    agent.name, resolved,
                )
            agents[agent.name] = agent

    # Warn about mismatched tool names in agent YAMLs
    known = _get_known_tools()
    if known:
        ALIASES = {"read":"read_file","list":"list_files","write":"write_file","edit":"edit_file","patch":"apply_patch"}
        for name, agent in agents.items():
            for t in agent.tools or []:
                if t not in known and t not in ALIASES:
                    logger.warning(
                        "Agent '%s' references unknown tool '%s' — "
                        "did you mean '%s'?", name, t, ALIASES.get(t),
                    )

    return agents


def get_agent(name: str) -> AgentConfig | None:
    """Get an agent definition by name from built-in or override dir."""
    return discover_agents().get(name)


def get_subagent_prompt(agent_name: str, goal: str, context: str = "", allowed_tools: list[str] | None = None) -> str:
    """Build a subagent prompt from an agent definition file.

    Uses the Hermes pattern: load the agent markdown file's system prompt
    (body), then append the goal, context, and available tools.

    Falls back to load_agent_prompt() if no matching agent definition found.
    """
    from harness.prompt_builder import load_agent_prompt, load_system_prompt

    agent = get_agent(agent_name)
    if agent and agent.prompt:
        base = agent.prompt
    else:
        base = load_agent_prompt(agent_name) or load_system_prompt("worker-instructions") or ""

    extra = (
        "## Instructions\n"
        "- Use your tools to complete the task — do not describe what you would do\n"
        "- If you hit an error, diagnose and retry with a different approach\n"
        "- Report: what you did, what you found, files created/changed\n"
        "- Be thorough but concise\n"
    )

    from datetime import datetime, timezone
    parts = [base, extra, f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]
    if allowed_tools:
        parts.append(f"## Available Tools\n{', '.join(sorted(allowed_tools))}")
    if context:
        parts.append(f"## Context\n{context}")
    parts.append(f"## Task\n{goal}")

    return "\n\n".join(parts)
