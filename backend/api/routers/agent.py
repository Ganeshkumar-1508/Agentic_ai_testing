"""Agent CRUD — list, create, get, check, delete custom agents.

Agents are stored as .md files with YAML frontmatter in:
  1. .testai/agents/_custom/  (user-created via UI)
  2. harness/agents/          (built-in)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harness.agent_config import AgentStore

router = APIRouter(prefix="/api/agents", tags=["agents"])

CUSTOM_DIR = Path(".testai") / "agents" / "_custom"


class AgentOut(BaseModel):
    name: str
    description: str
    model: str | None = None
    tools: list[str] = []
    skills: list[str] = []
    prompt: str = ""


class CreateAgentIn(BaseModel):
    name: str
    description: str = ""
    model: str | None = None
    tools: list[str] = []
    skills: list[str] = []
    prompt: str = ""


def _all_agents() -> list[dict[str, Any]]:
    """Return all agents from built-in + custom dirs."""
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    for agents_dir in [Path("harness/agents"), CUSTOM_DIR]:
        if not agents_dir.exists():
            continue
        store = AgentStore(agents_dir=agents_dir)
        for agent in store.list_agents():
            if agent.name in seen:
                continue
            seen.add(agent.name)
            results.append({
                "name": agent.name,
                "description": agent.description,
                "model": agent.model or None,
                "tools": agent.tools,
                "skills": agent.skills,
                "prompt": agent.prompt,
            })
    return results


@router.get("")
async def list_agents() -> dict[str, list[dict[str, Any]]]:
    return {"agents": _all_agents()}


@router.get("/check")
async def check_agent_name(name: str) -> dict[str, bool | str]:
    if not name:
        raise HTTPException(400, "name is required")
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    store = AgentStore(agents_dir=CUSTOM_DIR)
    existing = store.get_agent(name)
    return {"available": existing is None, "name": name}


@router.get("/{name}")
async def get_agent(name: str) -> dict[str, Any]:
    for entry in _all_agents():
        if entry["name"] == name:
            return entry
    raise HTTPException(404, "Agent not found")


@router.post("", status_code=201)
async def create_agent(body: CreateAgentIn) -> dict[str, Any]:
    if not body.name.strip():
        raise HTTPException(400, "name is required")

    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    store = AgentStore(agents_dir=CUSTOM_DIR)

    if store.get_agent(body.name):
        raise HTTPException(409, "Agent already exists")

    from harness.agent_config import AgentConfig

    agent = AgentConfig(
        name=body.name,
        description=body.description or f"Custom agent: {body.name}",
        model=body.model or "",
        tools=body.tools or ["codegraph_explore", "grep", "read", "bash", "edit", "write"],
        skills=body.skills or [],
        prompt=body.prompt or body.description or "",
    )
    store.save_agent(agent)
    return {
        "name": agent.name,
        "description": agent.description,
        "model": agent.model or None,
        "tools": agent.tools,
        "skills": agent.skills,
        "prompt": agent.prompt,
    }


@router.delete("/{name}")
async def delete_agent(name: str) -> dict[str, bool]:
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    store = AgentStore(agents_dir=CUSTOM_DIR)
    if not store.delete_agent(name):
        raise HTTPException(404, "Agent not found")
    return {"deleted": True}
