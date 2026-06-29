"""CodeGraph MCP tools — the orchestrator's code-intelligence surface.

Per the upstream CodeGraph README
(https://github.com/colbymchenry/codegraph#mcp-tools), the MCP server
exposes a focused set of four tools. A leaner list steers agents to
the right tool and saves context every session.

Each TestAI tool below is a thin wrapper that delegates to the
CodeGraph CLI via ``harness.codegraph``. The tool names match the
upstream MCP tool names so switching from CLI to MCP is zero-friction.

Tools:
  - codegraph_explore  Primary. Free-form natural-language query;
                       returns the relevant symbols' source grouped
                       by file plus the relationship map and blast
                       radius.
  - codegraph_node     One symbol's full source + caller/callee
                       trail. Or pass a file path to read a whole
                       file.
  - codegraph_search   Find symbols by name across the codebase.
  - codegraph_callers  Every call site of a function, including
                       callback registrations. One section per
                       definition when several share a name.

Pre-C3.1 TestAI had five ad-hoc tools that re-implemented subsets of
this surface: test_impact, dependency_graph, code_search, ast_grep,
kg_search/callers/callees. They have been removed; these four are the
single code-intelligence surface.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from harness.codegraph import (
    _run_in_sandbox,
    get_callers,
    get_callees,
    get_sandbox_env,
    get_status,
    query_symbols,
)
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = "/workspace/repo"


def _resolve_workspace_path() -> str:
    return _WORKSPACE_ROOT


async def _require_sandbox() -> Any | None:
    env = await get_sandbox_env()
    if env is None:
        return None
    return env


# ---------------------------------------------------------------------------
# codegraph_explore — primary free-form query
# ---------------------------------------------------------------------------


class CodeGraphExploreTool(BaseTool):
    """Primary CodeGraph tool. Free-form natural-language query.

    Returns the relevant symbols' source grouped by file, plus the
    relationship map and blast radius. Surfaces dynamic-dispatch hops
    (callbacks, React re-render, interface->impl) that grep can't
    follow.
    """

    name = "codegraph_explore"
    description = (
        "**Primary.** Answer almost any question in one call — 'how "
        "does X work', a flow ('how does X reach Y'), or surveying an "
        "area — returning the relevant symbols' verbatim source "
        "grouped by file, plus a relationship map and blast radius. "
        "Surfaces dynamic-dispatch hops (callbacks, React re-render, "
        "interface→impl) grep can't follow."
    )
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-form natural-language question about the code",
                    },
                    "max_results": {"type": "integer", "default": 15},
                },
                "required": ["query"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = int(kwargs.get("max_results", 15))
        if not query:
            return ToolResult(success=False, output="`query` is required", error="missing_arg")
        env = await _require_sandbox()
        if env is None:
            return ToolResult(success=False, output="No sandbox environment", error="no_sandbox")

        ws = _resolve_workspace_path()
        results = await query_symbols(env, ws, query, limit=limit)
        if not results:
            return ToolResult(
                success=False,
                output="No knowledge graph found. Run ANALYZE phase first.",
                error="no_graph",
            )
        return ToolResult(
            success=True,
            output=json.dumps({"query": query, "count": len(results), "results": results}, indent=2),
        )


# ---------------------------------------------------------------------------
# codegraph_node — one symbol's full source + caller/callee trail
# ---------------------------------------------------------------------------


class CodeGraphNodeTool(BaseTool):
    """One symbol's full source + caller/callee trail.

    Or pass a file path to read a whole file like the Read tool.
    """

    name = "codegraph_node"
    description = (
        "One symbol's full source + caller/callee trail (every "
        "overload for an ambiguous name) — or pass a file path to "
        "read a whole file like the Read tool (same line-numbered "
        "output, `offset`/`limit`), with its dependents attached."
    )
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name (function/class/method) to look up",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path to read whole-file (alternative to symbol)",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional kind filter (e.g. 'function', 'class', 'method')",
                    },
                    "offset": {"type": "integer", "default": 0, "description": "File-read offset (line)"},
                    "limit": {"type": "integer", "default": 0, "description": "File-read line limit"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "anyOf": [
                    {"required": ["symbol"]},
                    {"required": ["path"]},
                ],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        symbol = kwargs.get("symbol", "")
        path = kwargs.get("path", "")
        kind = kwargs.get("kind", "")
        limit = int(kwargs.get("max_results", 10))
        if not symbol and not path:
            return ToolResult(
                success=False,
                output="One of `symbol` or `path` is required",
                error="missing_arg",
            )
        env = await _require_sandbox()
        if env is None:
            return ToolResult(success=False, output="No sandbox environment", error="no_sandbox")

        ws = _resolve_workspace_path()
        if path:
            # File-read mode: hand off to the sandbox's `cat` with the file
            # path. CodeGraph's "node" tool reads files like the Read tool.
            offset = int(kwargs.get("offset", 0))
            line_limit = int(kwargs.get("limit", 0))
            file_cmd = f"cat -n {path}"
            if offset:
                file_cmd = f"tail -n +{offset + 1} {path} | cat -n"
            if line_limit:
                file_cmd = f"{file_cmd} | head -n {line_limit}"
            proc = await _run_in_sandbox(env, [], timeout=30)  # noop, use env.run directly
            proc = await env.run(file_cmd, timeout=30)
            if proc.returncode == 0 and proc.stdout:
                return ToolResult(
                    success=True,
                    output=proc.stdout,
                )
            return ToolResult(
                success=False,
                output=f"Could not read {path}",
                error="io_error",
            )

        # Symbol-lookup mode.
        results = await query_symbols(env, ws, symbol, kind=kind, limit=limit)
        if not results:
            return ToolResult(
                success=False,
                output=f"No symbol matching '{symbol}' in the knowledge graph.",
                error="no_results",
            )
        return ToolResult(
            success=True,
            output=json.dumps({
                "symbol": symbol,
                "kind": kind,
                "count": len(results),
                "results": results,
            }, indent=2),
        )


# ---------------------------------------------------------------------------
# codegraph_search — find symbols by name across the codebase
# ---------------------------------------------------------------------------


class CodeGraphSearchTool(BaseTool):
    """Find symbols by name across the codebase."""

    name = "codegraph_search"
    description = "Find symbols by name across the codebase"
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Symbol name to search for"},
                    "kind": {
                        "type": "string",
                        "description": "Optional kind filter (e.g. 'function', 'class')",
                    },
                    "max_results": {"type": "integer", "default": 15},
                },
                "required": ["query"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        kind = kwargs.get("kind", "")
        limit = int(kwargs.get("max_results", 15))
        if not query:
            return ToolResult(success=False, output="`query` is required", error="missing_arg")
        env = await _require_sandbox()
        if env is None:
            return ToolResult(success=False, output="No sandbox environment", error="no_sandbox")

        ws = _resolve_workspace_path()
        results = await query_symbols(env, ws, query, kind=kind, limit=limit)
        if not results:
            return ToolResult(
                success=False,
                output=f"No symbols matching '{query}'.",
                error="no_results",
            )
        return ToolResult(
            success=True,
            output=json.dumps({
                "query": query,
                "kind": kind,
                "count": len(results),
                "results": results,
            }, indent=2),
        )


# ---------------------------------------------------------------------------
# codegraph_callers — every call site of a function
# ---------------------------------------------------------------------------


class CodeGraphCallersTool(BaseTool):
    """Every call site of a function, including callback registrations."""

    name = "codegraph_callers"
    description = (
        "Every call site of a function — including where it's "
        "registered as a callback — with one section per definition "
        "when several share a name"
    )
    default_level = "allow"
    capabilities = ["can_search_code"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Function/method name to find callers for",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["callers", "callees"],
                        "default": "callers",
                        "description": "'callers' (who calls it) or 'callees' (what it calls)",
                    },
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["symbol"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        symbol = kwargs.get("symbol", "")
        direction = kwargs.get("direction", "callers")
        limit = int(kwargs.get("max_results", 20))
        if not symbol:
            return ToolResult(success=False, output="`symbol` is required", error="missing_arg")
        env = await _require_sandbox()
        if env is None:
            return ToolResult(success=False, output="No sandbox environment", error="no_sandbox")

        ws = _resolve_workspace_path()
        if direction == "callees":
            results = await get_callees(env, ws, symbol, limit=limit)
            key = "callees"
        else:
            results = await get_callers(env, ws, symbol, limit=limit)
            key = "callers"

        if not results:
            return ToolResult(
                success=False,
                output=f"No {direction} found for '{symbol}'",
                error="no_results",
            )
        return ToolResult(
            success=True,
            output=json.dumps({
                "symbol": symbol,
                "direction": direction,
                "count": len(results),
                key: results,
            }, indent=2),
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

registry.register(CodeGraphExploreTool(), toolset="intelligence")
registry.register(CodeGraphNodeTool(), toolset="intelligence")
registry.register(CodeGraphSearchTool(), toolset="intelligence")
registry.register(CodeGraphCallersTool(), toolset="intelligence")


class CodeGraphCalleesTool(CodeGraphCallersTool):
    """Back-compat alias for ``codegraph_callers(direction="callees")``.

    The leaf-allow-list (``backend/harness/tools/delegate_task.py:332``)
    and several agent recipes still reference ``codegraph_callees`` as
    a tool name. The implementation is identical to
    :class:`CodeGraphCallersTool` with the direction forced to
    ``"callees"``. P0 audit fix 2026-06-23 — keep the name reachable
    rather than dropping it.
    """

    name = "codegraph_callees"
    description = (
        "Find what a symbol calls (callees). Back-compat alias for "
        "codegraph_callers(direction=\"callees\"). Returns JSON "
        "{symbol, direction: \"callees\", count, callees}."
    )

    async def run(self, *, symbol: str, max_results: int = 20, **_unused) -> str:  # type: ignore[override]
        return await super().run(
            symbol=symbol, direction="callees", max_results=max_results,
        )


registry.register(CodeGraphCalleesTool(), toolset="intelligence")


__all__ = [
    "CodeGraphExploreTool",
    "CodeGraphNodeTool",
    "CodeGraphSearchTool",
    "CodeGraphCallersTool",
    "CodeGraphCalleesTool",
]
