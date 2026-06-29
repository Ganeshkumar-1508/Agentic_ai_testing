"""Knowledge graph tools for agents — CodeGraph-only interface.

Single data source: CodeGraph SQLite DB (``.codegraph/codegraph.db``) built
by ``codegraph init`` during the ANALYZE phase. Commands run inside the sandbox.

CodeGraph CLI docs (https://github.com/colbymchenry/codegraph):
  query:    ``codegraph query -j -p <path> <search>``
  callers:  ``codegraph callers -j -p <path> <symbol>``
  callees:  ``codegraph callees -j -p <path> <symbol>``
  status:   ``codegraph status -j <path>``

Workspace layout (Option C — namespaced paths):
  /workspace/repo/              Primary repo (writable, default)
  /workspace/context/{name}/    Context repos (read-only, opt-in)

Tools: kg_search, kg_callers, kg_callees, kg_graph_status

The ``kg_refresh`` tool previously lived here; it was promoted to
``harness/tools/kg_refresh_tool.py`` (C04, June 2026) which adds
debounce, delta computation, ``kg.refreshed`` event emission, and
categorized failure reporting. The replacement is registered
automatically when ``kg_refresh_tool`` is imported.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec

# Trigger registration of the promoted ``kg_refresh`` tool. Anyone
# who imports this module (which happens in several places via the
# tool loader) gets the promoted tool's ``registry.register`` call
# executed as a side-effect of import. This keeps the public
# surface unchanged (callers see ``kg_refresh`` in the registry)
# while moving the implementation to its own file.
from harness.tools import kg_refresh_tool  # noqa: F401

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = "/workspace/repo"
_CONTEXT_ROOT = "/workspace/context"


def _resolve_workspace_path(repo: str = "") -> str:
    """Resolve the workspace path, defaulting to primary repo.

    Args:
        repo: If provided, resolves to /workspace/context/{repo}.
              If empty, resolves to /workspace/repo (primary).
    """
    if repo:
        repo_clean = repo.strip("/").split("/")[-1].replace(".git", "")
        return f"{_CONTEXT_ROOT}/{repo_clean}"
    return _WORKSPACE_ROOT


async def _run_cg(args: list[str], timeout: int = 30, repo: str = "") -> subprocess.CompletedProcess | None:
    """Run a codegraph command inside the sandbox.

    Args:
        repo: Context repo name to query. Defaults to primary repo.
    """
    from harness.codegraph import get_sandbox_env
    env = await get_sandbox_env()
    if not env:
        return None
    ws = _resolve_workspace_path(repo)
    cmd = "cd {} && npx --yes @colbymchenry/codegraph {}".format(
        _q(ws),
        " ".join(_q(a) for a in args),
    )
    return await env.run(cmd, timeout=timeout)


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


async def _search_cg(query: str, limit: int = 10, repo: str = "") -> list[dict]:
    """Search CodeGraph for symbols. Uses ``codegraph query -j -p <path> <search>``."""
    proc = await _run_cg(["query", "-j", "-p", _resolve_workspace_path(repo), "-l", str(limit), query], timeout=30, repo=repo)
    if proc and proc.returncode == 0 and proc.stdout and proc.stdout.strip():
        try:
            return json.loads(proc.stdout).get("results", [])
        except json.JSONDecodeError:
            pass
    return []


async def _get_callers_cg(symbol_id: str, limit: int = 20, repo: str = "") -> list[dict]:
    """Find callers. Uses ``codegraph callers -j -p <path> <symbol_id>``."""
    proc = await _run_cg(["callers", "-j", "-p", _resolve_workspace_path(repo), "-l", str(limit), symbol_id], timeout=30, repo=repo)
    if proc and proc.returncode == 0 and proc.stdout and proc.stdout.strip():
        try:
            return json.loads(proc.stdout).get("callers", [])
        except json.JSONDecodeError:
            pass
    return []


async def _get_callees_cg(symbol_id: str, limit: int = 20, repo: str = "") -> list[dict]:
    """Find callees. Uses ``codegraph callees -j -p <path> <symbol_id>``."""
    proc = await _run_cg(["callees", "-j", "-p", _resolve_workspace_path(repo), "-l", str(limit), symbol_id], timeout=30, repo=repo)
    if proc and proc.returncode == 0 and proc.stdout and proc.stdout.strip():
        try:
            return json.loads(proc.stdout).get("callees", [])
        except json.JSONDecodeError:
            pass
    return []


async def _get_status_cg(repo: str = "") -> dict | None:
    """Get CodeGraph indexing status. Uses ``codegraph status -j <path>``."""
    proc = await _run_cg(["status", "-j", _resolve_workspace_path(repo)], timeout=30, repo=repo)
    if proc and proc.returncode == 0 and proc.stdout and proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


_REPO_PARAM = {
    "repo": {
        "type": "string",
        "description": "Context repo name to query instead of primary. Repos live at /workspace/context/{name}.",
    },
}


class KGSearchTool(BaseTool):
    name = "kg_search"
    description = "Search the code knowledge graph for symbols (functions, classes, files) by name or description. Uses CodeGraph query. Returns matching nodes. Optionally search a context repo's KG."
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term — matches symbol names and labels"},
                "max_results": {"type": "integer", "description": "Max results (default 10)"},
                **_REPO_PARAM,
            },
            "required": ["query"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = int(kwargs.get("max_results", 10))
        repo = kwargs.get("repo", "")
        if not query:
            return ToolResult(success=False, output="Query is required", error="missing_query")

        results = await _search_cg(query, limit, repo=repo)
        if results:
            return ToolResult(success=True, output=json.dumps({"query": query, "count": len(results), "results": results, "repo": repo or "primary"}, indent=2))

        return ToolResult(success=False, output="No knowledge graph found. Run ANALYZE phase first to build one.", error="no_graph")


class KGCallersTool(BaseTool):
    name = "kg_callers"
    description = "Find what functions or code call a given symbol. Like 'find references' in an IDE. Optionally search a context repo."
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string", "description": "The symbol/node ID to find callers for"},
                "max_results": {"type": "integer", "description": "Max results (default 20)"},
                **_REPO_PARAM,
            },
            "required": ["symbol_id"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        symbol_id = kwargs.get("symbol_id", "")
        limit = int(kwargs.get("max_results", 20))
        repo = kwargs.get("repo", "")
        if not symbol_id:
            return ToolResult(success=False, output="Symbol ID is required", error="missing_id")
        results = await _get_callers_cg(symbol_id, limit, repo=repo)
        if not results:
            return ToolResult(success=False, output=f"No callers found for '{symbol_id}'", error="no_results")
        return ToolResult(success=True, output=json.dumps({"symbol_id": symbol_id, "count": len(results), "callers": results, "repo": repo or "primary"}, indent=2))


class KGCalleesTool(BaseTool):
    name = "kg_callees"
    description = "Find what functions or code a given symbol calls. Like 'go to definition' recursion. Optionally search a context repo."
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "symbol_id": {"type": "string", "description": "The symbol/node ID to find callers for"},
                "max_results": {"type": "integer", "description": "Max results (default 20)"},
                **_REPO_PARAM,
            },
            "required": ["symbol_id"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        symbol_id = kwargs.get("symbol_id", "")
        limit = int(kwargs.get("max_results", 20))
        repo = kwargs.get("repo", "")
        if not symbol_id:
            return ToolResult(success=False, output="Symbol ID is required", error="missing_id")
        results = await _get_callees_cg(symbol_id, limit, repo=repo)
        if not results:
            return ToolResult(success=False, output=f"No callees found for '{symbol_id}'", error="no_results")
        return ToolResult(success=True, output=json.dumps({"symbol_id": symbol_id, "count": len(results), "callees": results, "repo": repo or "primary"}, indent=2))


class KGGraphStatusTool(BaseTool):
    name = "kg_graph_status"
    description = "Check the knowledge graph status: node/edge counts, data source, health. Optionally check a context repo."
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                **_REPO_PARAM,
            },
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        repo = kwargs.get("repo", "")
        status = await _get_status_cg(repo=repo)
        if status:
            return ToolResult(success=True, output=json.dumps({
                "status": "ready",
                "source": "codegraph",
                "symbols": status.get("symbols", 0),
                "files": status.get("files", 0),
                "repo": repo or "primary",
            }, indent=2))
        return ToolResult(success=False, output="No knowledge graph found. Run ANALYZE phase first.", error="no_graph")


# Register
# The ``kg_refresh`` tool was promoted to ``kg_refresh_tool.py`` and
# is imported there. The remaining four read-only KG tools (search,
# callers, callees, status) stay here. The ``intelligence`` toolset
# in toolsets.py still lists ``kg_refresh``; the dispatcher's name
# lookup finds the promoted tool regardless of which toolset
# originally listed it.
from harness.tools.registry import registry

registry.register(KGSearchTool(), toolset="intelligence")
registry.register(KGCallersTool(), toolset="intelligence")
registry.register(KGCalleesTool(), toolset="intelligence")
registry.register(KGGraphStatusTool(), toolset="intelligence")

# Back-compat alias
KnowledgeGraphSearchTool = KGSearchTool
