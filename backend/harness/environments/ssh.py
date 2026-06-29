"""SSH remote execution environment — adapted from Hermes ssh.py.

Uses SSH ControlMaster for connection persistence. Spawn-per-call model.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shlex
import shutil
import tempfile
from pathlib import Path

from harness.environments.base import BaseEnvironment

logger = logging.getLogger(__name__)


def _ensure_ssh_available() -> None:
    if not shutil.which("ssh"):
        raise RuntimeError("SSH not installed. Install OpenSSH client.")
    if not shutil.which("scp"):
        raise RuntimeError("SCP not installed. Install OpenSSH client.")


class SSHEnvironment(BaseEnvironment):
    """Run commands on a remote machine over SSH with ControlMaster persistence."""

    def __init__(self, host: str, user: str, cwd: str = "~",
                 timeout: int = 120, port: int = 22, key_path: str = ""):
        super().__init__(cwd=cwd, timeout=timeout)
        self.host = host
        self.user = user
        self.port = port
        self.key_path = key_path

        self.control_dir = Path(tempfile.gettempdir()) / "testai-ssh"
        self.control_dir.mkdir(parents=True, exist_ok=True)
        host_hash = hashlib.sha256(f"{user}@{host}:{port}".encode()).hexdigest()[:16]
        self.control_socket = str(self.control_dir / f"ssh-{host_hash}")

    def _build_ssh_args(self, extra_args: list[str] | None = None) -> list[str]:
        args = [
            "ssh",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={self.control_socket}",
            "-o", "ControlPersist=30",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            "-p", str(self.port),
        ]
        if self.key_path:
            args += ["-i", self.key_path]
        if extra_args:
            args += extra_args
        args.append(f"{self.user}@{self.host}")
        return args

    async def execute(self, command: str, timeout: int | None = None, **kwargs) -> str:
        import asyncio, subprocess as sp
        timeout = timeout or self._timeout
        ssh_args = self._build_ssh_args()
        shell = shlex.quote(f"cd {shlex.quote(self._cwd)} && {command}")
        cmd = ssh_args + [shell]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=sp.PIPE,
                stderr=sp.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = (stdout or b"").decode("utf-8", errors="replace")
            if stderr:
                output += "\n" + stderr.decode("utf-8", errors="replace")
            return output
        except asyncio.TimeoutError:
            if proc:
                proc.kill()
            return f"[timeout after {timeout}s]"
        except Exception as e:
            return f"[error: {e}]"

    async def copy_to(self, local_path: str, remote_path: str) -> str:
        """Copy a file to the remote host."""
        import asyncio, subprocess as sp
        scp_args = ["scp", "-P", str(self.port)]
        if self.key_path:
            scp_args += ["-i", self.key_path]
        scp_args += ["-o", "StrictHostKeyChecking=accept-new"]
        scp_args += [local_path, f"{self.user}@{self.host}:{remote_path}"]
        try:
            proc = await asyncio.create_subprocess_exec(*scp_args, stdout=sp.PIPE, stderr=sp.PIPE)
            await proc.communicate()
            return f"Copied {local_path} to {remote_path}"
        except Exception as e:
            return f"[error: {e}]"

    async def copy_from(self, remote_path: str, local_path: str) -> str:
        """Copy a file from the remote host."""
        import asyncio, subprocess as sp
        scp_args = ["scp", "-P", str(self.port)]
        if self.key_path:
            scp_args += ["-i", self.key_path]
        scp_args += ["-o", "StrictHostKeyChecking=accept-new"]
        scp_args += [f"{self.user}@{self.host}:{remote_path}", local_path]
        try:
            proc = await asyncio.create_subprocess_exec(*scp_args, stdout=sp.PIPE, stderr=sp.PIPE)
            await proc.communicate()
            return f"Copied {remote_path} to {local_path}"
        except Exception as e:
            return f"[error: {e}]"
