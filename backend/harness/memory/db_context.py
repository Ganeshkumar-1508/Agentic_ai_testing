"""Database context — replaces the Database._instance singleton pattern.

Usage:
    from harness.memory.db_context import get_db

    db = get_db()  # returns the Database instance or None

For modules that receive DB via DI (AgentDependencies, constructor),
use the injected instance directly. This module is for transitional
use in tools and modules that can't yet receive DI.

The instance is set once at startup via `set_db()` and read by `get_db()`.
This is still a module-level global — but it's an explicit, documented
seam rather than a class-attribute mutation on Database.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.memory.database import Database

_instance: Database | None = None


def set_db(db: "Database") -> None:
    """Set the global Database instance. Called once at startup."""
    global _instance
    _instance = db


def get_db() -> "Database | None":
    """Get the global Database instance. Returns None if not set."""
    return _instance
