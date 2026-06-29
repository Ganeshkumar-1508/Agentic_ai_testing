"""Lifecycle hooks + PluginManager for the agent harness.

Three hook power levels:
   1. Observer  — return None. Fire-and-forget (logging, metrics, audit).
   2. Blocking  — return ``{"action": "block", "message": "..."}``.
                  ``pre_tool_call`` only. First block wins.
   3. Transform — return a string to replace output, or None to pass through.
                  ``transform_*`` hooks only. First non-None string wins.

Filesystem hooks: Shell scripts at ``<cwd>/.testai/hooks/<event>/<name>.sh``
and ``~/.testai/hooks/<event>/<name>.sh`` are loaded at startup and called
with JSON stdin/stdout matching the hook protocol.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid hook names (12 hooks across 4 categories)
# ---------------------------------------------------------------------------

VALID_HOOKS: set[str] = {
    # Agent Loop (6)
    "pre_llm_call",
    "post_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "on_session_start",
    "on_session_end",
    # Transform (3)
    "transform_llm_output",
    "transform_tool_result",
    "transform_terminal_output",
    # Subagent (1)
    "subagent_stop",
    # Approval (2)
    "pre_approval_request",
    "post_approval_response",
}

# ---------------------------------------------------------------------------
# HookRegistry — in-process hook storage
# ---------------------------------------------------------------------------

HookHandler = Callable[..., Any]


class HookRegistry:
    """Stores registered hook callbacks. Thread-safe for reads.

    Each hook name maps to an ordered list of callbacks.
    Callbacks are invoked in registration order.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = {}

    def register(self, event: str, handler: HookHandler) -> None:
        if event not in VALID_HOOKS:
            logger.warning("Ignoring unknown hook '%s'", event)
            return
        self._handlers.setdefault(event, []).append(handler)

    def unregister(self, event: str, handler: HookHandler) -> None:
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h is not handler]

    def clear(self) -> None:
        self._handlers.clear()

    # -- Dispatch -----------------------------------------------------------

    async def invoke(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Call all registered callbacks for *hook_name*.

        Supports both sync and async callbacks (auto-detected via
        ``inspect.iscoroutinefunction``). Each callback is wrapped in
        its own try/except so a misbehaving plugin cannot break the loop.
        """
        results: list[Any] = []
        for cb in self._handlers.get(hook_name, []):
            try:
                if inspect.iscoroutinefunction(cb):
                    ret = await cb(**kwargs)
                else:
                    ret = cb(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as exc:
                logger.warning("Hook '%s' callback %s raised: %s", hook_name, getattr(cb, "__name__", repr(cb)), exc)
        return results

    async def invoke_blocking(self, hook_name: str, **kwargs: Any) -> str | None:
        """Invoke ``pre_tool_call`` hooks, return the first block message.

        Returns ``None`` when no hook blocks execution.
        """
        for cb in self._handlers.get(hook_name, []):
            try:
                if inspect.iscoroutinefunction(cb):
                    ret = await cb(**kwargs)
                else:
                    ret = cb(**kwargs)
                if isinstance(ret, dict) and ret.get("action") == "block":
                    msg = ret.get("message", "")
                    if isinstance(msg, str) and msg:
                        return msg
            except Exception as exc:
                logger.warning("Hook '%s' callback %s raised: %s", hook_name, getattr(cb, "__name__", repr(cb)), exc)
        return None

    async def invoke_transform(self, hook_name: str, text: str, **kwargs: Any) -> str:
        """Invoke ``transform_*`` hooks, return the first non-None replacement.

        Returns the original text when no hook transforms it.
        """
        for cb in self._handlers.get(hook_name, []):
            try:
                if inspect.iscoroutinefunction(cb):
                    ret = await cb(text=text, **kwargs)
                else:
                    ret = cb(text=text, **kwargs)
                if isinstance(ret, str) and ret:
                    return ret
            except Exception as exc:
                logger.warning("Hook '%s' callback %s raised: %s", hook_name, getattr(cb, "__name__", repr(cb)), exc)
        return text


# ---------------------------------------------------------------------------
# Module-level singleton.
# ---------------------------------------------------------------------------

_hook_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    global _hook_registry
    if _hook_registry is None:
        _hook_registry = HookRegistry()
    return _hook_registry


def hooks() -> HookRegistry:
    """Shortcut — returns the module-level HookRegistry singleton."""
    return get_hook_registry()


# ---------------------------------------------------------------------------
# Filesystem hook loader — shell scripts + HTTP hooks from .testai/hooks/
# ---------------------------------------------------------------------------

HOOKS_SEARCH_PATHS = [
    Path.home() / ".testai" / "hooks",       # Global
    Path.cwd() / ".testai" / "hooks",         # Project
]

SUPPORTED_HOOK_EVENTS = {
    "PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit",
    "PostToolUseFailure", "Stop", "Notification",
}


def load_filesystem_hooks(registry: HookRegistry | None = None) -> HookRegistry:
    """Scan filesystem for shell/HTTP hook scripts and register them.

    Directory structure:
      <path>/PreToolUse/block-destructive.sh
      <path>/PostToolUse/format-on-write.sh
      <path>/SessionStart/inject-context.sh

    Each script receives JSON on stdin and returns JSON on stdout
    (matching the hook JSON protocol).
    """
    reg = registry or get_hook_registry()
    for base in HOOKS_SEARCH_PATHS:
        if not base.exists():
            continue
        for event_dir in base.iterdir():
            if not event_dir.is_dir() or event_dir.name.startswith("."):
                continue
            event_name = event_dir.name
            if event_name not in SUPPORTED_HOOK_EVENTS:
                logger.debug("Ignoring unknown hook event directory: %s", event_name)
                continue
            for script in sorted(event_dir.iterdir()):
                if script.suffix not in {".sh", ".bash", ".py", ".js"}:
                    continue
                if not os.access(str(script), os.X_OK):
                    logger.warning("Hook script not executable: %s", script)
                    continue
                internal_event = _filesystem_event_to_internal(event_name)
                if internal_event:
                    handler = _make_shell_hook_handler(str(script), event_name)
                    reg.register(internal_event, handler)
                    logger.info("Loaded hook: %s -> %s", script, internal_event)
    return reg


def _filesystem_event_to_internal(event_name: str) -> str | None:
    """Map filesystem directory names to internal hook event names."""
    mapping = {
        "PreToolUse": "pre_tool_call",
        "PostToolUse": "post_tool_call",
        "SessionStart": "on_session_start",
        "UserPromptSubmit": "pre_llm_call",
        "PostToolUseFailure": "post_tool_call",
        "Stop": "on_session_end",
    }
    return mapping.get(event_name)


def _make_shell_hook_handler(script_path: str, event_name: str) -> HookHandler:
    """Create an async hook handler that calls a shell script with JSON protocol.

    The script receives JSON on stdin:
      {"tool_name": "Bash", "tool_input": {"command": "..."}, ...}

    It returns JSON on stdout:
      {"permissionDecision": "deny", "permissionDecisionReason": "..."}
    """
    async def handler(**kwargs: Any) -> dict[str, Any] | None:
        try:
            input_data = json.dumps(kwargs, default=str)
            proc = await asyncio.create_subprocess_exec(
                script_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate(
                input=input_data.encode("utf-8"),
                timeout=10.0,
            )
            if proc.returncode == 2:
                # Exit code 2 = blocking error
                try:
                    result = json.loads(stdout_bytes.decode("utf-8"))
                    hook_output = result.get("hookSpecificOutput", {})
                    decision = hook_output.get("permissionDecision", "deny")
                    reason = hook_output.get("permissionDecisionReason", "Blocked by hook")
                    return {"action": "block" if decision == "deny" else "allow", "message": reason}
                except json.JSONDecodeError:
                    stderr = stderr_bytes.decode("utf-8").strip()
                    return {"action": "block", "message": stderr or f"Hook {script_path} blocked"}
            elif proc.returncode == 0 and stdout_bytes.strip():
                try:
                    result = json.loads(stdout_bytes.decode("utf-8"))
                    hook_output = result.get("hookSpecificOutput", {})
                    decision = hook_output.get("permissionDecision", "allow")
                    if decision == "deny":
                        reason = hook_output.get("permissionDecisionReason", "Denied by hook")
                        return {"action": "block", "message": reason}
                except json.JSONDecodeError:
                    pass
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Hook %s timed out after 10s", script_path)
            return None
        except Exception as exc:
            logger.warning("Hook %s failed: %s", script_path, exc)
            return None

    return handler


# ---------------------------------------------------------------------------
# Plugin context  — handed to each plugin's register() function
# ---------------------------------------------------------------------------


@dataclass
class PluginManifest:
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    requires_env: list[str] = field(default_factory=list)
    provides_tools: list[str] = field(default_factory=list)
    provides_hooks: list[str] = field(default_factory=list)
    kind: str = "standalone"
    path: str = ""


class PluginContext:
    """Facade given to plugins so they can register hooks and tools."""

    def __init__(self, manifest: PluginManifest, registry: HookRegistry) -> None:
        self.manifest = manifest
        self._registry = registry

    def register_hook(self, event: str, handler: HookHandler) -> None:
        """Register a lifecycle hook callback."""
        self._registry.register(event, handler)

    def register_tool(self, name: str, toolset: str, schema: dict, handler: Callable) -> None:  # noqa: ARG002
        """Register a tool in the global tool registry."""
        from harness.tools.registry import registry
        registry.register_tool(handler, toolset=toolset)


# ---------------------------------------------------------------------------
# Plugin discovery  — directory scanning + config
# ---------------------------------------------------------------------------


def discover_plugins(registry: HookRegistry | None = None) -> None:
    """Scan plugin directories and load filesystem hooks."""
    reg = registry or get_hook_registry()
    load_filesystem_hooks(reg)
    """Scan plugin directories and load discovered plugins.

    Sources (earlier overrides later on name collision):
      1. BUNDLED  — backend/plugins/<name>/
      2. CONFIG   — listed in config
      3. USER     — ~/.testai/plugins/<name>/
      4. PROJECT  — ./.testai/plugins/<name>/
    """
    reg = registry or get_hook_registry()
    scanned: set[str] = set()

    # Bundled plugins
    bundled = Path(__file__).resolve().parent / "plugins"
    if bundled.exists():
        _scan_dir(bundled, reg, scanned, source="bundled")

    # User plugins
    user_dir = Path.home() / ".testai" / "plugins"
    if user_dir.exists():
        _scan_dir(user_dir, reg, scanned, source="user")

    # Project plugins
    project_dir = Path.cwd() / ".testai" / "plugins"
    if project_dir.exists():
        _scan_dir(project_dir, reg, scanned, source="project")


def _scan_dir(root: Path, reg: HookRegistry, scanned: set[str], source: str) -> None:
    """Scan a single plugin directory for plugin.yaml + __init__.py."""
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name.startswith("_"):
            continue
        if child.name in scanned:
            continue

        manifest_file = child / "plugin.yaml"
        init_file = child / "__init__.py"
        if not manifest_file.exists() or not init_file.exists():
            continue

        try:
            manifest_data = yaml.safe_load(manifest_file.read_text("utf-8"))
            if not isinstance(manifest_data, dict):
                continue
            manifest = PluginManifest(
                name=manifest_data.get("name", child.name),
                version=str(manifest_data.get("version", "")),
                description=str(manifest_data.get("description", "")),
                author=str(manifest_data.get("author", "")),
                requires_env=manifest_data.get("requires_env", []),
                provides_tools=manifest_data.get("provides_tools", []),
                provides_hooks=manifest_data.get("provides_hooks", []),
                kind=manifest_data.get("kind", "standalone"),
                path=str(child),
            )
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", manifest_file, exc)
            continue

        # Check env requirements
        if manifest.requires_env:
            missing = [k for k in manifest.requires_env if not os.environ.get(k)]
            if missing:
                logger.info("Plugin '%s' skipped — missing env: %s", manifest.name, missing)
                continue

        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{child.name}", init_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "register"):
                ctx = PluginContext(manifest, reg)
                mod.register(ctx)
                logger.info("Plugin '%s' loaded from %s", manifest.name, source)
        except Exception as exc:
            logger.warning("Failed to load plugin '%s': %s", manifest.name, exc)
            continue

        scanned.add(child.name)
