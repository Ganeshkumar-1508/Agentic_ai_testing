"""Shared constants for TestAI.

Import-safe module with no dependencies — mirrors the pattern of
``hermes_agent.hermes_constants`` but for the ``TESTAI_HOME`` root.

All TestAI core code that needs to read or write user-level state
(``~/.testai/skills/``, ``~/.testai/tools/``, etc.) should import from
here so that:
    1. Multiple consumers share a single source of truth for paths.
    2. Test fixtures can override ``TESTAI_HOME`` once and have all
       consumers see the override.
    3. User-facing messages can show a ``~/``-shortened path that respects
       the active ``TESTAI_HOME``.

Resolution order (mirrors ``hermes_constants.get_hermes_home``):
    1. ``TESTAI_HOME`` environment variable (explicit override).
    2. ``~/.testai`` (the default for production runs).

Use this module instead of hardcoding ``Path.home() / ".testai"`` anywhere
that reads or writes state — that pattern broke hermes profile handling
(see hermes AGENTS.md §"DO NOT hardcode ~/.hermes paths") and we want
the same fix applied here from day one.
"""

from __future__ import annotations

import os
import sys
from contextvars import ContextVar, Token
from pathlib import Path

_UNSET: object = object()
_TESTAI_HOME_OVERRIDE: ContextVar[str | object] = ContextVar(
    "_TESTAI_HOME_OVERRIDE", default=_UNSET
)


def set_testai_home_override(path: str | Path | None) -> Token:
    """Set a context-local TESTAI_HOME override and return its reset token.

    For in-process, per-task scoping. Deliberately does not mutate
    ``os.environ`` (shared by every thread in the process).
    """
    value: object = _UNSET if path is None else str(path)
    return _TESTAI_HOME_OVERRIDE.set(value)


def reset_testai_home_override(token: Token) -> None:
    """Restore the previous context-local TESTAI_HOME override."""
    _TESTAI_HOME_OVERRIDE.reset(token)


def get_testai_home_override() -> str | None:
    """Return the active context-local TESTAI_HOME override, if any."""
    override = _TESTAI_HOME_OVERRIDE.get()
    if override is _UNSET or not override:
        return None
    return str(override)


def get_testai_home() -> Path:
    """Return the TestAI home directory (default: ``~/.testai``).

    Reads ``TESTAI_HOME`` env var, falls back to ``~/.testai``. This is
    the single source of truth — all other copies should import this.

    Mirrors ``hermes_constants.get_hermes_home()``.
    """
    override = get_testai_home_override()
    if override:
        return Path(override)

    val = os.environ.get("TESTAI_HOME", "").strip()
    if val:
        return Path(val)

    return Path.home() / ".testai"


def display_testai_home() -> str:
    """Return a user-friendly display string for the current TESTAI_HOME.

    Uses ``~/`` shorthand for readability::

        default:  ``~/.testai``
        override: ``/opt/testai-data``

    Use this in **user-facing** print/log messages instead of hardcoding
    ``~/.testai``. For code that needs a real ``Path``, use
    :func:`get_testai_home` instead.

    Mirrors ``hermes_constants.display_hermes_home()``.
    """
    home = get_testai_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


def get_skills_dir() -> Path:
    """Return the TestAI **user** skills directory (default: ``TESTAI_HOME/skills/``).

    For user-installed skills that override or supplement the bundled set.
    Mirrors ``hermes_constants.get_skills_dir()``.
    """
    return get_testai_home() / "skills"


def get_bundled_skills_dir(default: Path | None = None) -> Path:
    """Return the bundled skills directory that ships with the TestAI repo.

    Resolution order (mirrors ``hermes_constants.get_bundled_skills_dir()``):
        1. ``TESTAI_BUNDLED_SKILLS`` env var (Nix / explicit override)
        2. Caller-supplied ``default`` (the source-checkout path)
        3. ``<TESTAI_HOME>/skills`` last-resort

    In the source checkout, the bundled location is the project-level
    ``.testai/skills/`` directory; in containerized deployments it is
    set to whatever path the Dockerfile or compose mount exposes.
    """
    override = os.getenv("TESTAI_BUNDLED_SKILLS", "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_testai_home() / "skills"


def get_tools_dir() -> Path:
    """Return the TestAI user-tools directory (default: ``TESTAI_HOME/tools/``).

    Matches the tool-discovery scan in
    :mod:`harness.tools.registry` — user-installed tools placed here are
    auto-discovered alongside the bundled ``harness/tools/`` set.
    """
    return get_testai_home() / "tools"


def get_plugins_dir() -> Path:
    """Return the TestAI user-plugins directory (default: ``TESTAI_HOME/plugins/``).

    Reserved for the future TestAI plugin surface. Mirrors hermes's
    ``$HERMES_HOME/plugins/`` user-extension point.
    """
    return get_testai_home() / "plugins"


def is_container() -> bool:
    """Return True when running inside a Docker/Podman container.

    Mirrors ``hermes_constants.is_container()``. Result is cached for
    the process lifetime.
    """
    cached = getattr(is_container, "_cached", None)
    if cached is not None:
        return cached

    detected = False
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        detected = True
    else:
        try:
            cgroup = Path("/proc/1/cgroup").read_text()
            if "docker" in cgroup or "podman" in cgroup or "/lxc/" in cgroup:
                detected = True
        except OSError:
            pass

    is_container._cached = detected  # type: ignore[attr-defined]
    return detected


def warn_if_fallback_active(active_marker: str | None) -> None:
    """Emit a one-shot warning when ``TESTAI_HOME`` is unset but a custom
    marker file indicates the user is in a non-default context.

    Mirrors hermes's "profile fallback" warning pattern. Currently a
    no-op stub — wire to a marker file when TestAI adopts multi-profile
    support.
    """
    if not active_marker:
        return
    try:
        sys.stderr.write(
            f"[TESTAI_HOME fallback] TESTAI_HOME is unset but marker "
            f"indicates {active_marker!r}. Falling back to ~/.testai.\n"
        )
        sys.stderr.flush()
    except Exception:
        pass
