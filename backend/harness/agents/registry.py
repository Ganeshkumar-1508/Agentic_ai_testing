"""Agent Registry — filesystem-first, DB-mirrored.

Resolution order (matches CONTEXT.md):
  1. DB user-created agents (via UI)
  2. .testai/agents/_custom/ (project overrides)
  3. .testai/agents/ (built-in)
  4. agent_workspace/agents/ (legacy markdown)

The registry syncs filesystem changes to the DB on startup and on file watch.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from harness.agents.spec import yaml_to_agent_def
from harness.store.protocols import AgentDef

logger = logging.getLogger(__name__)

# Search paths in priority order (first match wins)
_SEARCH_PATHS: list[tuple[str, str]] = [
    ("project_custom", ".testai/agents/_custom/"),
    ("builtin", ".testai/agents/"),
    ("legacy", "agent_workspace/agents/"),
]


def _find_agent_files(project_root: str) -> list[tuple[str, str, str]]:
    """Return (source_label, role_name, file_path) for every agent definition found."""
    found: list[tuple[str, str, str]] = []
    seen_roles: set[str] = set()

    for source_label, rel_path in _SEARCH_PATHS:
        abs_path = os.path.join(project_root, rel_path)
        if not os.path.isdir(abs_path):
            continue
        for entry in sorted(os.listdir(abs_path)):
            if not entry.endswith((".yaml", ".yml", ".md")):
                continue
            role = Path(entry).stem
            if role in seen_roles:
                continue
            seen_roles.add(role)
            found.append((source_label, role, os.path.join(abs_path, entry)))

    return found


class AgentRegistry:
    """Filesystem-first agent definition source.

    On init, scans all search paths and syncs to AgentStore.
    Provides resolve() for orchestrator to look up agents by role or trigger.
    """

    def __init__(self, store, project_root: str = "."):
        self._store = store
        self._project_root = project_root

    async def sync_from_filesystem(self) -> int:
        """Scan filesystem and upsert all agent definitions into DB. Returns count."""
        found = _find_agent_files(self._project_root)
        count = 0
        for source_label, role, file_path in found:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                agent = yaml_to_agent_def(content, source_path=file_path, source=source_label)
                agent.role = role
                await self._store.upsert_agent(agent)
                count += 1
            except Exception as e:
                logger.warning("Failed to load agent %s from %s: %s", role, file_path, e)
        return count

    async def resolve(self, role: str) -> AgentDef | None:
        """Resolve an agent by role name. DB-first, then filesystem."""
        agent = await self._store.get_agent(role)
        if agent:
            return agent
        # Filesystem fallback: scan for the role
        found = _find_agent_files(self._project_root)
        for source_label, r, file_path in found:
            if r == role:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    agent = yaml_to_agent_def(content, source_path=file_path, source=source_label)
                    agent.role = role
                    return agent
                except Exception as e:
                    logger.warning("Failed to load agent %s: %s", role, e)
                    return None
        return None

    async def resolve_by_triggers(self, goal: str) -> list[AgentDef]:
        """Match task goal text against agent triggers. Returns ranked matches."""
        return await self._store.resolve_by_trigger(goal)

    async def list_agents(self) -> list[AgentDef]:
        """List all known agents from DB."""
        return await self._store.list_agents()
