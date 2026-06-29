"""Tests for C3.1: the 4 CodeGraph MCP tools are the orchestrator's
sole code-intelligence surface.

Per the upstream CodeGraph README
(https://github.com/colbymchenry/codegraph#mcp-tools), the MCP
server exposes exactly four tools: codegraph_explore (primary),
codegraph_node, codegraph_search, codegraph_callers. The four other
tools stay functional but unlisted. We adopt the same names in
TestAI to keep the agent's mental model consistent with Claude Code,
Cursor, Codex, opencode, Hermes Agent, Gemini, Antigravity, and Kiro.

These tests assert:
  - the 4 tools are registered with the upstream names
  - the 4 tools are in the `intelligence` toolset
  - the 4 tools have descriptions matching the upstream
  - select_affected_tests() in codegraph.py uses `codegraph affected`
  - the 4 deleted ad-hoc tools are not in the registry
  - the 4 ad-hoc tools are not referenced anywhere
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Tool registration — names match upstream CodeGraph MCP tools
# ---------------------------------------------------------------------------


class TestCodeGraphMCPToolNames:
    """Tool names must match the upstream CodeGraph MCP tool names exactly.
    Drift breaks the convention adopted by Claude Code, Cursor, Codex,
    opencode, Hermes Agent, Gemini, Antigravity, and Kiro."""

    def test_all_four_tools_registered(self):
        from harness.tools.codegraph_tools import (
            CodeGraphExploreTool,
            CodeGraphNodeTool,
            CodeGraphSearchTool,
            CodeGraphCallersTool,
        )
        assert CodeGraphExploreTool.name == "codegraph_explore"
        assert CodeGraphNodeTool.name == "codegraph_node"
        assert CodeGraphSearchTool.name == "codegraph_search"
        assert CodeGraphCallersTool.name == "codegraph_callers"

    def test_tools_registered_in_registry(self):
        # Importing the module triggers registry.register() calls.
        from harness.tools import codegraph_tools  # noqa: F401
        from harness.tools.registry import registry

        names = {
            e.name for e in registry.list_entries()
            if e.name in {
                "codegraph_explore", "codegraph_node",
                "codegraph_search", "codegraph_callers",
            }
        }
        assert names == {
            "codegraph_explore", "codegraph_node",
            "codegraph_search", "codegraph_callers",
        }


class TestCodeGraphMCPToolset:
    """The 4 CodeGraph MCP tools live in the `intelligence` toolset."""

    def test_intelligence_toolset_contains_codegraph_tools(self):
        from harness.tools.toolsets import TOOLSETS
        intel = TOOLSETS["intelligence"]["tools"]
        for tool in ("codegraph_explore", "codegraph_node",
                     "codegraph_search", "codegraph_callers"):
            assert tool in intel, f"{tool!r} missing from intelligence toolset"

    def test_intelligence_toolset_drops_deleted_tools(self):
        """The 4 ad-hoc tools deleted in C3.1 must not appear in any toolset."""
        from harness.tools.toolsets import TOOLSETS
        all_tools = set()
        for ts in TOOLSETS.values():
            all_tools.update(ts.get("tools", []))
            for inc in ts.get("includes", []):
                all_tools.update(TOOLSETS.get(inc, {}).get("tools", []))
        for deleted in ("ast_grep", "code_search", "dependency_graph", "test_impact"):
            assert deleted not in all_tools, (
                f"Deleted tool {deleted!r} still in some toolset"
            )


class TestCodeGraphMCPToolDescriptions:
    """Tool descriptions match the upstream CodeGraph README.

    The installer writes a four-line marker-fenced section to
    CLAUDE.md / AGENTS.md / GEMINI.md pointing at the
    `codegraph explore` / `codegraph node` CLI commands — the same
    tool descriptions the MCP server delivers to the main agent."""

    def test_explore_description(self):
        from harness.tools.codegraph_tools import CodeGraphExploreTool
        d = CodeGraphExploreTool.description
        assert "Primary" in d
        # The upstream description mentions the four primary use cases
        for phrase in ("how does X work", "X reach Y", "blast radius", "Surfaces"):
            assert phrase in d, f"codegraph_explore description missing {phrase!r}"

    def test_node_description(self):
        from harness.tools.codegraph_tools import CodeGraphNodeTool
        d = CodeGraphNodeTool.description
        # The upstream description mentions the two modes
        for phrase in ("source", "caller/callee trail", "file path"):
            assert phrase in d, f"codegraph_node description missing {phrase!r}"

    def test_search_description(self):
        from harness.tools.codegraph_tools import CodeGraphSearchTool
        d = CodeGraphSearchTool.description
        assert "symbols by name" in d

    def test_callers_description(self):
        from harness.tools.codegraph_tools import CodeGraphCallersTool
        d = CodeGraphCallersTool.description
        for phrase in ("call site", "callback", "one section per definition"):
            assert phrase in d, f"codegraph_callers description missing {phrase!r}"


# ---------------------------------------------------------------------------
# Tool input schemas — must accept the documented args
# ---------------------------------------------------------------------------


class TestCodeGraphNodeAcceptsFilePath:
    """The upstream `codegraph_node` accepts EITHER a symbol OR a file
    path. Verify the TestAI wrapper preserves that contract."""

    def test_node_input_schema_supports_file_path(self):
        from harness.tools.codegraph_tools import CodeGraphNodeTool
        schema = CodeGraphNodeTool().spec().input_schema
        # both `symbol` and `path` must be in properties
        assert "symbol" in schema["properties"]
        assert "path" in schema["properties"]
        # anyOf clause: at least one of symbol or path must be required
        assert "anyOf" in schema


class TestCodeGraphCallersDirection:
    """The TestAI `codegraph_callers` extends the upstream with a
    `direction` parameter (callers/callees), so one tool covers
    both upstream `codegraph_callers` and `codegraph_callees`."""

    def test_callers_input_schema_has_direction(self):
        from harness.tools.codegraph_tools import CodeGraphCallersTool
        schema = CodeGraphCallersTool().spec().input_schema
        assert "direction" in schema["properties"]
        assert "callers" in schema["properties"]["direction"]["enum"]
        assert "callees" in schema["properties"]["direction"]["enum"]


# ---------------------------------------------------------------------------
# select_affected_tests — the CodeGraph wrapper for the deleted test_impact
# ---------------------------------------------------------------------------


class TestSelectAffectedTests:
    """The C3.1 test_impact replacement. Delegates to `codegraph affected`
    per the upstream docs."""

    @pytest.mark.asyncio
    async def test_passes_changed_files_as_args(self):
        """When changed_files is given, the wrapper passes them as CLI args
        (not via stdin)."""
        from harness.codegraph import select_affected_tests

        env = MagicMock()
        env.run = AsyncMock(return_value=MagicMock(returncode=0, stdout="tests/foo_test.py\ntests/bar_test.py\n", stderr=""))

        await select_affected_tests(
            env, "/workspace/repo",
            changed_files=["src/foo.py", "src/bar.py"],
        )
        # env.run is called with a string command (one big shell line)
        cmd_str = env.run.call_args[0][0]
        assert "codegraph" in cmd_str
        assert "affected" in cmd_str
        # The changed files are passed as args
        assert "src/foo.py" in cmd_str
        assert "src/bar.py" in cmd_str
        # depth default = 5
        assert "--depth" in cmd_str
        assert "'5'" in cmd_str

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_failure(self):
        from harness.codegraph import select_affected_tests

        env = MagicMock()
        env.run = AsyncMock(return_value=MagicMock(returncode=1, stdout="", stderr="oops"))

        result = await select_affected_tests(
            env, "/workspace/repo",
            changed_files=["src/foo.py"],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_env_output(self):
        from harness.codegraph import select_affected_tests

        env = MagicMock()
        env.run = AsyncMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))

        result = await select_affected_tests(
            env, "/workspace/repo",
            changed_files=["src/foo.py"],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_passes_test_filter_when_provided(self):
        from harness.codegraph import select_affected_tests

        env = MagicMock()
        env.run = AsyncMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))

        await select_affected_tests(
            env, "/workspace/repo",
            changed_files=["src/foo.py"],
            test_filter="e2e/*",
        )
        cmd_str = env.run.call_args[0][0]
        assert "--filter" in cmd_str
        assert "e2e/*" in cmd_str

    @pytest.mark.asyncio
    async def test_filters_blank_lines_from_output(self):
        from harness.codegraph import select_affected_tests

        env = MagicMock()
        env.run = AsyncMock(return_value=MagicMock(
            returncode=0,
            stdout="tests/foo_test.py\n\n\ntests/bar_test.py\n  \n",
            stderr="",
        ))

        result = await select_affected_tests(
            env, "/workspace/repo",
            changed_files=["src/foo.py"],
        )
        assert result == ["tests/foo_test.py", "tests/bar_test.py"]


# ---------------------------------------------------------------------------
# Negative tests — the 4 ad-hoc tools are GONE
# ---------------------------------------------------------------------------


class TestAdHocToolsDeleted:
    """The 4 hand-rolled KG tools deleted in C3.1 must not exist as
    importable modules or be registered in the tool registry."""

    def test_test_impact_tool_module_deleted(self):
        with pytest.raises(ModuleNotFoundError):
            import harness.tools.test_impact  # noqa: F401

    def test_dependency_graph_tool_module_deleted(self):
        with pytest.raises(ModuleNotFoundError):
            import harness.tools.dependency_graph_tool  # noqa: F401

    def test_code_search_tool_module_deleted(self):
        with pytest.raises(ModuleNotFoundError):
            import harness.tools.code_search_tool  # noqa: F401

    def test_ast_grep_tool_module_deleted(self):
        with pytest.raises(ModuleNotFoundError):
            import harness.tools.ast_grep_tool  # noqa: F401

    def test_no_adhoc_tool_in_registry(self):
        from harness.tools.codegraph_tools import (  # noqa: F401  triggers registrations
            CodeGraphExploreTool,
        )
        from harness.tools.registry import registry

        registered = {e.name for e in registry.list_entries()}
        for deleted in ("ast_grep", "code_search", "dependency_graph", "test_impact"):
            assert deleted not in registered, (
                f"Deleted tool {deleted!r} still registered in the tool registry"
            )
