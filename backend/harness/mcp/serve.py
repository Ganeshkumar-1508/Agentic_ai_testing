"""MCP Server — expose TestAI agent tools as MCP for other agents (Claude Desktop, Cursor, etc.).

Enables bidirectional MCP: OTHER agents can connect to OUR agent and use its tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TestAIMPCServer:
    """MCP server that exposes TestAI's capabilities to other agents.

    Other agents (Claude Desktop, Cursor, Codex) connect to this server
    via stdio MCP transport and discover our tools.
    """

    def __init__(self, tool_registry: Any, session_db: Any | None = None):
        self.registry = tool_registry
        self.session_db = session_db

    def get_tool_list(self) -> list[dict]:
        """Return the list of available tools in MCP format."""
        tools = []
        try:
            entries = self.registry.list_entries() if hasattr(self.registry, 'list_entries') else []
            for entry in entries:
                spec = getattr(entry, 'spec', None)
                if spec and isinstance(spec, dict):
                    tools.append({
                        "name": entry.get("name", ""),
                        "description": spec.get("description", ""),
                        "inputSchema": spec.get("parameters", {"type": "object", "properties": {}}),
                    })
        except Exception as e:
            logger.warning("Failed to build tool list: %s", e)
        return tools

    def handle_call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call from an external agent."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                self.registry.execute(tool_name, arguments)
            )
            if hasattr(result, 'output'):
                return result.output
            return str(result)
        except Exception as e:
            return json.dumps({"error": str(e)})
