"""Environment variable loader — .env file support for API keys.

Loads ``.env`` files in order (later overrides earlier):
  1. ``~/.testai/.env`` (global)
  2. ``<cwd>/.testai/.env`` (project)

Keys are loaded into ``os.environ`` so they're available via ``os.getenv()``.

Write functions save keys back to the project ``.env`` file.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def get_env_dir(scope: str = "project") -> Path:
    if scope == "global":
        d = Path.home() / ".testai"
        d.mkdir(parents=True, exist_ok=True)
        return d
    cwd = Path.cwd()
    project_dir = cwd / ".testai"
    if project_dir.exists():
        return project_dir
    home_dir = Path.home() / ".testai"
    home_dir.mkdir(parents=True, exist_ok=True)
    return home_dir


def get_env_path(scope: str = "project") -> Path:
    return get_env_dir(scope) / ".env"


def load_all_envs() -> dict[str, tuple[str, str]]:
    """Load and merge all .env files. Returns {key: (value, source_scope)}."""
    result: dict[str, tuple[str, str]] = {}
    for scope in ("global", "project"):
        path = get_env_path(scope)
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("\"'")
                if key:
                    result[key] = (val, scope)
        except Exception as e:
            logger.warning("Failed to load env file %s: %s", path, e)
    return result


def load_env_file(path: Path, force: bool = False) -> None:
    """Load a single .env file into os.environ (does not override existing unless force=True)."""
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and (force or key not in os.environ):
                os.environ[key] = val
    except Exception as e:
        logger.warning("Failed to load env file %s: %s", path, e)


def load_env(force: bool = False) -> None:
    """Load all .env files into os.environ. If force=True, overwrite existing vars."""
    global_path = Path.home() / ".testai" / ".env"
    project_path = Path.cwd() / ".testai" / ".env"

    load_env_file(global_path, force=force)
    load_env_file(project_path, force=force)

    if global_path.exists() or project_path.exists():
        logger.info("Loaded .env files (global=%s, project=%s)",
                     global_path.exists(), project_path.exists())


def write_key(key: str, value: str, scope: str = "project") -> None:
    """Write or update a single key in the specified scope's .env file."""
    env_path = get_env_path(scope=scope)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#") or "=" not in line_stripped:
                continue
            k, _, v = line_stripped.partition("=")
            existing[k.strip()] = v.strip().strip("\"'")

    existing[key] = value

    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    os.environ[key] = value
    logger.info("Wrote key '%s' to %s", key, env_path)


def delete_key(key: str) -> None:
    """Remove a key from the project .env file."""
    env_path = get_env_path()
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    remaining = [l for l in lines if not l.strip().startswith(key + "=")]
    env_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    os.environ.pop(key, None)
    logger.info("Removed key '%s' from %s", key, env_path)


def get_provider_env_key(provider_name: str) -> str:
    """Return the env var name for a provider's API key."""
    safe = provider_name.upper().replace("-", "_").replace(" ", "_")
    return f"{safe}_API_KEY"


def list_keys(prefix: str | None = None) -> list[tuple[str, str]]:
    """List all keys matching an optional prefix from os.environ."""
    result: list[tuple[str, str]] = []
    for key in sorted(os.environ.keys()):
        if prefix and not key.startswith(prefix):
            continue
        result.append((key, os.environ[key]))
    return result
