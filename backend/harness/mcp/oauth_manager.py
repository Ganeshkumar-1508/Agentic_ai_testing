"""Central manager for per-server MCP OAuth state — ported from Hermes mcp_oauth_manager.py."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class MCPOAuthManager:
    """Single shared OAuth manager for all MCP servers.

    Coordinates token recovery, deduplication, and reconnect signalling.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._providers: dict[str, Any] = {}
        self._in_flight: dict[str, asyncio.Future] = {}

    def register_provider(self, server_name: str, provider: Any) -> None:
        with self._lock:
            self._providers[server_name] = provider

    def get_provider(self, server_name: str) -> Any | None:
        with self._lock:
            return self._providers.get(server_name)

    async def handle_401(self, server_name: str) -> bool:
        """Handle a 401 response from an MCP server.

        Attempts token refresh, deduplicating concurrent requests.
        Returns True if recovery succeeded.
        """
        # Check for in-flight recovery
        with self._lock:
            future = self._in_flight.get(server_name)
            if future is not None:
                return await future

            future = asyncio.get_event_loop().create_future()
            self._in_flight[server_name] = future

        try:
            provider = self.get_provider(server_name)
            if provider is None:
                return False

            try:
                await provider.refresh_tokens()
                return True
            except Exception:
                return False
        finally:
            with self._lock:
                self._in_flight.pop(server_name, None)


_manager: MCPOAuthManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> MCPOAuthManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = MCPOAuthManager()
        return _manager
