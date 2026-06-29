"""MCP OAuth 2.1 Client Support — ported from Hermes mcp_oauth.py.

Implements browser-based OAuth 2.1 authorization code flow with PKCE
for MCP servers requiring OAuth authentication.

Uses the MCP Python SDK's OAuthClientProvider for token management.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

_OAUTH_AVAILABLE = False
try:
    from mcp.client.auth import OAuthClientProvider
    _OAUTH_AVAILABLE = True
except ImportError:
    pass

TOKEN_DIR = Path.home() / ".testai" / "mcp-tokens"


class HermesTokenStorage:
    """Persists MCP OAuth tokens to disk, keyed by server URL."""

    def __init__(self, server_url: str):
        self._server_url = server_url
        self._safe_name = (
            server_url.replace("://", "_").replace("/", "_").replace(".", "_")
        )
        self._token_path = TOKEN_DIR / f"{self._safe_name}.json"

    def load_tokens(self) -> dict | None:
        try:
            if self._token_path.exists():
                return json.loads(self._token_path.read_text())
        except Exception:
            pass
        return None

    def save_tokens(self, tokens: dict) -> None:
        try:
            TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(json.dumps(tokens, indent=2))
        except Exception as e:
            logger.warning("Failed to save OAuth tokens: %s", e)

    def delete_tokens(self) -> None:
        try:
            if self._token_path.exists():
                self._token_path.unlink()
        except Exception:
            pass


def _find_free_port() -> int:
    """Find a free ephemeral port for the OAuth redirect server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_oauth_auth(
    server_url: str,
    client_id: str | None = None,
    client_secret: str | None = None,
    scope: str | None = None,
    redirect_port: int = 0,
    client_name: str = "TestAI Agent",
) -> Any | None:
    """Build an OAuthClientProvider for the given MCP server.

    Returns None if MCP OAuth SDK is not available.
    """
    if not _OAUTH_AVAILABLE:
        logger.warning("MCP OAuth SDK not installed. pip install mcp")
        return None

    storage = HermesTokenStorage(server_url)
    existing = storage.load_tokens()
    token_dir = TOKEN_DIR / storage._safe_name

    provider = OAuthClientProvider(
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        redirect_port=redirect_port or _find_free_port(),
        client_name=client_name,
        token_dir=token_dir,
        token_persistence=storage,
    )

    if existing:
        try:
            provider.restore_tokens(existing)
        except Exception:
            pass

    return provider
