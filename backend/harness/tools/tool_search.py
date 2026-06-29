"""Tool Search — on-demand tool discovery for the autonomy model.

Mirrors Claude Code's ToolSearch pattern: the agent sees a lightweight
name-only index of available tools in the system prompt. When it needs
a capability, it calls tool_search() to load full schemas into context.

Two query modes:
  - keyword: "slack message" — fuzzy match against tool names + descriptions
  - select:  "select:Read,Edit,Grep" — load specific tools by exact name
"""

from __future__ import annotations

import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)

# Tools always available without search (core system tools)
# These must match actual tool names in the registry
CORE_TOOLS = frozenset({
    "read_file", "bash",
    "delegate_task", "collect_results",
    "tool_search", "memory", "todo",
    "skills_list", "skill_view", "skill_manage",
})

# Maximum tools that can be loaded per session to prevent context bloat
MAX_DISCOVERED_TOOLS = 30


def build_available_tools_xml() -> str:
    """Build the <available-tools> XML block for the system prompt.

    Lists every registered tool NOT in CORE_TOOLS by name only.
    Core tools are always loaded and don't need discovery.
    """
    entries = registry.list_entries()
    deferred = sorted(
        e.name for e in entries
        if e.name not in CORE_TOOLS
    )
    if not deferred:
        return ""
    parts = ["<available-tools>"]
    for name in deferred:
        parts.append(f"  <tool>{name}</tool>")
    parts.append("</available-tools>")
    parts.append(
        "\nUse tool_search(keyword) or tool_search(select=['name1','name2']) "
        "to load any of these tools before calling them."
    )
    return "\n".join(parts)


def search_tools(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search the tool registry by keyword or select.

    Args:
        query: Keyword string or "select:name1,name2" for exact selection.
        max_results: Max tools to return for keyword searches.

    Returns:
        List of tool spec dicts matching the query.
    """
    # Select mode: exact name matching
    if query.startswith("select:"):
        names = [n.strip() for n in query[7:].split(",") if n.strip()]
        results = []
        for name in names:
            spec = registry.get_spec(name)
            if spec:
                results.append(spec)
        return results

    # Keyword mode: fuzzy match against names + descriptions
    query_lower = query.lower()
    query_terms = query_lower.split()

    entries = registry.list_entries()
    scored: list[tuple[int, dict[str, Any]]] = []

    for entry in entries:
        if entry.name in CORE_TOOLS:
            continue  # Core tools are always loaded, don't advertise them
        score = 0
        name_lower = entry.name.lower()
        desc_lower = entry.spec.get("description", "").lower()

        # Direct name match (highest score)
        if query_lower == name_lower:
            score += 100
        elif query_lower in name_lower:
            score += 50

        # Term matches in description
        for term in query_terms:
            if term in name_lower:
                score += 30
            if term in desc_lower:
                score += 10

        if score > 0:
            spec = registry.get_spec(entry.name)
            if spec:
                scored.append((score, spec))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [spec for _, spec in scored[:max_results]]


class ToolSearchTool(BaseTool):
    """Dynamically discover and load tools on-demand.

    The agent calls this tool when it needs a capability not already
    in its loaded tool set. Searches the tool catalog by keyword or
    selects specific tools by name.
    """
    name = "tool_search"
    description = (
        "Search for and load tools from the available catalog. "
        "Use keyword search ('github api') to find relevant tools, "
        "or select specific tools (select=['read_file','bash']). "
        "Loaded tools become available in subsequent turns."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Keyword search query — matches tool names and descriptions",
                    },
                    "select": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exact tool names to load (bypasses keyword search)",
                    },
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        keyword = kwargs.get("keyword", "")
        select = kwargs.get("select", None)

        if not keyword and not select:
            return ToolResult(
                success=False,
                output="Provide keyword or select to search for tools",
                error="missing_query",
            )

        if select:
            results = []
            for name in select:
                spec = registry.get_spec(name)
                if spec:
                    results.append(spec)
        else:
            results = search_tools(keyword, max_results=5)

        if not results:
            return ToolResult(
                success=True,
                output="No matching tools found. Try different keywords.",
                data={"tools": [], "count": 0},
            )

        # Store discovered tools on the parent agent for next request
        tool_names = [r["function"]["name"] for r in results]
        loaded_str = ", ".join(tool_names)

        return ToolResult(
            success=True,
            output=(
                f"Loaded {len(results)} tool(s): {loaded_str}\n\n"
                "These tools are now available. You can call them directly "
                "in your next response."
            ),
            data={"tools": results, "count": len(results), "loaded_names": tool_names},
        )


# Register at import time
_tool_search = ToolSearchTool()
registry.register(_tool_search, toolset="core")
