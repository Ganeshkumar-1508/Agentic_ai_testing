"""Backend factory — creates and tracks per-session execution environments.

Features:
  - Creates LocalEnvironment, DockerEnvironment, SSHEnvironment from config
  - Thread-safe singleton with double-checked locking
  - Tracks active backends per session for reuse and cleanup
  - Task-level env/timeout overrides
  - Approval callbacks for HITL (dangerous commands)
  - Sudo password callback for password-protected sudo
  - Orphan teardown on replacement
  - Proper shutdown lifecycle

Ported from Hermes + deer-flow (MIT License).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from .base import BaseEnvironment
from .backend_configs import get_backend_config
from .docker import DockerEnvironment
from .local import LocalEnvironment
from .ssh import SSHEnvironment

logger = logging.getLogger(__name__)

_BACKEND_REGISTRY: dict[str, type[BaseEnvironment]] = {
    "local": LocalEnvironment,
    "docker": DockerEnvironment,
    "ssh": SSHEnvironment,
}

# Active backend registry — tracks per-session environments
_active_backends: dict[str, BaseEnvironment] = {}
_env_lock = threading.Lock()


def clear_backend_cache() -> None:
    with _env_lock:
        _active_backends.clear()

# Per-task overrides: {task_id: {"env": dict, "timeout": int, ...}}
_task_overrides: dict[str, dict[str, Any]] = {}

# Callbacks
_approval_callback: Callable | None = None
_approval_lock = threading.Lock()
_sudo_password_callback: Callable | None = None
_sudo_lock = threading.Lock()


def register_backend(name: str, cls: type[BaseEnvironment]) -> None:
    _BACKEND_REGISTRY[name] = cls


def get_backend_class(backend_type: str) -> type[BaseEnvironment]:
    cls = _BACKEND_REGISTRY.get(backend_type)
    if cls is None:
        raise ValueError(f"Unknown backend_type: {backend_type!r}")
    return cls


def resolve_backend_type(db, session_id: str, default: str = "local") -> str:
    row = db.fetchone(
        "SELECT backend_type FROM sessions WHERE id = $1", [session_id],
    )
    if row and row[0]:
        return row[0]
    cfg_row = db.fetchone(
        "SELECT value FROM sandbox_config WHERE key = 'default_backend_type'",
    )
    if cfg_row and cfg_row[0]:
        return cfg_row[0]
    return default


def get_backend(
    db,
    session_id: str,
    *,
    backend_type: str | None = None,
    config: dict[str, Any] | None = None,
    cwd: str = "",
    timeout: int = 120,
    env: dict | None = None,
) -> BaseEnvironment:
    """Return a backend for *session_id*. Creates if not cached."""
    with _env_lock:
        existing = _active_backends.get(session_id)
        if existing is not None:
            return existing

    bt = backend_type or resolve_backend_type(db, session_id)
    cls = _BACKEND_REGISTRY.get(bt)
    if cls is None:
        raise ValueError(f"Unknown backend_type: {bt!r}. Known: {list(_BACKEND_REGISTRY)}")

    cfg = config if config is not None else get_backend_config(db, session_id)

    # Apply task-level overrides
    overrides = _task_overrides.get(session_id, {})

    kwargs: dict[str, Any] = {
        "session_id": session_id,
        "cwd": cwd or overrides.get("cwd", ""),
        "timeout": overrides.get("timeout", timeout),
    }
    merged_env = dict(env or {})
    merged_env.update(overrides.get("env", {}))
    if merged_env:
        kwargs["env"] = merged_env

    if bt == "local":
        pass
    elif bt == "docker":
        kwargs["image"] = cfg.get("image", "nikolaik/python-nodejs:python3.11-nodejs20")
        kwargs["cpu"] = cfg.get("cpu", 0)
        kwargs["memory_mb"] = cfg.get("memory_mb", 0)
        kwargs["disk_mb"] = cfg.get("disk_mb", 0)
        kwargs["network"] = cfg.get("network", True)
        kwargs["volumes"] = cfg.get("volumes")
    elif bt == "ssh":
        kwargs["host"] = cfg.get("host", "")
        kwargs["user"] = cfg.get("user", "")
        kwargs["port"] = int(cfg.get("port", 22))
        kwargs["key_path"] = cfg.get("key_path", "")

    backend = cls(**kwargs)
    with _env_lock:
        _active_backends[session_id] = backend
    return backend


def get_active_backend(session_id: str) -> BaseEnvironment | None:
    with _env_lock:
        return _active_backends.get(session_id)


def cleanup_backend(session_id: str) -> None:
    with _env_lock:
        backend = _active_backends.pop(session_id, None)
    if backend is not None:
        try:
            backend.cleanup()
        except Exception as exc:
            logger.warning("cleanup_backend %s failed: %s", session_id, exc)


def cleanup_all_backends() -> int:
    with _env_lock:
        ids = list(_active_backends.keys())
        _active_backends.clear()
    cleaned = 0
    for sid in ids:
        try:
            backend = get_active_backend(sid)
            if backend:
                backend.cleanup()
            cleaned += 1
        except Exception as exc:
            logger.warning("cleanup_all: %s failed: %s", sid, exc)
    return cleaned


def register_task_overrides(task_id: str, overrides: dict[str, Any]) -> None:
    _task_overrides[task_id] = dict(overrides)


def clear_task_overrides(task_id: str) -> None:
    _task_overrides.pop(task_id, None)


def resolve_task_overrides(task_id: str) -> dict[str, Any]:
    return dict(_task_overrides.get(task_id, {}))


def set_approval_callback(cb: Callable | None) -> None:
    global _approval_callback
    with _approval_lock:
        _approval_callback = cb


def get_approval_callback() -> Callable | None:
    with _approval_lock:
        return _approval_callback


def set_sudo_password_callback(cb: Callable | None) -> None:
    global _sudo_password_callback
    with _sudo_lock:
        _sudo_password_callback = cb


def get_sudo_password_callback() -> Callable | None:
    with _sudo_lock:
        return _sudo_password_callback


# ---------------------------------------------------------------------------
# Singleton provider (deer-flow pattern)
# ---------------------------------------------------------------------------

_default_factory: Callable | None = None
_factory_lock = threading.Lock()


def get_default_factory(**kwargs) -> Callable:
    """Thread-safe singleton with double-checked locking."""
    global _default_factory
    with _factory_lock:
        if _default_factory is not None:
            return _default_factory

    from .backend_configs import get_backend_config as _gbc

    def _factory(session_id, *, backend_type=None, config=None, cwd="", timeout=120, env=None):
        bt = backend_type or resolve_backend_type(kwargs.get("db"), session_id)
        cls = _BACKEND_REGISTRY.get(bt)
        if cls is None:
            raise ValueError(f"Unknown backend_type: {bt!r}")
        cfg = config if config is not None else _gbc(kwargs.get("db"), session_id)
        return cls(session_id=session_id, cwd=cwd, timeout=timeout, env=env or {})

    with _factory_lock:
        if _default_factory is None:
            _default_factory = _factory
        winner = _default_factory
    return winner


def shutdown_factory() -> None:
    """Shutdown all active backends and reset the singleton."""
    global _default_factory
    with _factory_lock:
        provider = _default_factory
        _default_factory = None
    cleanup_all_backends()
    if provider is not None:
        logger.info("Backend factory shut down")
