"""Docker utility helpers for the agent-facing docker tools.

This module predates the tool-based architecture; it holds
the *tool-level* utilities the agent's `docker_executor` and
`docker_image_list` tools use. The container-lifecycle state
(records, locks, the per-session activity tracking) used to
live here too, but the C5 deepening of the architecture
review moved that into a typed `ContainerRegistry`
Protocol at `harness.sandbox.registry`. The `SandboxManager`
and the agent's `docker_executor` tool now share container
state through that Protocol; this module is just the
tool-utility surface.

What stays here (tool-level utilities):

  - `find_docker(force_resolve=False)` — cascading binary
    resolution: env override → `docker` on PATH → `podman`
    on PATH → well-known Docker Desktop install locations.
  - `_ensure_docker_available()` — pre-flight `docker
    version` check with a clear actionable error.
  - `_BASE_SECURITY_ARGS`, `build_security_args(...)` — the
    hardened-Docker baseline (cap-drop ALL, no-new-privileges,
    pids-limit, tmpfs) plus the per-call overrides (memory,
    cpu, network, env, mounts).

What moved out (C5):

  - `_container_records`, `_lock`, `touch_container`,
    `list_containers`, `destroy_container` — moved to
    `harness.sandbox.registry.InProcessContainerRegistry`.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# Common Docker Desktop install paths checked when 'docker' is not in PATH.
# macOS Intel: /usr/local/bin, macOS Apple Silicon (Homebrew): /opt/homebrew/bin,
# Docker Desktop app bundle: /Applications/Docker.app/Contents/Resources/bin
_DOCKER_SEARCH_PATHS = [
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
    "/Applications/Docker.app/Contents/Resources/bin/docker",
]

# Cached binary resolution. The first call wins, but explicit
# TESTAI_DOCKER_BINARY env var always overrides the cache.
_docker_executable: str | None = None


def find_docker(force_resolve: bool = False) -> str | None:
    """Locate the docker (or podman) CLI binary.

    Resolution order:
      1. ``TESTAI_DOCKER_BINARY`` env override (explicit, wins always)
      2. ``docker`` on PATH via ``shutil.which``
      3. ``podman`` on PATH (drop-in compatible with the docker CLI
         we use, so we accept it as a fallback)
      4. Well-known macOS Docker Desktop install locations

    Returns the absolute path, or ``None`` if no runtime can be found.
    Caches the result; pass ``force_resolve=True`` to bypass.
    """
    global _docker_executable
    if _docker_executable is not None and not force_resolve:
        return _docker_executable

    # 1. Explicit override via env var.
    override = os.getenv("TESTAI_DOCKER_BINARY")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        _docker_executable = override
        logger.info("Using TESTAI_DOCKER_BINARY override: %s", override)
        return override

    # 2. docker on PATH
    found = shutil.which("docker")
    if found:
        _docker_executable = found
        return found
    # 3. podman on PATH (drop-in compatible)
    found = shutil.which("podman")
    if found:
        _docker_executable = found
        logger.info("Using podman as container runtime: %s", found)
        return found
    # 4. Well-known macOS Docker Desktop locations
    for path in _DOCKER_SEARCH_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            _docker_executable = path
            logger.info("Found docker at non-PATH location: %s", path)
            return path
    return None


def _ensure_docker_available() -> str:
    """Best-effort check that the docker CLI is reachable before any work.

    Runs ``docker version`` (5s timeout) and raises RuntimeError with a
    clear actionable message on any failure. Returns the resolved
    docker binary path on success.

    This is a pre-flight gate, not a health check: we call it once at
    the start of every tool call so the user sees a single
    "Docker not available" message instead of a cascade of confusing
    errors from the underlying subprocess.
    """
    docker_exe = find_docker()
    if not docker_exe:
        raise RuntimeError(
            "Docker executable not found in PATH or known install locations. "
            "Install Docker (https://docs.docker.com/get-docker/) and ensure "
            "the 'docker' command is available, or set TESTAI_DOCKER_BINARY."
        )
    import subprocess
    try:
        result = subprocess.run(
            [docker_exe, "version"], capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"Docker executable at '{docker_exe}' could not be executed. "
            f"Check your Docker installation."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Docker daemon is not responding (5s timeout on `docker version`). "
            f"Ensure Docker is running and try again."
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Docker command is available but 'docker version' failed "
            f"(exit {result.returncode}, stderr={result.stderr.strip()[:200]}). "
            f"Check your Docker installation."
        )
    return docker_exe


# Security baseline applied to every container we create. The container
# itself is the security boundary (isolated from host). We drop all
# capabilities, block privilege escalation, and limit PIDs. This is
# the standard hardened-Docker baseline: same posture as the
# SandboxScope used by SandboxManager for the workspace container.
# Callers can extend (not weaken) this via the `extra_args` knob.
_BASE_SECURITY_ARGS = [
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--pids-limit", "256",
    "--tmpfs", "/tmp:rw,nosuid,size=512m",
    "--tmpfs", "/var/tmp:rw,noexec,nosuid,size=256m",
    "--tmpfs", "/run:rw,noexec,nosuid,size=64m",
]


def build_security_args(
    memory_mb: int = 0, cpu: float = 0.0, network: str = "bridge",
    user: str | None = None, env: dict[str, str] | None = None,
    mounts: list[str] | None = None, extra_args: list[str] | None = None,
) -> list[str]:
    """Build the full docker run args (security + resources + env + mounts).

    Centralised here so the SandboxManager and the agent-facing
    docker_tool.py produce equivalent security postures. The
    `extra_args` list is appended last so callers can override
    defaults (e.g. add `--cap-add SYS_PTRACE` for debugging).
    """
    args = list(_BASE_SECURITY_ARGS)
    if memory_mb and memory_mb > 0:
        args.extend(["--memory", f"{memory_mb}m"])
    if cpu and cpu > 0:
        args.extend(["--cpus", str(cpu)])
    if network and network != "bridge":
        args.extend(["--network", network])
    if user:
        args.extend(["--user", user])
    if env:
        for k in sorted(env):
            v = (env[k] or "").replace("\n", " ")
            args.extend(["-e", f"{k}={v}"])
    if mounts:
        for m in mounts:
            if isinstance(m, str) and ":" in m:
                args.extend(["-v", m])
            else:
                logger.warning("Skipping invalid docker mount: %r", m)
    if extra_args:
        for a in extra_args:
            if isinstance(a, str):
                args.append(a)
    return args


__all__ = [
    "find_docker",
    "_ensure_docker_available",
    "_BASE_SECURITY_ARGS",
    "build_security_args",
]
