from __future__ import annotations

from typing import Any

import yaml

from harness.store.protocols import AgentDef


def agent_def_to_yaml(agent: AgentDef) -> str:
    """Serialize an AgentDef to a YAML string (matches orchestrator-pipeline-design.md Q10 format)."""
    data = {
        "role": agent.role,
        "version": agent.version,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "allowed_tools": agent.allowed_tools,
        "allowed_skills": agent.allowed_skills,
        "model": {
            "primary": agent.model_primary,
            "fallback": agent.model_fallback,
        } if agent.model_primary or agent.model_fallback else None,
        "delegation_depth": agent.delegation_depth,
        "delegation_role": agent.delegation_role,
        "triggers": agent.triggers or None,
        "bash_constraints": agent.bash_constraints or None,
        "output_contract": agent.output_contract or None,
    }
    data = {k: v for k, v in data.items() if v is not None and v != [] and v != {}}
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True).strip()


def yaml_to_agent_def(yaml_str: str, source_path: str = "", source: str = "user") -> AgentDef:
    """Parse a YAML string into an AgentDef."""
    data = yaml.safe_load(yaml_str) or {}
    model = data.get("model", {}) or {}
    return AgentDef(
        role=data.get("role", data.get("name", "")),
        version=data.get("version", 1),
        description=data.get("description", ""),
        system_prompt=_extract_prompt(yaml_str, data),
        allowed_tools=data.get("allowed_tools", data.get("tools", [])),
        allowed_skills=data.get("allowed_skills", data.get("skills", [])),
        model_primary=model.get("primary", data.get("model_primary", "")),
        model_fallback=model.get("fallback", data.get("model_fallback", "")),
        delegation_depth=data.get("delegation_depth", 1),
        delegation_role=data.get("delegation_role", "leaf"),
        triggers=data.get("triggers", []),
        bash_constraints=data.get("bash_constraints", data.get("constraints", {})),
        output_contract=data.get("output_contract", ""),
        source=source,
    )


def _extract_prompt(yaml_str: str, parsed: dict) -> str:
    """Extract the prompt body — after frontmatter if present, else from 'system_prompt' or 'prompt' field."""
    if parsed.get("system_prompt"):
        return parsed["system_prompt"]
    if parsed.get("prompt"):
        return parsed["prompt"]
    # Try to find content after YAML frontmatter (--- ... ---)
    if yaml_str.startswith("---"):
        parts = yaml_str.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return parsed.get("description", "")
