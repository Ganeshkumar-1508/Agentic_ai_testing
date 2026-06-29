"""Plugin system — discover and load plugins from directories and pip packages.

Plugins can register:
  - Tools (via tool registry)
  - Hooks (lifecycle callbacks)
  - Memory providers
  - CLI commands

Discovery sources (in priority order):
  1. ~/.testai/plugins/ (user plugins)
  2. .testai/plugins/ (project plugins)
  3. pip entry points (testai_plugins)
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_loaded_plugins: dict[str, Any] = {}


def get_plugin_dirs() -> list[Path]:
    """Get plugin search directories in priority order."""
    testai_home = Path(os.environ.get("TESTAI_HOME", Path.home() / ".testai"))
    return [
        testai_home / "plugins",
        Path.cwd() / ".testai" / "plugins",
    ]


def discover_plugins() -> list[str]:
    """Discover available plugin names from directories and entry points."""
    names: set[str] = set()

    # Filesystem plugins
    for d in get_plugin_dirs():
        if d.exists():
            for entry in d.iterdir():
                if entry.is_dir() and (entry / "__init__.py").exists():
                    names.add(entry.name)
                elif entry.suffix == ".py" and entry.stem != "__init__":
                    names.add(entry.stem)

    # Pip entry points
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="testai_plugins")
        names.update(ep.name for ep in eps)
    except Exception:
        pass

    return sorted(names)


def load_plugin(name: str) -> Any | None:
    """Load a single plugin by name. Returns the plugin module or None."""
    if name in _loaded_plugins:
        return _loaded_plugins[name]

    module = None

    # Try filesystem plugins
    for d in get_plugin_dirs():
        plugin_path = d / f"{name}.py"
        if plugin_path.exists():
            spec = importlib.util.spec_from_file_location(f"testai_plugin_{name}", plugin_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception as e:
                    logger.error("Failed to load plugin %s: %s", name, e)
                    module = None
                break

        plugin_dir = d / name
        if plugin_dir.is_dir() and (plugin_dir / "__init__.py").exists():
            init_path = plugin_dir / "__init__.py"
            spec = importlib.util.spec_from_file_location(f"testai_plugin_{name}", init_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception as e:
                    logger.error("Failed to load plugin %s: %s", name, e)
                    module = None
                break

    # Try pip entry points
    if module is None:
        try:
            from importlib.metadata import entry_points
            for ep in entry_points(group="testai_plugins"):
                if ep.name == name:
                    module = ep.load()
                    break
        except Exception:
            pass

    if module is not None:
        _loaded_plugins[name] = module
        logger.info("Loaded plugin: %s", name)

    return module


def load_all_plugins():
    """Discover and load all available plugins."""
    for name in discover_plugins():
        try:
            load_plugin(name)
        except Exception as e:
            logger.warning("Failed to load plugin %s: %s", name, e)


class PluginContext:
    """Context API that plugins use to register capabilities.

    A plugin's setup() function receives a PluginContext instance.
    """

    def __init__(self, name: str):
        self.name = name
        self._tools: list[type] = []
        self._hooks: list[tuple[str, Callable]] = []
        self._commands: list[tuple[str, Callable]] = []

    def register_tool(self, tool_cls: type) -> None:
        """Register a tool class. It will be instantiated and added to the registry."""
        self._tools.append(tool_cls)

    def register_hook(self, event: str, handler: Callable) -> None:
        """Register a lifecycle hook handler.

        Events: 'session_start', 'session_end', 'pre_tool', 'post_tool', 'pre_llm', 'post_llm'
        """
        self._hooks.append((event, handler))

    def register_command(self, name: str, handler: Callable) -> None:
        """Register a CLI command."""
        self._commands.append((name, handler))

    def apply(self):
        """Apply all registrations from this plugin."""
        for tool_cls in self._tools:
            try:
                from harness.tools.registry import registry
                instance = tool_cls()
                registry.register_tool(instance, toolset="plugin")
                logger.debug("Plugin %s registered tool: %s", self.name, instance.name)
            except Exception as e:
                logger.warning("Plugin %s tool registration failed: %s", self.name, e)

        for event, handler in self._hooks:
            try:
                from harness._hook_system import get_hook_registry; hook_registry = get_hook_registry()
                hook_registry.register(event, handler)
                logger.debug("Plugin %s registered hook: %s", self.name, event)
            except Exception as e:
                logger.warning("Plugin %s hook registration failed: %s", self.name, e)

        logger.info("Plugin %s applied: %d tools, %d hooks, %d commands",
                     self.name, len(self._tools), len(self._hooks), len(self._commands))


def setup_plugin(name: str) -> PluginContext | None:
    """Load a plugin and call its setup() function.

    Expected plugin structure:
        def setup(ctx: PluginContext):
            ctx.register_tool(MyTool)
            ctx.register_hook('session_start', my_handler)
    """
    module = load_plugin(name)
    if module is None:
        return None

    if hasattr(module, "setup"):
        ctx = PluginContext(name)
        try:
            module.setup(ctx)
            ctx.apply()
            return ctx
        except Exception as e:
            logger.error("Plugin %s setup failed: %s", name, e)
            return None

    logger.info("Plugin %s loaded (no setup function)", name)
    return None
