from harness._hook_system import (
    HookRegistry,
    PluginManifest,
    VALID_HOOKS,
    discover_plugins,
    get_hook_registry,
    hooks,
    load_filesystem_hooks,
)

hook_registry = get_hook_registry()

__all__ = [
    "hook_registry",
    "HookRegistry",
    "PluginManifest",
    "VALID_HOOKS",
    "discover_plugins",
    "get_hook_registry",
    "hooks",
    "load_filesystem_hooks",
]
