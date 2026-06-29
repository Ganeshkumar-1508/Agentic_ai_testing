"""Docker executor tool — agent-facing surface for running in containers.

The orchestrator's coordinator uses this when it needs to:
  - run a command inside a specific image (e.g. `golang:1.22` for
    Go tests) when the default workspace image is missing a runtime
  - run a command with different network, memory, CPU, user, or env
    configuration than the default workspace
  - mount additional host directories into the container
  - inspect the list of locally-available images before pulling

The tool wraps two execution paths:
  1. **Default workspace** — uses `SandboxManager.get_or_create(session_id)`
     so commands run in the per-session workspace container the
     manager already created. No extra security args needed; the
     manager handles that.
  2. **Custom image (sidecar)** — does a one-off `docker run --rm`
     with the same security baseline as the workspace container
     (cap-drop ALL, no-new-privileges, pids-limit, tmpfs). The
     container is tagged with `testai-agent=1` so a future
     orphan-reaper can clean up if TestAI crashes.

Configuration surface: image, network, memory_mb, cpu, user, env,
mounts, extra_args. The `extra_args` parameter is the explicit
escape hatch for knobs the tool doesn't model directly (e.g.
`--cap-add SYS_PTRACE`).

If the sandbox manager is not initialised (e.g. local dev where
Docker isn't available), the tool returns a clear "not available"
result instead of crashing. The agent can fall back to `bash`.

Module-level deps are injected at app startup via
`set_backend_factory`.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
import uuid
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.docker_executor import (
    _BASE_SECURITY_ARGS, _ensure_docker_available, build_security_args,
    find_docker,
)
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


_deps_ref: dict[str, Any] = {}


def set_backend_factory(factory: Any) -> None:
    _deps_ref["backend_factory"] = factory


def _backend_factory() -> Any:
    return _deps_ref.get("backend_factory")


def _session_id(kwargs: dict[str, Any]) -> str:
    return kwargs.get("session_id") or kwargs.get("run_id") or "default"


def _exec_in_container(
    docker: str, container_id: str, command: str, timeout: int,
) -> subprocess.CompletedProcess:
    """Run a command in an already-running container via `docker exec`."""
    return subprocess.run(
        [docker, "exec", container_id, "sh", "-c", command],
        capture_output=True, text=True, timeout=timeout,
    )


def _run_one_off_sidecar(
    docker: str, image: str, command: str, timeout: int,
    memory_mb: int, cpu: float, network: str, user: str | None,
    env: dict[str, str] | None, mounts: list[str] | None,
    extra_args: list[str] | None, session_id: str,
) -> tuple[int, str, str, str]:
    """Spin up a one-off container, run command, return result.

    Returns (container_id, stdout, stderr, exit_code_note). The
    container is removed after the command exits; it does not
    persist (use SandboxManager for persistent containers).
    """
    # 1. Pull image if not available locally (best-effort).
    if not _image_available(docker, image):
        subprocess.run(
            [docker, "pull", image], capture_output=True, text=True, timeout=120,
        )
    # 2. Build security + config args.
    security = build_security_args(
        memory_mb=memory_mb, cpu=cpu, network=network,
        user=user, env=env, mounts=mounts, extra_args=extra_args,
    )
    # 3. Spin up. We use `docker run --rm` so the container is
    # removed when the command exits — appropriate for one-off
    # sidecar commands. The workspace container (managed by
    # SandboxManager) is the persistent one.
    container_name = f"testai-exec-{session_id[:8]}-{uuid.uuid4().hex[:6]}"
    label_args = [
        "--label", "testai-agent=1",
        "--label", f"testai-session-id={session_id[:63]}",
        "--label", f"testai-exec-time={int(time.time())}",
    ]
    run_cmd = [
        docker, "run", "--rm", "--name", container_name,
        *label_args, *security, image, "sh", "-c", command,
    ]
    proc = subprocess.run(
        run_cmd, capture_output=True, text=True, timeout=timeout,
    )
    return container_name, proc.stdout, proc.stderr, str(proc.returncode)


def _image_available(docker: str, image: str) -> bool:
    """Check if a docker image is present locally (no pull)."""
    try:
        proc = subprocess.run(
            [docker, "image", "inspect", image],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return proc.returncode == 0


class DockerExecTool(BaseTool):
    name = "docker_executor"
    default_level = "ask"
    description = (
        "Run a shell command inside a Docker container. By default "
        "uses the per-session workspace container (Python 3.11 + "
        "Node 20). Pass `image` to run in a different image (e.g. "
        "`golang:1.22` for Go tests). Configurable knobs: `network` "
        "(bridge|none|host), `memory_mb`, `cpu`, `user`, `env` (dict), "
        "`mounts` (list of host:container), `extra_args` (list of "
        "extra docker run flags). Pre-flight: verifies `docker version` "
        "succeeds before any work. Returns a clear error if Docker is "
        "unavailable — the agent should fall back to `bash`."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run inside the container",
                    },
                    "image": {
                        "type": "string",
                        "description": (
                            "Image override. If set, runs in a one-off "
                            "container (--rm) with the requested image. "
                            "Defaults to the per-session workspace container."
                        ),
                    },
                    "network": {
                        "type": "string", "enum": ["bridge", "none", "host"],
                        "default": "bridge",
                        "description": "Docker network mode (sidecar only)",
                    },
                    "memory_mb": {
                        "type": "integer", "default": 0, "minimum": 0, "maximum": 65536,
                        "description": "Memory limit in MB; 0 = unlimited (sidecar only)",
                    },
                    "cpu": {
                        "type": "number", "default": 0.0, "minimum": 0.0, "maximum": 64.0,
                        "description": "CPU limit (cores); 0 = unlimited (sidecar only)",
                    },
                    "user": {
                        "type": "string",
                        "description": "Run as this user, e.g. '1000:1000' (sidecar only)",
                    },
                    "env": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Environment variables to set (sidecar only)",
                    },
                    "mounts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Bind mounts in 'host:container[:ro]' form (sidecar only)",
                    },
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra flags appended to `docker run` (sidecar only)",
                    },
                    "timeout": {
                        "type": "integer", "default": 60, "minimum": 1, "maximum": 3600,
                    },
                },
                "required": ["command"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        # Pre-flight: ensure docker is reachable. This is the single
        # place we surface "Docker is not installed / daemon down".
        try:
            docker = _ensure_docker_available()
        except RuntimeError as exc:
            return ToolResult(
                success=False,
                output=(
                    f"{exc}\n"
                    f"Tip: set TESTAI_DOCKER_BINARY to a non-PATH docker "
                    f"location, or fall back to the `bash` tool which "
                    f"runs locally."
                ),
                error="docker_unavailable",
            )

        command = kwargs.get("command")
        if not command or not isinstance(command, str):
            return ToolResult(success=False, output="`command` is required", error="missing_arg")
        try:
            timeout = max(1, min(3600, int(kwargs.get("timeout", 60) or 60)))
        except (TypeError, ValueError):
            timeout = 60
        session_id = _session_id(kwargs)
        image = kwargs.get("image")

        try:
            if image:
                # Sidecar path: one-off container with the configured
                # security baseline. We run the loop in an executor
                # so we don't block the event loop on the subprocess.
                loop = asyncio.get_event_loop()
                _name, stdout, stderr, exit_code_str = await loop.run_in_executor(
                    None, lambda: _run_one_off_sidecar(
                        docker, image, command, timeout,
                        memory_mb=int(kwargs.get("memory_mb", 0) or 0),
                        cpu=float(kwargs.get("cpu", 0.0) or 0.0),
                        network=kwargs.get("network", "bridge") or "bridge",
                        user=kwargs.get("user") or None,
                        env=kwargs.get("env") or None,
                        mounts=kwargs.get("mounts") or None,
                        extra_args=kwargs.get("extra_args") or None,
                        session_id=session_id,
                    ),
                )
                ok = exit_code_str == "0"
                body: list[str] = []
                if stdout:
                    body.append(f"### stdout\n```\n{stdout.rstrip()}\n```")
                if stderr:
                    body.append(f"### stderr\n```\n{stderr.rstrip()}\n```")
                body.append(f"**exit code: {exit_code_str}** (one-off sidecar; container removed)")
                return ToolResult(
                    success=ok,
                    output="\n\n".join(body),
                    data={
                        "stdout": stdout, "stderr": stderr,
                        "exit_code": int(exit_code_str) if exit_code_str.lstrip("-").isdigit() else -1,
                        "image": image, "sidecar": True,
                    },
                )
            # Default workspace path: use the per-session container.
            factory = _backend_factory()
            if factory is not None:
                backend = factory(session_id, backend_type="docker")
                proc = await backend.run(command, timeout=timeout)
            else:
                return ToolResult(
                    success=False,
                    output=(
                        "Backend not initialised. Ensure a factory is "
                        "configured, or fall back to the `bash` tool."
                    ),
                    error="not_initialised",
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output=f"Command timed out after {timeout}s. Increase `timeout` or break the work into smaller steps.",
                error="timeout",
            )
        except Exception as exc:
            logger.warning("docker_executor run failed: %s", exc)
            return ToolResult(
                success=False, output=f"Container exec failed: {exc}",
                error="docker_error",
            )
        ok = proc.returncode == 0
        body = []
        if proc.stdout:
            body.append(f"### stdout\n```\n{proc.stdout.rstrip()}\n```")
        if proc.stderr:
            body.append(f"### stderr\n```\n{proc.stderr.rstrip()}\n```")
        body.append(f"**exit code: {proc.returncode}**")
        return ToolResult(
            success=ok,
            output="\n\n".join(body),
            data={
                "stdout": proc.stdout, "stderr": proc.stderr,
                "exit_code": proc.returncode, "image": image or env.role,
            },
        )


class DockerImageListTool(BaseTool):
    name = "docker_image_list"
    default_level = "ask"
    description = (
        "List Docker images available in the local Docker daemon. "
        "Used by the coordinator to discover what's pre-pulled. "
        "Returns image tags and sizes."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={"type": "object", "properties": {}},
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            docker = _ensure_docker_available()
        except RuntimeError as exc:
            return ToolResult(success=False, output=str(exc), error="docker_unavailable")
        loop = asyncio.get_event_loop()
        try:
            proc = await loop.run_in_executor(
                None, lambda: subprocess.run(
                    [docker, "images", "--format", "{{.Repository}}:{{.Tag}} {{.Size}}"],
                    capture_output=True, text=True, timeout=30,
                ),
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"List failed: {exc}", error="docker_error")
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            return ToolResult(success=True, output="No images found (or `docker` not in PATH).")
        md = ["| Image | Size |", "|---|---|"]
        for ln in lines:
            parts = ln.rsplit(" ", 1)
            md.append(f"| {parts[0]} | {parts[1] if len(parts) > 1 else '?'} |")
        return ToolResult(success=True, output="\n".join(md), data={"lines": lines})


registry.register(DockerExecTool(), toolset="read")
registry.register(DockerImageListTool(), toolset="read")
