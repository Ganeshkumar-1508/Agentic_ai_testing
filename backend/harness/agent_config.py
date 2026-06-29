"""Agent configuration — load/save agent definitions as markdown files with YAML frontmatter.

Follows the same pattern as OpenHands microagents and OpenCode agent markdown files.
Agents are stored in `/app/agent_workspace/agents/` (persistent on host).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

AGENTS_DIR = Path(os.environ.get("AGENT_WORKSPACE_MOUNT", "/app/agent_workspace")) / "agents"

# Default agent definitions reference existing Claude Code prompt files
# instead of embedding inline text. Each entry maps a role to a prompt file
# in harness/prompts/ via prompt_for_role().
_DEFAULT_AGENT_META: dict[str, dict[str, Any]] = {}
# Auto-populated on first use from agent-prompt-*.md files in
# harness/prompts/ plus agents/*.txt in TESTAI_HOME/prompts/agents/.
# See _agent_meta_autodiscover() below.


def _agent_meta_autodiscover(force: bool = False) -> dict[str, dict[str, Any]]:
    """Scan prompt directories and auto-discover all known agents.

    Resolution order:
      1. Agents in TESTAI_HOME/prompts/agents/*.txt (user-custom)
      2. Built-in agent-prompt-*.md files in harness/prompts/

    Returns a ``{role_name: meta}`` dict that mirrors the old
    ``_DEFAULT_AGENT_META`` shape.
    """
    from harness.prompts import load_prompt, PROMPTS_DIR

    meta: dict[str, dict[str, Any]] = {}

    # 1. User-custom agent .txt files under TESTAI_HOME/prompts/agents/
    testai_home = os.environ.get("TESTAI_HOME", "/app/.testai")
    custom_dir = Path(testai_home) / "prompts" / "agents"
    if custom_dir.is_dir():
        for fpath in sorted(custom_dir.glob("*.txt")):
            name = fpath.stem
            meta[name] = {
                "description": f"Custom agent: {name.replace('-', ' ').title()}",
                "model": "",  # Empty = use default model; user can override via API
                "tools": ["read", "write", "glob", "grep", "bash", "edit"],
                "triggers": [name.replace("-", " ").lower()],
                "_prompt_file": str(fpath),
                "_is_custom": True,
            }

    # 2. Built-in agent-prompt-*.md files
    for fpath in sorted(PROMPTS_DIR.glob("agent-prompt-*.md")):
        name = fpath.stem[len("agent-prompt-"):]
        if name in meta:
            continue
        desc = name.replace("-", " ").title()
        meta[name] = {
            "description": desc,
            "model": "",  # Empty = use default model; user can override via API
            "tools": ["read", "glob", "grep"],
            "triggers": [name.replace("-", " ").lower()],
            "_prompt_file": str(fpath),
            "_is_custom": False,
        }

    return meta


def _prompt_for_role(name: str) -> str:
    """Return the prompt text for *name*.

    Tries, in order:
      1. ``agent-prompt-{name}.md`` in the built-in prompts dir
      2. ``{name}.txt`` in TESTAI_HOME/prompts/agents/
      3. A generic fallback
    """
    from harness.prompts import load_prompt, PROMPTS_DIR

    # Try built-in prompt file (harness/prompts/agent-prompt-{name}.md)
    builtin = load_prompt(f"agent-prompt-{name}")
    if builtin:
        return builtin

    # Try TESTAI_HOME/prompts/agents/{name}.txt
    testai_home = os.environ.get("TESTAI_HOME", "/app/.testai")
    custom_path = Path(testai_home) / "prompts" / "agents" / f"{name}.txt"
    if custom_path.exists():
        try:
            return custom_path.read_text("utf-8").strip()
        except Exception:
            pass

    # Generic fallback
    return f"You are a {name.replace('-', ' ')}. Complete the task using your tools."


@dataclass
class AgentConfig:
    name: str
    description: str = ""
    model: str = ""
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    mode: str = "subagent"
    prompt: str = ""
    color: str = ""
    temperature: float = 0.3
    max_steps: int = 20
    disabled: bool = False
    # Q5: toolsets the role is allowed to use. If empty, the orchestrator
    # applies the curated default for the agent's mode (coordinator uses
    # "coordinator", subagents inherit "bug-fixer" / "test-writer" / etc.).
    # The user can override per-role via the AgentsSettings UI.
    toolsets: list[str] = field(default_factory=list)
    # Delegation: matches AgentDef from the YAML Role system.
    # Depth controls how many levels of subagents this agent can spawn.
    # Role determines whether it can delegate at all.
    delegation_depth: int = 1
    delegation_role: str = "leaf"

    def to_markdown(self) -> str:
        frontmatter = []
        frontmatter.append("---")
        frontmatter.append(f"name: {self.name}")
        frontmatter.append(f"description: {self.description}")
        if self.model:
            frontmatter.append(f"model: {self.model}")
        frontmatter.append(f"tools: {json.dumps(self.tools)}")
        if self.disallowed_tools:
            frontmatter.append(f"disallowed_tools: {json.dumps(self.disallowed_tools)}")
        frontmatter.append(f"skills: {json.dumps(self.skills)}")
        frontmatter.append(f"triggers: {json.dumps(self.triggers)}")
        frontmatter.append(f"mode: {self.mode}")
        if self.toolsets:
            frontmatter.append(f"toolsets: {json.dumps(self.toolsets)}")
        frontmatter.append(f"delegation_depth: {self.delegation_depth}")
        frontmatter.append(f"delegation_role: {self.delegation_role}")
        if self.color:
            frontmatter.append(f"color: {self.color}")
        frontmatter.append(f"temperature: {self.temperature}")
        frontmatter.append(f"max_steps: {self.max_steps}")
        frontmatter.append(f"disabled: {str(self.disabled).lower()}")
        frontmatter.append("---")
        frontmatter.append("")
        frontmatter.append(self.prompt)
        return "\n".join(frontmatter)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_markdown(cls, content: str) -> AgentConfig:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
        if not match:
            return cls(name="unknown", prompt=content[:500])
        frontmatter = match.group(1)
        prompt = match.group(2).strip()
        cfg: dict[str, Any] = {"name": "unknown", "prompt": prompt or ""}
        # Normalise Hermes-style frontmatter keys to Python field names
        _KEY_MAP = {
            "disallowedTools": "disallowed_tools",
            "disallowed_tools": "disallowed_tools",
        }
        # State machine: handles inline JSON, inline comma-lists, and YAML block-lists.
        _KEY_MAP.update({
            "delegationRole": "delegation_role",
            "delegationDepth": "delegation_depth",
            "delegation-depth": "delegation_depth",
            "delegation-role": "delegation_role",
        })
        list_keys = {"tools", "skills", "triggers", "disallowed_tools", "toolsets"}
        current_list_key: str | None = None
        for raw_line in frontmatter.split("\n"):
            if current_list_key is not None and raw_line.startswith("  - "):
                item = raw_line[4:].strip()
                if item.startswith("[") and item.endswith("]"):
                    try:
                        cfg[current_list_key].extend(json.loads(item))
                        continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                cfg[current_list_key].append(item.strip('"').strip("'"))
                continue
            current_list_key = None
            if ":" not in raw_line:
                continue
            key, _, val = raw_line.partition(":")
            key = key.strip()
            val = val.strip()
            key = _KEY_MAP.get(key, key)
            if key == "model":
                cfg[key] = val.strip('"').strip("'")
            elif key in list_keys:
                if val.startswith("["):
                    try:
                        cfg[key] = json.loads(val)
                        continue
                    except (json.JSONDecodeError, TypeError):
                        val = val.strip("[]")
                if val == "":
                    cfg[key] = []
                    current_list_key = key
                else:
                    cfg[key] = [v.strip().strip('"').strip("'") for v in val.split(",") if v.strip()]
            elif key in ("temperature",):
                try:
                    cfg[key] = float(val)
                except ValueError:
                    cfg[key] = 0.3
            elif key in ("delegation_depth",):
                try:
                    cfg[key] = int(val)
                except ValueError:
                    cfg[key] = 1
            elif key in ("delegation_role",):
                cfg[key] = val.strip('"').strip("'") if val else "leaf"
            elif key in ("max_steps",):
                try:
                    cfg[key] = int(val)
                except ValueError:
                    cfg[key] = 20
            elif key == "disabled":
                cfg[key] = val.lower() == "true"
            elif key:
                cfg[key] = val
        return cls(**cfg)


class AgentStore:
    """Load/save agent configs from the agent_workspace filesystem."""

    def __init__(self, agents_dir: str | Path | None = None):
        self._dir = Path(agents_dir) if agents_dir else AGENTS_DIR

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_agents(self) -> list[AgentConfig]:
        self._ensure_dir()
        agents = []
        for fpath in sorted(self._dir.glob("*.md")):
            try:
                content = fpath.read_text(encoding="utf-8")
                agent = AgentConfig.from_markdown(content)
                agents.append(agent)
            except Exception:
                continue
        # Seed defaults if empty
        if not agents:
            self._seed_defaults()
            return self.list_agents()
        return agents

    def get_agent(self, name: str) -> AgentConfig | None:
        for agent in self.list_agents():
            if agent.name == name:
                return agent
        return None

    def save_agent(self, agent: AgentConfig) -> None:
        self._ensure_dir()
        fpath = self._dir / f"{agent.name}.md"
        fpath.write_text(agent.to_markdown(), encoding="utf-8")

    def delete_agent(self, name: str) -> bool:
        fpath = self._dir / f"{name}.md"
        if fpath.exists():
            fpath.unlink()
            return True
        return False

    def _seed_defaults(self) -> None:
        self._ensure_dir()
        meta = _agent_meta_autodiscover()
        if not meta:
            return
        for name, meta_entry in meta.items():
            prompt = _prompt_for_role(name)
            tools = meta_entry.get("tools", ["read", "glob", "grep"])
            triggers = meta_entry.get("triggers", [name.replace("-", " ").lower()])
            md_content = (
                f"---\nname: {name}\ndescription: {meta_entry['description']}\n"
                f"tools: {json.dumps(tools)}\nskills: []\n"
                f"triggers: {json.dumps(triggers)}\nmode: subagent\n---\n"
                f"{prompt}"
            )
            agent = AgentConfig.from_markdown(md_content)
            self.save_agent(agent)

    def resolve_by_triggers(self, goal: str) -> list[AgentConfig]:
        """Match task goal text against agent triggers. Returns ranked matches."""
        q = goal.lower()
        matched = []
        for agent in self.list_agents():
            if agent.disabled:
                continue
            if any(t.lower() in q for t in agent.triggers):
                matched.append(agent)
        return matched

    async def sync_to_db(self, agent_store: Any) -> int:
        """Sync all filesystem agents to DB (AgentStore protocol)."""
        from harness.store.protocols import AgentDef
        count = 0
        for agent in self.list_agents():
            if agent.disabled:
                continue
            ad = AgentDef(
                role=agent.name,
                description=agent.description,
                system_prompt=agent.prompt,
                allowed_tools=agent.tools,
                allowed_skills=agent.skills,
                triggers=agent.triggers,
                source="builtin",
            )
            await agent_store.upsert_agent(ad)
            count += 1
        return count
