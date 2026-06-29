"""File passthrough registry for remote backends.

Remote backends (SSH, future Modal, Daytona) run in isolated environments
with no host files. This module ensures credential files, skills, and
cache directories are synced into those environments.

**Credentials** — session-scoped registry fed by skill declarations and
user config. Only files under ``~/.testai/`` are allowed (prevents path
traversal).

**Skills** — local skill directories synced to remote so the agent
can load and execute skills inside the sandbox.

**Cache** — gateway-cached uploads, browser screenshots, processed
media synced for agent consumption.

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import logging
import os
import posixpath
from contextvars import ContextVar
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_registered_files_var: ContextVar[dict[str, str]] = ContextVar("_registered_files")


def _get_registered() -> dict[str, str]:
    try:
        return _registered_files_var.get()
    except LookupError:
        val: dict[str, str] = {}
        _registered_files_var.set(val)
        return val


def _testai_home() -> Path:
    return Path.home() / ".testai"


def register_credential_file(
    relative_path: str,
    container_base: str = "/root/.testai",
) -> bool:
    """Register a credential file for syncing into remote sandboxes.

    *relative_path* is relative to ``~/.testai/``.
    Rejects absolute paths and path traversal (``..``).
    """
    home = _testai_home()
    if os.path.isabs(relative_path):
        logger.warning("credential_files: rejected absolute path %r", relative_path)
        return False
    host_path = (home / relative_path).resolve()
    try:
        host_path.relative_to(home.resolve())
    except ValueError:
        logger.warning("credential_files: path traversal %r", relative_path)
        return False
    if not host_path.is_file():
        logger.debug("credential_files: skipping %s (not found)", host_path)
        return False
    registered = _get_registered()
    container_path = posixpath.join(container_base, relative_path.replace("\\", "/"))
    registered[str(host_path)] = container_path
    logger.info("credential_files: registered %s -> %s", host_path, container_path)
    return True


def register_credential_files(files: list[str]) -> None:
    """Register multiple credential files at once."""
    for f in files:
        register_credential_file(f)


def clear_credential_files() -> None:
    """Clear all registered credential files for the current context."""
    try:
        _registered_files_var.set({})
    except Exception:
        pass


def get_credential_file_mounts() -> list[dict[str, str]]:
    """Return list of {host_path, container_path} for registered credentials."""
    return [
        {"host_path": host, "container_path": container}
        for host, container in _get_registered().items()
    ]


def iter_skills_files(container_base: str = "/root/.testai") -> list[dict[str, str]]:
    """Enumerate skill files to sync to remote."""
    files: list[dict[str, str]] = []
    skills_dir = _testai_home() / "skills"
    if not skills_dir.is_dir():
        return files
    for fpath in skills_dir.rglob("*"):
        if fpath.is_file():
            rel = fpath.relative_to(_testai_home())
            container_path = posixpath.join(container_base, rel.as_posix())
            files.append({"host_path": str(fpath), "container_path": container_path})
    return files


def get_skills_directory_mount() -> list[dict[str, str]]:
    """Return the skills directory mount point."""
    skills_dir = _testai_home() / "skills"
    if skills_dir.is_dir():
        return [{"host_path": str(skills_dir), "container_path": "/root/.testai/skills"}]
    return []


def iter_cache_files(container_base: str = "/root/.testai") -> list[dict[str, str]]:
    """Enumerate cache files to sync to remote."""
    files: list[dict[str, str]] = []
    cache_dir = _testai_home() / "cache"
    if not cache_dir.is_dir():
        return files
    for fpath in cache_dir.rglob("*"):
        if fpath.is_file():
            rel = fpath.relative_to(_testai_home())
            container_path = posixpath.join(container_base, rel.as_posix())
            files.append({"host_path": str(fpath), "container_path": container_path})
    return files


def get_cache_directory_mounts() -> list[dict[str, str]]:
    """Return the cache directory mount point."""
    cache_dir = _testai_home() / "cache"
    if cache_dir.is_dir():
        return [{"host_path": str(cache_dir), "container_path": "/root/.testai/cache"}]
    return []
