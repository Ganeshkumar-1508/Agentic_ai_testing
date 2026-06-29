"""Docker execution backend: spawn-per-call inside a container.

Container lifecycle: created once in __init__, kept running, destroyed
on cleanup(). Supports auto-recovery when container is killed out-of-band,
container reuse across process restarts, configurable security modes,
resource limits (CPU, memory, disk), env forwarding, and orphan reaping.

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from .base import BaseEnvironment, _popen_bash

logger = logging.getLogger(__name__)

_DOCKER_SEARCH_PATHS = [
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
    "/Applications/Docker.app/Contents/Resources/bin/docker",
]

_BASE_SECURITY_ARGS = [
    "--cap-drop", "ALL",
    "--cap-add", "DAC_OVERRIDE",
    "--cap-add", "CHOWN",
    "--cap-add", "FOWNER",
    "--security-opt", "no-new-privileges",
    "--pids-limit", "256",
    "--tmpfs", "/tmp:rw,nosuid,size=512m",
    "--tmpfs", "/var/tmp:rw,noexec,nosuid,size=256m",
    "--tmpfs", "/run:rw,noexec,nosuid,size=64m",
    "--tmpfs", "/workspace:rw,exec,size=10g",
    "--tmpfs", "/root:rw,exec,size=1g",
]

_RUN_TMPFS_NOEXEC = "--tmpfs", "/run:rw,noexec,nosuid,size=64m"
_RUN_TMPFS_EXEC = "--tmpfs", "/run:rw,exec,nosuid,size=64m"
_PRIVDROP_CAP_ARGS = ["--cap-add", "SETUID", "--cap-add", "SETGID"]

_docker_executable: Optional[str] = None
_storage_opt_ok: Optional[bool] = None
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LABEL_VALUE_OK_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _sanitize_label_value(value: str) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    cleaned = _LABEL_VALUE_OK_RE.sub("_", value)
    return (cleaned[:63]) or "unknown"


def _normalize_env_dict(env: dict | None) -> dict[str, str]:
    if not env:
        return {}
    normalized: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not _ENV_VAR_NAME_RE.match(key.strip()):
            continue
        key = key.strip()
        if isinstance(value, (int, float, bool)):
            value = str(value)
        elif not isinstance(value, str):
            continue
        normalized[key] = value
    return normalized


def _normalize_forward_env_names(forward_env: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in forward_env or []:
        if not isinstance(item, str):
            continue
        key = item.strip()
        if not key or not _ENV_VAR_NAME_RE.match(key) or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _build_security_args(run_as_host_user: bool, run_exec: bool = False) -> list[str]:
    run_tmpfs = list(_RUN_TMPFS_EXEC if run_exec else _RUN_TMPFS_NOEXEC)
    args = list(_BASE_SECURITY_ARGS) + run_tmpfs
    if run_as_host_user:
        return args
    return args + list(_PRIVDROP_CAP_ARGS)


def _resolve_host_user_spec() -> Optional[str]:
    get_uid = getattr(os, "getuid", None)
    get_gid = getattr(os, "getgid", None)
    if get_uid is None or get_gid is None:
        return None
    try:
        return f"{get_uid()}:{get_gid()}"
    except Exception:
        return None


def _container_finished_at(docker_exe: str, container_id: str):
    try:
        result = subprocess.run(
            [docker_exe, "inspect", "--format", "{{.State.FinishedAt}}", container_id],
            capture_output=True, text=True, timeout=10, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw or raw.startswith("0001-01-01"):
        return None
    import datetime
    raw = re.sub(r"(\.\d{6})\d+", r"\1", raw)
    raw = raw.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def _storage_opt_supported(docker_exe: str) -> bool:
    global _storage_opt_ok
    if _storage_opt_ok is not None:
        return _storage_opt_ok
    try:
        result = subprocess.run(
            [docker_exe, "info", "--format", "{{.Driver}}"],
            capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        driver = result.stdout.strip().lower()
        if driver != "overlay2":
            _storage_opt_ok = False
            return False
        probe = subprocess.run(
            [docker_exe, "create", "--storage-opt", "size=1m", "hello-world"],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            container_id = probe.stdout.strip()
            if container_id:
                subprocess.run([docker_exe, "rm", container_id], capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
            _storage_opt_ok = True
        else:
            _storage_opt_ok = False
    except Exception:
        _storage_opt_ok = False
    return _storage_opt_ok


def find_docker() -> Optional[str]:
    global _docker_executable
    if _docker_executable is not None:
        return _docker_executable
    override = os.getenv("TESTAI_DOCKER_BINARY")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        _docker_executable = override
        return override
    found = shutil.which("docker")
    if found:
        _docker_executable = found
        return found
    found = shutil.which("podman")
    if found:
        _docker_executable = found
        return found
    for path in _DOCKER_SEARCH_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            _docker_executable = path
            return path
    return None


def _ensure_docker_available() -> None:
    docker_exe = find_docker()
    if not docker_exe:
        raise RuntimeError("Docker executable not found. Install Docker.")
    try:
        result = subprocess.run(
            [docker_exe, "version"], capture_output=True, text=True, timeout=5,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise RuntimeError(f"Docker daemon not responding: {e}") from e
    if result.returncode != 0:
        raise RuntimeError("Docker is installed but 'docker version' failed.")


def reap_orphan_containers(
    *, max_age_seconds: int = 600, docker_exe: str | None = None,
) -> int:
    docker = docker_exe or find_docker() or "docker"
    filters = ["--filter", "label=testai-managed=1", "--filter", "status=exited"]
    try:
        listing = subprocess.run(
            [docker, "ps", "-a", *filters, "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=15, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0
    if listing.returncode != 0:
        return 0
    candidate_ids = [ln.strip() for ln in listing.stdout.splitlines() if ln.strip()]
    if not candidate_ids:
        return 0
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    removed = 0
    for cid in candidate_ids:
        finished_at = _container_finished_at(docker, cid)
        if finished_at is None:
            continue
        age = (now - finished_at).total_seconds()
        if age < max_age_seconds:
            continue
        try:
            result = subprocess.run(
                [docker, "rm", "-f", cid],
                capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                removed += 1
                logger.info("Reaped orphan container %s", cid[:12])
        except (subprocess.TimeoutExpired, OSError):
            pass
    return removed


def _image_uses_init_entrypoint(docker_exe: str, image: str) -> bool:
    """Return True if image entrypoint is s6-overlay /init.

    s6-overlay images use their own /init as PID-1, which conflicts
    with Docker's --init (two competing inits). Detection is
    best-effort — on failure we return False and keep defaults.
    """
    try:
        result = subprocess.run(
            [docker_exe, "image", "inspect", image,
             "--format", "{{json .Config.Entrypoint}}"],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    if result.returncode != 0:
        return False
    raw = (result.stdout or "").strip()
    if not raw or raw == "null":
        return False
    try:
        entrypoint = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if isinstance(entrypoint, str):
        entrypoint = [entrypoint]
    if not isinstance(entrypoint, list) or not entrypoint:
        return False
    first = str(entrypoint[0]).strip()
    return first in ("/init", "/package/admin/s6-overlay/command/init")


class DockerEnvironment(BaseEnvironment):
    _NO_CONTAINER_PATTERNS = (
        "No such container", "is not running", "no such container",
    )

    def __init__(
        self,
        session_id: str,
        cwd: str = "/root",
        timeout: int = 120,
        image: str = "nikolaik/python-nodejs:python3.11-nodejs20",
        cpu: float = 0,
        memory_mb: int = 0,
        disk_mb: int = 0,
        network: bool = True,
        volumes: list[str] | None = None,
        env: dict | None = None,
        forward_env: list[str] | None = None,
        run_as_host_user: bool = False,
        persist_across_processes: bool = True,
        extra_args: list[str] | None = None,
    ):
        super().__init__(session_id=session_id, cwd=cwd, timeout=timeout, env=env or {})
        _ensure_docker_available()
        self._docker_exe = find_docker() or "docker"
        self._image = image
        self._persist_across_processes = persist_across_processes
        self._forward_env = _normalize_forward_env_names(forward_env)
        self._env = _normalize_env_dict(env)
        self._container_id: Optional[str] = None
        self._labels: dict[str, str] = {}
        self._container_name = f"testai-{uuid.uuid4().hex[:8]}"
        self._image_uses_s6_init = _image_uses_init_entrypoint(self._docker_exe, image)

        resource_args = []
        if cpu > 0:
            resource_args.extend(["--cpus", str(cpu)])
        if memory_mb > 0:
            resource_args.extend(["--memory", f"{memory_mb}m"])
        if disk_mb > 0 and sys.platform != "darwin":
            if _storage_opt_supported(self._docker_exe):
                resource_args.extend(["--storage-opt", f"size={disk_mb}m"])

        volume_args = []
        for vol in (volumes or []):
            if isinstance(vol, str) and ":" in vol:
                volume_args.extend(["-v", vol])

        if not network:
            resource_args.append("--network=none")

        run_as_host = run_as_host_user and _resolve_host_user_spec() is not None
        user_args = []
        if run_as_host:
            user_spec = _resolve_host_user_spec()
            if user_spec is not None:
                user_args = ["--user", user_spec]

        env_args = []
        for key in sorted(self._env):
            env_args.extend(["-e", f"{key}={self._env[key]}"])

        image_uses_s6_init = _image_uses_init_entrypoint(self._docker_exe, image)
        self._image_uses_s6_init = image_uses_s6_init
        security_args = _build_security_args(
            run_as_host, run_exec=image_uses_s6_init,
        )
        init_args = [] if image_uses_s6_init else ["--init"]
        validated_extra = [a for a in (extra_args or []) if isinstance(a, str)]

        self._all_run_args = (
            init_args + security_args + user_args + resource_args + volume_args + env_args + validated_extra
        )

        # Build init-time env forwarding args (used only by init_session)
        self._init_env_args = self._build_init_env_args()

        label_args = [
            "--label", "testai-managed=1",
            "--label", f"testai-session-id={_sanitize_label_value(session_id)[:63]}",
        ]
        self._labels = {"testai-managed": "1", "testai-session-id": _sanitize_label_value(session_id)[:63]}

        # Cross-process container reuse
        reused = False
        if persist_across_processes:
            existing = self._find_reusable_container()
            if existing is not None:
                container_id, state = existing
                self._container_id = container_id
                if state != "running":
                    try:
                        subprocess.run(
                            [self._docker_exe, "start", container_id],
                            capture_output=True, text=True, timeout=30, check=True,
                            stdin=subprocess.DEVNULL,
                        )
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        self._container_id = None
                if self._container_id:
                    logger.info("Reusing container %s (prior state=%s)", container_id[:12], state)
                    reused = True

        if not reused:
            run_cmd = [
                self._docker_exe, "run", "-d",
                "--name", self._container_name,
                *label_args, "-w", cwd, *self._all_run_args,
                image, "sleep", "infinity",
            ]
            try:
                result = subprocess.run(
                    run_cmd, capture_output=True, text=True, timeout=120, check=True,
                    stdin=subprocess.DEVNULL,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                raise RuntimeError(f"Failed to start Docker container: {e}") from e
            self._container_id = result.stdout.strip()
            logger.info("Started container %s (%s)", self._container_name, self._container_id[:12])

        self.init_session()

    def _build_init_env_args(self) -> list[str]:
        """Build -e KEY=VALUE args for injecting host env vars into init_session.

        These are used once during init_session so export -p captures them
        into the snapshot. Subsequent commands get env vars from the snapshot.
        """
        exec_env: dict[str, str] = dict(self._env)
        forward_keys = set(self._forward_env)
        for key in sorted(forward_keys):
            value = os.environ.get(key)
            if value:
                exec_env[key] = value
        args = []
        for key in sorted(exec_env):
            args.extend(["-e", f"{key}={exec_env[key]}"])
        return args

    def _run_bash(self, cmd_string, *, login=False, timeout=120, stdin_data=None):
        assert self._container_id, "Container not started"
        cmd = [self._docker_exe, "exec"]
        if stdin_data is not None:
            cmd.append("-i")
        # Only inject -e env args during init_session (login=True).
        # Subsequent commands get env vars from the snapshot.
        if login:
            cmd.extend(self._init_env_args)
        if login:
            cmd.extend([self._container_id, "bash", "-l", "-c", cmd_string])
        else:
            cmd.extend([self._container_id, "bash", "-c", cmd_string])
        return _popen_bash(cmd, stdin_data)

    def _is_container_gone(self, output: str) -> bool:
        return any(p in output for p in self._NO_CONTAINER_PATTERNS)

    def _find_reusable_container(self) -> Optional[tuple[str, str]]:
        try:
            result = subprocess.run(
                [
                    self._docker_exe, "ps", "-a",
                    "--filter", "label=testai-managed=1",
                    "--filter", f"label=testai-session-id={_sanitize_label_value(self.session_id)[:63]}",
                    "--format", "{{.ID}}\t{{.State}}",
                ],
                capture_output=True, text=True, timeout=10, check=False,
                stdin=subprocess.DEVNULL,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if result.returncode != 0:
            return None
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        if not lines:
            return None
        running = None
        first = None
        for ln in lines:
            parts = ln.split("\t", 1)
            if len(parts) != 2:
                continue
            cid, state = parts[0], parts[1].lower()
            if first is None:
                first = (cid, state)
            if state == "running" and running is None:
                running = (cid, state)
        return running or first

    def _recreate_container(self) -> bool:
        old_id = (self._container_id or "")[:12]
        logger.warning("Container %s gone — attempting recovery", old_id)
        self._container_id = None
        existing = self._find_reusable_container()
        if existing is not None:
            cid, state = existing
            if state == "running":
                self._container_id = cid
                logger.info("Recovery: reusing running container %s", cid[:12])
            else:
                try:
                    subprocess.run(
                        [self._docker_exe, "start", cid],
                        capture_output=True, text=True, timeout=30, check=True,
                        stdin=subprocess.DEVNULL,
                    )
                    self._container_id = cid
                    logger.info("Recovery: restarted container %s", cid[:12])
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass
        if not self._container_id:
            if not self._image:
                logger.error("Recovery: no saved image name")
                return False
            try:
                new_name = f"testai-{uuid.uuid4().hex[:8]}"
                label_args = []
                for k, v in self._labels.items():
                    label_args.extend(["--label", f"{k}={v}"])
                run_cmd = [
                    self._docker_exe, "run", "-d",
                    "--init", "--name", new_name,
                    *label_args, "-w", self.cwd,
                    *self._all_run_args,
                    self._image, "sleep", "infinity",
                ]
                result = subprocess.run(
                    run_cmd, capture_output=True, text=True, timeout=120, check=True,
                    stdin=subprocess.DEVNULL,
                )
                self._container_id = result.stdout.strip()
                self._container_name = new_name
                logger.info("Recovery: created fresh container %s (%s)", new_name, self._container_id[:12])
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
                logger.error("Recovery: failed: %s", e)
                return False
        try:
            self._snapshot_ready = False
            self.init_session()
        except Exception as e:
            logger.error("Recovery: init_session failed: %s", e)
            return False
        return True

    def execute(self, command, cwd="", *, timeout=None, stdin_data=None):
        result = super().execute(command, cwd, timeout=timeout, stdin_data=stdin_data)
        if (
            not result.success
            and self._is_container_gone(result.output)
            and self._persist_across_processes
        ):
            if self._recreate_container():
                result = super().execute(command, cwd, timeout=timeout, stdin_data=stdin_data)
        return result

    def cleanup(self, *, force_remove: bool = False):
        container_id = self._container_id
        if not container_id:
            return

        if force_remove:
            should_stop, should_remove = True, True
        elif self._persist_across_processes:
            self._container_id = None
            return
        else:
            should_stop, should_remove = True, True

        docker_exe = self._docker_exe
        log_id = container_id[:12]

        def _do_cleanup():
            if should_stop:
                try:
                    subprocess.run(
                        [docker_exe, "stop", "-t", "10", container_id],
                        capture_output=True, timeout=30, stdin=subprocess.DEVNULL,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    pass
            if should_remove:
                try:
                    subprocess.run(
                        [docker_exe, "rm", "-f", container_id],
                        capture_output=True, timeout=30, stdin=subprocess.DEVNULL,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    pass

        t = threading.Thread(target=_do_cleanup, daemon=True, name=f"testai-cleanup-{log_id}")
        t.start()
        self._cleanup_thread = t
        self._container_id = None

    def wait_for_cleanup(self, timeout: float = 30.0) -> bool:
        thread = getattr(self, "_cleanup_thread", None)
        if thread is None or not thread.is_alive():
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()


import threading
