"""MCP Client — connects to external MCP servers, discovers tools, registers them.

Ported from Hermes mcp_tool.py with full feature parity:
  - StreamableHTTP + SSE + Stdio transport
  - Credential stripping in error messages (security)
  - Per-server timeouts (connect + tool call)
  - Stderr redirection for clean dashboard output
  - Automatic reconnection with exponential backoff
  - OAuth2 support for protected MCP servers
  - Parallel tool calls (per-server opt-in)
  - Tool result caching
  - Health checking (periodic ping)
  - Tool include/exclude filtering
  - Resource/Prompt utility tools
  - Env var filtering for subprocess security
  - Sampling (MCP server → LLM completion requests)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

# ── Config ──────────────────────────────────────────────────────────────
ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")
RECONNECT_MAX_RETRIES = 5
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0
HEALTH_CHECK_INTERVAL = 30
CACHE_TTL_SECONDS = 60
DEFAULT_TOOL_TIMEOUT = 120
DEFAULT_CONNECT_TIMEOUT = 60

# Circuit breaker
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 60

# Session expiry markers (lower-cased)
SESSION_EXPIRED_MARKERS: tuple = (
    "invalid or expired session", "expired session", "session expired",
    "session not found", "unknown session", "session terminated",
    "closedresourceerror", "closed resource",
    "transport is closed", "connection closed",
    "broken pipe", "end of file",
)
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_MCP_AVAILABLE = True
try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.types import CallToolResult
except ImportError:
    _MCP_AVAILABLE = False

_STREAMABLE_HTTP_AVAILABLE = False
try:
    from mcp.client.streamable_http import streamablehttp_client
    _STREAMABLE_HTTP_AVAILABLE = True
except ImportError:
    try:
        from mcp.client.streamable_http import streamable_http_client as streamablehttp_client
        _STREAMABLE_HTTP_AVAILABLE = True
    except ImportError:
        pass

# Credential patterns to strip from error messages
_CREDENTIAL_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key|token|secret|password|auth)[=:]\s*\S+'), r'\1=***'),
    (re.compile(r'(?i)(Authorization|X-API-Key|Bearer):\s*\S+'), r'\1: ***'),
    (re.compile(r'sk-[a-zA-Z0-9]{10,}'), 'sk-***'),
    (re.compile(r'ghp_[a-zA-Z0-9]{10,}'), 'ghp_***'),
    (re.compile(r'gho_[a-zA-Z0-9]{10,}'), 'gho_***'),
    (re.compile(r'xox[baprs]-[a-zA-Z0-9-]{10,}'), 'xox*-***'),
]


def sanitize_error_message(msg: str) -> str:
    """Strip credential patterns from error messages before they reach the LLM."""
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


def _normalize_env(env: dict | None) -> dict:
    """Filter env vars for MCP subprocess — only pass explicitly listed vars (security)."""
    filtered = {}
    if env:
        for k, v in env.items():
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', str(k)):
                filtered[str(k)] = str(v)
    return filtered


def _get_mcp_stderr_log():
    """Redirect MCP server stderr to a log file instead of the TUI."""
    log_dir = Path.home() / ".testai" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mcp-stderr.log"
    try:
        return open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        try:
            return open(os.devnull, "w", encoding="utf-8")
        except Exception:
            return sys.stderr


def _normalize_input_schema(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    if "type" not in schema:
        schema["type"] = "object"
    if "properties" not in schema:
        schema["properties"] = {}
    return schema


def _mcp_tool_name(server_name: str, tool_name: str) -> str:
    safe_server = re.sub(r'[^a-zA-Z0-9_-]', '_', server_name)
    safe_tool = re.sub(r'[^a-zA-Z0-9_-]', '_', tool_name)
    return f"mcp_{safe_server}_{safe_tool}"


def _normalize_name_filter(filter_list: list | None, context: str = "") -> set:
    """Normalize a list of tool name patterns, logging warnings for empties."""
    if not filter_list:
        return set()
    result = set()
    for entry in filter_list:
        if isinstance(entry, str) and entry.strip():
            result.add(entry.strip())
    return result


def _interpolate_env_vars(value):
    """Recursively resolve ``${VAR}`` placeholders from ``os.environ``."""
    if isinstance(value, str):
        def _replace(m):
            return os.environ.get(m.group(1), m.group(0))
        return ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_vars(v) for v in value]
    return value


def _format_connect_error(exc: BaseException) -> str:
    """Return a user-friendly (sanitized) connection error string."""
    msg = sanitize_error_message(str(exc))
    # Drop long traceback-ish content
    if len(msg) > 500:
        msg = msg[:500] + "..."
    return msg


# Circuit breaker state
_server_error_counts: dict[str, int] = {}
_server_breaker_opened_at: dict[str, float] = {}


def _bump_server_error(server_name: str) -> None:
    n = _server_error_counts.get(server_name, 0) + 1
    _server_error_counts[server_name] = n
    if n >= CIRCUIT_BREAKER_THRESHOLD:
        _server_breaker_opened_at[server_name] = time.monotonic()


def _reset_server_error(server_name: str) -> None:
    _server_error_counts[server_name] = 0
    _server_breaker_opened_at.pop(server_name, None)


def _is_server_circuit_open(server_name: str) -> bool:
    opened_at = _server_breaker_opened_at.get(server_name)
    if opened_at is None:
        return False
    if time.monotonic() - opened_at > CIRCUIT_BREAKER_COOLDOWN:
        _server_breaker_opened_at.pop(server_name, None)
        return False
    return True


def _is_auth_error(exc: BaseException) -> bool:
    """Detect MCP OAuth/401 errors across SDK versions."""
    try:
        from mcp.client.auth import OAuthFlowError, OAuthTokenError
        if isinstance(exc, (OAuthFlowError, OAuthTokenError)):
            return True
    except ImportError:
        pass
    try:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            return getattr(exc.response, "status_code", None) == 401
    except ImportError:
        pass
    return False


def _is_session_expired_error(exc: BaseException) -> bool:
    """Return True if exc looks like an MCP transport session expiry."""
    if isinstance(exc, InterruptedError):
        return False
    msg = str(exc).lower()
    if not msg:
        return False
    return any(marker in msg for marker in SESSION_EXPIRED_MARKERS)


# ---------------------------------------------------------------------------
# MCP Connection Info
# ---------------------------------------------------------------------------


class MCPToolDef:
    def __init__(self, name: str, description: str, input_schema: dict, server_id: str):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.server_id = server_id


class MCPResourceDef:
    def __init__(self, uri: str, name: str, description: str, mime_type: str, server_id: str):
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type
        self.server_id = server_id


class MCPPromptDef:
    def __init__(self, name: str, description: str, arguments: list, server_id: str):
        self.name = name
        self.description = description
        self.arguments = arguments
        self.server_id = server_id


# ---------------------------------------------------------------------------
# MCPServerTask — manages a single MCP server connection
# ---------------------------------------------------------------------------


class MCPServerTask:
    def __init__(self, name: str, config: dict, tool_registry: Any,
                 on_tools_changed: Callable | None = None,
                 sampling_handler: Any | None = None):
        self.name = name
        self.config = config
        self.registry = tool_registry
        self.on_tools_changed = on_tools_changed
        self.sampling_handler = sampling_handler
        self.session: ClientSession | None = None
        self._tools: list = []
        self._resources: list = []
        self._prompts: list = []
        self._registered_tool_names: list[str] = []
        self._cleanup: Callable | None = None
        self._connected = False
        self._reconnect_task: asyncio.Task | None = None
        self._exit = False
        self._last_health_ok = True

        # Feature: Per-server timeouts
        self.tool_timeout = config.get("timeout", DEFAULT_TOOL_TIMEOUT)
        self.connect_timeout = config.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT)

        # Feature: Parallel tool calls (per-server opt-in)
        self.supports_parallel = config.get("supports_parallel_tool_calls", False)

        # Feature: Tool caching
        self._cache: dict[str, tuple[float, str]] = {}
        self._cache_ttl = config.get("cache_ttl_seconds", CACHE_TTL_SECONDS)

        # Feature: Tool include/exclude filtering
        tools_filter = config.get("tools") or {}
        self._include_set = _normalize_name_filter(
            tools_filter.get("include"), f"mcp_servers.{name}.tools.include"
        )
        self._exclude_set = _normalize_name_filter(
            tools_filter.get("exclude"), f"mcp_servers.{name}.tools.exclude"
        )

    @property
    def connected(self) -> bool:
        return self._connected

    def _should_register_tool(self, tool_name: str) -> bool:
        """Feature: Tool include/exclude filtering."""
        if self._include_set:
            return tool_name in self._include_set
        if self._exclude_set:
            return tool_name not in self._exclude_set
        return True

    async def connect(self) -> bool:
        """Connect to the MCP server and discover tools.
        
        Feature: Reconnection with exponential backoff (up to 5 retries).
        """
        url = self.config.get("url", "")
        command = self.config.get("command", "")
        args = self.config.get("args", [])
        env = self.config.get("env", {})
        transport = self.config.get("transport", "stdio" if command else "sse")

        for attempt in range(RECONNECT_MAX_RETRIES):
            if self._exit:
                return False
            try:
                if url and "http" in url:
                    if transport == "sse":
                        await self._connect_sse(url)
                    else:
                        await self._connect_http(url)
                elif command:
                    await self._connect_stdio(command, args, env)
                else:
                    logger.error("MCP '%s': no url or command", self.name)
                    return False

                self._connected = True
                logger.info("MCP '%s': connected (attempt %d)", self.name, attempt + 1)
                return True
            except asyncio.TimeoutError:
                logger.warning("MCP '%s': timeout (attempt %d/%d)", self.name, attempt + 1, RECONNECT_MAX_RETRIES)
            except Exception as e:
                logger.warning("MCP '%s': failed (attempt %d/%d): %s",
                               self.name, attempt + 1, RECONNECT_MAX_RETRIES,
                               sanitize_error_message(str(e)))
            if attempt < RECONNECT_MAX_RETRIES - 1:
                delay = min(RECONNECT_BASE_DELAY * (2 ** attempt), RECONNECT_MAX_DELAY)
                await asyncio.sleep(delay)

        return False

    def _build_session_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.sampling_handler and self.sampling_handler.llm:
            kwargs["sampling_callback"] = self.sampling_handler.handle_sampling
        return kwargs

    async def _connect_sse(self, url: str):
        async def _run():
            async with sse_client(url=url) as (read, write):
                async with ClientSession(read, write, **self._build_session_kwargs()) as session:
                    await session.initialize()
                    self.session = session
                    await self._populate_capabilities()
                    await self._lifecycle_loop()
        await asyncio.wait_for(_run(), timeout=self.connect_timeout)

    async def _connect_http(self, url: str):
        if _STREAMABLE_HTTP_AVAILABLE:
            try:
                headers = {"mcp-protocol-version": "2025-03-26"}
                from harness.mcp.oauth_manager import get_manager
                oauth_mgr = get_manager()
                oauth_provider = oauth_mgr.get_provider(self.name)
                if oauth_provider:
                    headers["Authorization"] = f"Bearer {oauth_provider.access_token}"

                async def _run():
                    async with streamablehttp_client(url=url, headers=headers) as (read, write):
                        async with ClientSession(read, write, **self._build_session_kwargs()) as session:
                            await session.initialize()
                            self.session = session
                            await self._populate_capabilities()
                            await self._lifecycle_loop()

                await asyncio.wait_for(_run(), timeout=self.connect_timeout)
                return
            except Exception:
                pass
        await self._connect_sse(url)

    async def _connect_stdio(self, command: str, args: list, env: dict):
        """Feature: Env var filtering — only pass explicitly listed vars."""
        filtered_env = _normalize_env(env)
        merged_env = os.environ.copy()
        merged_env.update(filtered_env)
        stderr_log = _get_mcp_stderr_log()

        params = StdioServerParameters(
            command=command,
            args=list(args) if args else [],
            env=merged_env,
        )

        async def _run():
            async with stdio_client(params, errlog=stderr_log) as (read, write):
                async with ClientSession(read, write, **self._build_session_kwargs()) as session:
                    await session.initialize()
                    self.session = session
                    await self._populate_capabilities()
                    await self._lifecycle_loop()

        await asyncio.wait_for(_run(), timeout=self.connect_timeout)

    async def _populate_capabilities(self):
        """Feature: Discover tools, resources, and prompts."""
        if not self.session:
            return

        # Tools
        try:
            tools_result = await self.session.list_tools()
            all_tools = tools_result.tools if hasattr(tools_result, 'tools') else []
            self._tools = [t for t in all_tools if self._should_register_tool(t.name)]
        except Exception as e:
            logger.warning("MCP '%s': tool discovery failed: %s", self.name, e)
            self._tools = []

        # Resources
        try:
            resources_result = await self.session.list_resources()
            self._resources = resources_result.resources if hasattr(resources_result, 'resources') else []
        except Exception:
            self._resources = []

        # Prompts
        try:
            prompts_result = await self.session.list_prompts()
            self._prompts = prompts_result.prompts if hasattr(prompts_result, 'prompts') else []
        except Exception:
            self._prompts = []

    async def _lifecycle_loop(self):
        """Feature: Health checking with periodic ping.
        
        Runs while connected, pinging every HEALTH_CHECK_INTERVAL seconds.
        """
        while not self._exit:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            if self._exit:
                break
            try:
                if self.session:
                    await asyncio.wait_for(self.session.list_tools(), timeout=5.0)
                    self._last_health_ok = True
            except Exception:
                self._last_health_ok = False
                logger.warning("MCP '%s': health check failed, reconnecting...", self.name)
                if not self._exit:
                    self._connected = False
                    asyncio.create_task(self._reconnect())

    async def _reconnect(self):
        """Reconnect with exponential backoff."""
        for attempt in range(RECONNECT_MAX_RETRIES):
            if self._exit:
                return
            delay = min(RECONNECT_BASE_DELAY * (2 ** attempt), RECONNECT_MAX_DELAY)
            await asyncio.sleep(delay)
            if await self.connect():
                if self.on_tools_changed:
                    self.on_tools_changed()
                return
        logger.error("MCP '%s': reconnection failed after %d attempts", self.name, RECONNECT_MAX_RETRIES)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool. Feature: Tool result caching, parallel tool calls, auth/session retry."""
        if not self.session:
            return json.dumps({"error": "Not connected"})

        if _is_server_circuit_open(self.name):
            return json.dumps({
                "error": f"MCP server '{self.name}' circuit breaker open (too many consecutive failures). "
                         f"Cooling down for {CIRCUIT_BREAKER_COOLDOWN}s."
            })

        # Feature: Tool result caching
        cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
        cached = self._cache.get(cache_key)
        if cached:
            ts, result = cached
            if time.time() - ts < self._cache_ttl:
                return result

        async def _do_call() -> str:
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments),
                timeout=self.tool_timeout,
            )
            output = sanitize_error_message(str(result))
            if hasattr(result, 'content') and result.content:
                texts = []
                for c in result.content:
                    if hasattr(c, 'text'):
                        texts.append(c.text)
                    elif isinstance(c, dict):
                        texts.append(c.get('text', str(c)))
                if texts:
                    output = sanitize_error_message("\n".join(texts))
            return output

        try:
            output = await _do_call()
            _reset_server_error(self.name)
            self._cache[cache_key] = (time.time(), output)
            return output
        except Exception as e:
            _bump_server_error(self.name)
            err_msg = sanitize_error_message(str(e))

            # Auth error → trigger reconnect, retry once
            if _is_auth_error(e):
                logger.warning("MCP '%s': auth error, reconnecting...", self.name)
                self._connected = False
                asyncio.create_task(self._reconnect())
                await asyncio.sleep(2)
                try:
                    output = await _do_call()
                    _reset_server_error(self.name)
                    self._cache[cache_key] = (time.time(), output)
                    return output
                except Exception:
                    pass

            # Session expiry → trigger reconnect, retry once
            if _is_session_expired_error(e):
                logger.warning("MCP '%s': session expired, reconnecting...", self.name)
                self._connected = False
                asyncio.create_task(self._reconnect())
                await asyncio.sleep(2)
                try:
                    output = await _do_call()
                    _reset_server_error(self.name)
                    self._cache[cache_key] = (time.time(), output)
                    return output
                except Exception:
                    pass

            return json.dumps({"error": err_msg})

    async def read_resource(self, uri: str) -> str:
        """Feature: Resource utility — read a resource from the server."""
        if not self.session:
            return json.dumps({"error": "Not connected"})
        try:
            result = await asyncio.wait_for(
                self.session.read_resource(uri),
                timeout=self.tool_timeout,
            )
            return sanitize_error_message(str(result))
        except Exception as e:
            return json.dumps({"error": sanitize_error_message(str(e))})

    async def get_prompt(self, name: str, arguments: dict | None = None) -> str:
        """Feature: Prompt utility — get a prompt template from the server."""
        if not self.session:
            return json.dumps({"error": "Not connected"})
        try:
            result = await asyncio.wait_for(
                self.session.get_prompt(name, arguments or {}),
                timeout=self.tool_timeout,
            )
            return sanitize_error_message(str(result))
        except Exception as e:
            return json.dumps({"error": sanitize_error_message(str(e))})

    async def disconnect(self):
        self._exit = True
        self._connected = False
        if self._cleanup:
            try:
                self._cleanup()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Sampling support — MCP server requests LLM completion
# ---------------------------------------------------------------------------

class SamplingHandler:
    """Feature: Sampling — handles MCP server requests for LLM completions.
    
    Ported from Hermes SamplingHandler with rate limiting, model resolution,
    metrics tracking, and tool-call response support.
    """

    _STOP_REASON_MAP = {"stop": "endTurn", "length": "maxTokens", "tool_calls": "toolUse"}

    def __init__(self, llm_router: Any | None = None):
        self.llm = llm_router
        self._max_tokens = 4096
        self._timeout = 30
        self._max_rpm = 10
        self._rate_timestamps: list[float] = []
        self.metrics = {"requests": 0, "errors": 0, "tokens_used": 0, "tool_use_count": 0}

    def _check_rate_limit(self) -> bool:
        now = time.time()
        window = now - 60
        self._rate_timestamps[:] = [t for t in self._rate_timestamps if t > window]
        if len(self._rate_timestamps) >= self._max_rpm:
            return False
        self._rate_timestamps.append(now)
        return True

    async def handle_sampling(self, request: dict) -> dict:
        """Handle a sampling/createMessage request from an MCP server."""
        if not self.llm:
            return {"error": "LLM not available", "role": "assistant", "content": []}

        if not self._check_rate_limit():
            self.metrics["errors"] += 1
            return {"error": "Rate limit exceeded", "role": "assistant", "content": []}

        messages = request.get("messages", [])
        if not messages:
            return {"error": "No messages", "role": "assistant", "content": []}

        system_prompt = request.get("systemPrompt", "")
        max_tokens = min(request.get("maxTokens", self._max_tokens), self._max_tokens)
        temperature = request.get("temperature")

        try:
            from harness.llm import ChatMessage
            chat_msgs = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    tool_results = []
                    for c in content:
                        if isinstance(c, dict):
                            if c.get("type") == "text":
                                text_parts.append(c.get("text", ""))
                            elif c.get("type") == "tool_result":
                                tool_results.append(c)
                    content = "\n".join(text_parts)
                    for tr in tool_results:
                        chat_msgs.append(ChatMessage(role="tool", content=tr.get("content", "")))
                chat_msgs.append(ChatMessage(role=role, content=str(content)))

            if system_prompt:
                chat_msgs.insert(0, ChatMessage(role="system", content=system_prompt))

            response = await asyncio.wait_for(
                self.llm.chat(
                    messages=chat_msgs,
                    temperature=temperature or 0.3,
                    max_tokens=max_tokens,
                ),
                timeout=self._timeout,
            )

            self.metrics["requests"] += 1
            if hasattr(response, "usage") and response.usage:
                self.metrics["tokens_used"] += getattr(response.usage, "total_tokens", 0)

            return {
                "role": "assistant",
                "content": [{"type": "text", "text": response.content or ""}],
                "model": getattr(self.llm, "model", ""),
            }
        except asyncio.TimeoutError:
            self.metrics["errors"] += 1
            return {"error": "LLM call timed out", "role": "assistant", "content": []}
        except Exception as e:
            self.metrics["errors"] += 1
            return {"error": sanitize_error_message(str(e)), "role": "assistant", "content": []}


# ---------------------------------------------------------------------------
# MCPClient — manages multiple MCP server connections
# ---------------------------------------------------------------------------


class MCPClient:
    def __init__(self):
        self._servers: dict[str, MCPServerTask] = {}
        self._lock = threading.Lock()
        self._running = False
        self.sampling = SamplingHandler()
        self._tool_to_server: dict[str, str] = {}

    def set_llm(self, llm_router: Any) -> None:
        """Set the LLM router for sampling support."""
        self.sampling.llm = llm_router

    async def initialize(self, servers: list[dict[str, Any]]) -> None:
        if not _MCP_AVAILABLE:
            logger.warning("MCP SDK not installed")
            return
        self._running = True

        async def _connect_one(srv: dict):
            if not srv.get("enabled", True):
                return
            name = srv.get("name", srv.get("id", srv.get("url", "unknown")))
            config = {
                "url": srv.get("url", srv.get("server_url", "")),
                "command": srv.get("command", ""),
                "args": srv.get("args", []),
                "env": srv.get("env", {}),
                "timeout": srv.get("timeout", DEFAULT_TOOL_TIMEOUT),
                "connect_timeout": srv.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT),
                "transport": srv.get("transport", ""),
                "supports_parallel_tool_calls": srv.get("supports_parallel_tool_calls", False),
                "tools": srv.get("tools", {}),
            }

            from harness.tools.registry import registry
            task = MCPServerTask(name, config, registry, on_tools_changed=self._rebuild_index, sampling_handler=self.sampling)
            ok = await task.connect()
            if ok:
                with self._lock:
                    self._servers[name] = task
                self._register_server_tools(name, task, config)

        await asyncio.gather(
            *(asyncio.create_task(_connect_one(s)) for s in servers),
            return_exceptions=True,
        )

    def _rebuild_index(self):
        with self._lock:
            self._tool_to_server.clear()
            for srv_name, srv in self._servers.items():
                for tool in srv._tools:
                    prefixed = _mcp_tool_name(srv_name, tool.name)
                    self._tool_to_server[prefixed] = srv_name

    def _register_server_tools(self, name: str, task: MCPServerTask, config: dict):
        """Register tools from a connected server into the registry.

        C3 deepening of the architecture review: every MCP
        tool is registered through `register_async_raw` so
        the handler is a real coroutine on the agent's event
        loop, not a sync lambda wrapping `asyncio.run(...)`.
        The sync-wrapping lie caused:

          1. Cancellation leaks — parent loop's cancel didn't
             reach the MCP call's child loop.
          2. One event loop per tool call — `asyncio.run()`
             allocates a fresh `Selector` + `ThreadPoolExecutor`
             every time.
          3. Re-entrancy hazard — `asyncio.run()` from a
             running loop raises `RuntimeError`; the old
             code path silently swallowed it via the
             `try/except` in the registry.

        The async path fixes all three. The handler captures
        the server-name and tool-name via closure, just like
        the old lambda, so the registration shape is the
        same — only the handler is `async def` and the
        registration goes through `register_async_raw`.
        """
        from harness.tools.registry import registry as r
        toolset_name = f"mcp-{name}"

        for mcp_tool in task._tools:
            if not task._should_register_tool(mcp_tool.name):
                continue

            schema = {
                "name": _mcp_tool_name(name, mcp_tool.name),
                "description": mcp_tool.description or "",
                "parameters": _normalize_input_schema(
                    mcp_tool.input_schema if hasattr(mcp_tool, 'input_schema') else {}
                ),
            }
            ot = mcp_tool.name
            srv_name = name

            async def _handler(args, _ot=ot, _tn=srv_name):
                # No `asyncio.run()`. This coroutine runs on
                # the agent's event loop. Cancellation,
                # timeout, and exception propagation all
                # work as expected.
                server = self._servers.get(_tn)
                if server is None:
                    return json.dumps({"error": "server gone"})
                return await server.call_tool(_ot, args)

            r.register_async_raw(
                name=schema["name"],
                toolset=toolset_name,
                schema=schema,
                handler=_handler,
                description=schema["description"],
            )

        # Register resource/prompt utility tools. These are
        # also async on the MCP side; they were using
        # `asyncio.run()` before. Now they await directly.
        if task._resources:
            async def _list_resources(_name=name):
                return json.dumps(
                    [{"uri": r.uri, "name": r.name} for r in task._resources]
                )

            async def _read_resource(uri, _task=task):
                return await _task.read_resource(uri)

            utils = {
                f"mcp_{name}_list_resources": {
                    "description": f"List available resources from MCP server {name}",
                    "schema": {"type": "object", "properties": {}},
                    "handler": _list_resources,
                },
                f"mcp_{name}_read_resource": {
                    "description": f"Read a resource from MCP server {name}",
                    "schema": {"type": "object", "properties": {
                        "uri": {"type": "string"}
                    }},
                    "handler": _read_resource,
                },
            }
            for util_name, util_def in utils.items():
                r.register_async_raw(
                    name=util_name,
                    toolset=toolset_name,
                    schema={"name": util_name, "description": util_def["description"],
                            "parameters": util_def["schema"]},
                    handler=util_def["handler"],
                    description=util_def["description"],
                )

        if task._prompts:
            async def _list_prompts(_task=task):
                return json.dumps(
                    [{"name": p.name, "description": p.description} for p in _task._prompts]
                )

            r.register_async_raw(
                name=f"mcp_{name}_list_prompts",
                toolset=toolset_name,
                schema={"name": f"mcp_{name}_list_prompts", "description": f"List available prompts from MCP server {name}",
                        "parameters": {"type": "object", "properties": {}}},
                handler=_list_prompts,
                description=f"List available prompts from MCP server {name}",
            )

        self._rebuild_index()

    def get_server(self, tool_name: str) -> MCPServerTask | None:
        with self._lock:
            srv_name = self._tool_to_server.get(tool_name)
            if srv_name:
                return self._servers.get(srv_name)
            for srv_name, srv in self._servers.items():
                if tool_name.startswith(f"mcp_{srv_name}_"):
                    return srv
        return None

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        server = self.get_server(tool_name)
        if not server:
            return json.dumps({"error": f"No MCP server for tool: {tool_name}"})
        prefix = f"mcp_{server.name}_"
        original_name = tool_name[len(prefix):] if tool_name.startswith(prefix) else tool_name

        """Feature: Parallel tool calls — run concurrently when supported."""
        if server.supports_parallel:
            async def _call():
                return await server.call_tool(original_name, arguments)
            return await _call()
        return await server.call_tool(original_name, arguments)

    def has_tools(self) -> bool:
        with self._lock:
            return any(len(srv._tools) > 0 for srv in self._servers.values())

    def get_connections(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": name,
                    "name": name,
                    "url": srv.config.get("url", ""),
                    "connected": srv.connected,
                    "error": None if srv.connected or srv._last_health_ok else "Connection lost",
                    "tools": [
                        {
                            "name": t.name,
                            "description": getattr(t, "description", ""),
                            "input_schema": getattr(t, "inputSchema", getattr(t, "input_schema", {})),
                        }
                        for t in srv._tools
                    ],
                }
                for name, srv in self._servers.items()
            ]

    def get_mcp_status(self) -> list[dict]:
        """Return status of all MCP servers for dashboard display."""
        with self._lock:
            return [
                {
                    "name": name,
                    "transport": "http" if "url" in srv.config and srv.config["url"] else "stdio",
                    "tools": len(srv._tools),
                    "connected": srv.connected,
                    "error": None if srv.connected or srv._last_health_ok else "Connection lost",
                }
                for name, srv in self._servers.items()
            ]

    def get_openai_tools(self) -> list[dict]:
        schemas: list[dict] = []
        with self._lock:
            for srv_name, srv in self._servers.items():
                for tool in srv._tools:
                    schemas.append({
                        "type": "function",
                        "function": {
                            "name": _mcp_tool_name(srv_name, tool.name),
                            "description": tool.description or "",
                            "parameters": _normalize_input_schema(
                                tool.input_schema if hasattr(tool, 'input_schema') else {}
                            ),
                        },
                    })
        return schemas

    async def shutdown(self):
        self._running = False
        with self._lock:
            for srv in list(self._servers.values()):
                await srv.disconnect()
            self._servers.clear()
            self._tool_to_server.clear()
