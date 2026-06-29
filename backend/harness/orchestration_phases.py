"""Shared orchestration phases — reusable building blocks for both
OrchestratorEngine.run_single() and pipeline._run_pipeline_orchestrator().

These phases encapsulate the 5 structurally identical steps identified in
the architecture review: sandbox creation, repo cloning, KG indexing,
coordinator goal assembly, and result handling.

Each phase is a standalone async function that receives a context dict
and returns a result dict. The orchestrator and pipeline compose these
phases in their own order, adding path-specific steps between them.

Usage:
    from harness.orchestration_phases import (
        clone_repo,
        index_knowledge_graph,
        assemble_coordinator_goal,
    )

    sandbox = await clone_repo(session_id, repo_url, branch)
    kg = await index_knowledge_graph(sandbox, repo_url, branch)
    goal = assemble_coordinator_goal(base_goal, kg, memory, explore_findings)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CloneResult:
    success: bool
    workspace_path: str = "/workspace/repo"
    error: str | None = None
    local_repo: bool = False


async def clone_repo(
    sandbox: Any,
    repo_url: str,
    branch: str = "",
    workspace_path: str = "/workspace/repo",
) -> CloneResult:
    """Clone a repo into the sandbox. Handles both remote and local repos.

    Returns CloneResult with success/failure and the workspace path.
    """
    import os as _os

    # Handle local repos (file:// or absolute paths)
    if repo_url.startswith("file://") or _os.path.isabs(repo_url):
        local_path = repo_url.replace("file://", "")
        if not _os.path.exists(local_path):
            return CloneResult(success=False, error=f"Local path not found: {local_path}")
        import subprocess
        container_name = getattr(sandbox, "_container_name", getattr(sandbox, "container_name", ""))
        if container_name:
            subprocess.run(
                ["docker", "cp", local_path, f"{container_name}:{workspace_path}"],
                capture_output=True, timeout=120,
            )
            await sandbox.run(f"git init && git add -A && git commit -m 'init' --allow-empty", timeout=30)
        return CloneResult(success=True, workspace_path=workspace_path, local_repo=True)

    # Remote clone
    await sandbox.run(f"rm -rf {workspace_path} && mkdir -p {workspace_path}", timeout=30)
    clone_cmd = (
        f"git clone --depth 1 --branch {branch} {repo_url} {workspace_path} 2>&1"
        if branch
        else f"git clone --depth 1 {repo_url} {workspace_path} 2>&1"
    )
    result = await sandbox.run(clone_cmd, timeout=300)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return CloneResult(success=False, error=f"Clone failed: {err[:1000]}")

    return CloneResult(success=True, workspace_path=workspace_path)


@dataclass
class KGResult:
    success: bool
    graph_id: str = ""
    node_count: int = 0
    error: str | None = None


async def index_knowledge_graph(
    sandbox: Any,
    repo_url: str,
    branch: str = "",
    workspace_path: str = "/workspace/repo",
    install_codegraph: bool = False,
) -> KGResult:
    """Index the knowledge graph for a repo in the sandbox.

    Handles: host cache restore, codegraph index, mirror to host.
    Set install_codegraph=True to install the CLI first (pipeline path).
    """
    from harness.codegraph import (
        index_project, copy_db_to_host, restore_db_from_host,
        repo_graph_id, get_status as _cg_status,
    )

    graph_id = repo_graph_id(repo_url, branch or "main")
    host_dir = f"agent_workspace/knowledge-graphs/{graph_id}"
    prior_db_host = f"/app/{host_dir}/codegraph.db"

    # Optionally install codegraph CLI (pipeline path does this)
    if install_codegraph:
        await sandbox.run("npm install -g @colbymchenry/codegraph 2>/dev/null || true", timeout=120)

    # Restore from host cache if sandbox volume is fresh
    existing = await _cg_status(sandbox, workspace_path)
    has_nodes = (existing.get("nodeCount") or existing.get("symbols") or 0) > 0

    # Force fresh build when repo has newer commits than last indexed snapshot
    if not has_nodes and os.path.exists(prior_db_host):
        try:
            commit_date_result = await sandbox.run(
                "git -C /workspace/repo log -1 --format=%cI HEAD", timeout=10
            )
            commit_date = (commit_date_result.stdout or "").strip()
            provenance_path = os.path.join(host_dir, "provenance.json")
            if commit_date and os.path.exists(provenance_path):
                import datetime as _dt
                with open(provenance_path, "r") as pf:
                    prov = json.load(pf)
                last_indexed = prov.get("last_indexed_at", "")
                if last_indexed and commit_date > last_indexed:
                    logger.info("KG stale (commit %s > indexed %s), skipping host cache restore", commit_date, last_indexed)
                    has_nodes = True
        except Exception as exc:
            logger.debug("KG staleness check failed (proceeding with restore): %s", exc)

    if not has_nodes and os.path.exists(prior_db_host):
        await restore_db_from_host(sandbox, prior_db_host, workspace_path)

    # Build (or rebuild) the KG
    kg = await index_project(sandbox, workspace_path, timeout=600)

    # Mirror to host cache
    if kg.get("success"):
        await copy_db_to_host(sandbox, workspace_path, host_dir)

    return KGResult(
        success=kg.get("success", False),
        graph_id=graph_id,
        node_count=kg.get("nodeCount", kg.get("symbols", 0)),
        error=kg.get("error"),
    )


async def post_coordinator_kg_sync(
    sandbox: Any,
    repo_url: str,
    branch: str = "",
    workspace_path: str = "/workspace/repo",
) -> None:
    """Re-index KG after coordinator finishes (reflects agent edits)."""
    from harness.codegraph import (
        index_project, copy_db_to_host, repo_graph_id, write_provenance,
    )

    graph_id = repo_graph_id(repo_url, branch or "main")
    host_dir = f"agent_workspace/knowledge-graphs/{graph_id}"

    try:
        await index_project(sandbox, workspace_path, timeout=300)
        await copy_db_to_host(sandbox, workspace_path, host_dir)
        await write_provenance(graph_id, repo_url, branch or "main")
    except Exception as exc:
        logger.debug("Post-coordinator KG sync failed (non-fatal): %s", exc)


def assemble_coordinator_goal(
    base_goal: str,
    *,
    repo_url: str = "",
    workspace_path: str = "/workspace/repo",
    language: str = "",
    framework: str = "",
    kg_stats: dict | None = None,
    memory_block: str = "",
    explore_findings: str = "",
    kanban_board_id: str = "",
) -> str:
    """Assemble the coordinator agent's goal string.

    Both orchestrator and pipeline inject different context into the goal.
    This function normalizes the assembly into a single place.
    """
    parts = [base_goal]

    if repo_url:
        parts.append(f"\nREPO: {repo_url}")
    if workspace_path and workspace_path != "/workspace/repo":
        parts.append(f"WORKSPACE: {workspace_path}")
    if language:
        parts.append(f"LANGUAGE: {language}")
    if framework:
        parts.append(f"FRAMEWORK: {framework}")
    if kanban_board_id:
        parts.append(f"KANBAN_BOARD: {kanban_board_id}")

    if kg_stats:
        node_count = kg_stats.get("node_count", 0)
        if node_count:
            parts.append(f"\nKG: {node_count} symbols indexed")

    if memory_block:
        parts.append(f"\nCROSS-RUN MEMORY:\n{memory_block}")

    if explore_findings:
        parts.append(f"\nCODEBASE ANALYSIS:\n{explore_findings}")

    return "\n".join(parts)


@dataclass
class CoordinatorResult:
    success: bool
    output: str = ""
    error: str | None = None
    tool_calls: int = 0


def derive_run_success(result: dict) -> bool:
    """Determine if a coordinator run succeeded.

    Shared logic used by both orchestrator and pipeline to parse
    the coordinator's result dict.
    """
    if result.get("success"):
        return True
    output = str(result.get("output", "")).lower()
    if "max tool rounds" in output:
        return False
    if result.get("error"):
        return False
    return bool(result.get("output"))
