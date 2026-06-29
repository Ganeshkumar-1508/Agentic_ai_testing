"""Environment variable passthrough registry.

Skills that need certain env vars in sandboxed execution environments
can register them here. By default the blocklist strips secrets from
subprocesses; this module provides a session-scoped allowlist.

Ported from Hermes (MIT License).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Iterable

logger = logging.getLogger(__name__)

_allowed_env_vars_var: ContextVar[set[str]] = ContextVar("_allowed_env_vars")


def _get_allowed() -> set[str]:
    try:
        return _allowed_env_vars_var.get()
    except LookupError:
        val: set[str] = set()
        _allowed_env_vars_var.set(val)
        return val


def add_env_passthrough(names: str | Iterable[str]) -> None:
    """Register env var names that should pass through to sandboxes."""
    if isinstance(names, str):
        names = [names]
    allowed = _get_allowed()
    allowed.update(names)
    _allowed_env_vars_var.set(allowed)


def remove_env_passthrough(names: str | Iterable[str]) -> None:
    """Remove env var names from the passthrough allowlist."""
    if isinstance(names, str):
        names = [names]
    allowed = _get_allowed()
    allowed.difference_update(names)
    _allowed_env_vars_var.set(allowed)


def clear_env_passthrough() -> None:
    """Clear all passthrough entries for the current session context."""
    _allowed_env_vars_var.set(set())


def is_env_passthrough(name: str) -> bool:
    """Return True if *name* is allowed to pass through the blocklist."""
    return name in _get_allowed()


def get_all_passthrough() -> frozenset[str]:
    """Return all currently registered passthrough env var names."""
    return frozenset(_get_allowed())
