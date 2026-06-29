"""SSH remote execution backend with ControlMaster connection persistence.

Every execute() spawns a fresh ``ssh ... bash -c`` process over a
persistent ControlMaster connection. FileSyncManager keeps the remote
~/.testai directory tree in sync.

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import BaseEnvironment, ProcessHandle, _pipe_stdin
from .file_sync import (
    FileSyncManager,
    iter_sync_files,
    quoted_mkdir_command,
    quoted_rm_command,
    unique_parent_dirs,
)

logger = logging.getLogger(__name__)


def _ensure_ssh_available() -> None:
    if not shutil.which("ssh"):
        raise RuntimeError("SSH is not installed. Install OpenSSH client.")


class SSHEnvironment(BaseEnvironment):
    def __init__(
        self,
        session_id: str,
        cwd: str = "~",
        timeout: int = 120,
        host: str = "",
        user: str = "",
        port: int = 22,
        key_path: str = "",
        env: dict | None = None,
        sync_base_host: str = "",
    ):
        if cwd == "~":
            cwd = ""
        super().__init__(session_id=session_id, cwd=cwd, timeout=timeout, env=env or {})
        self.host = host
        self.user = user
        self.port = port
        self.key_path = key_path
        self._sync_base_host = sync_base_host

        _ensure_ssh_available()

        self.control_dir = Path(tempfile.gettempdir()) / "testai-ssh"
        self.control_dir.mkdir(parents=True, exist_ok=True)
        _socket_id = hashlib.sha256(f"{user}@{host}:{port}".encode()).hexdigest()[:16]
        self.control_socket = self.control_dir / f"{_socket_id}.sock"

        self._establish_connection()
        self._remote_home = self._detect_remote_home()

        self._ensure_remote_dirs()
        self._sync_manager = FileSyncManager(
            get_files_fn=self._get_sync_files,
            upload_fn=self._scp_upload,
            delete_fn=self._ssh_delete,
            bulk_upload_fn=self._ssh_bulk_upload,
            bulk_download_fn=self._ssh_bulk_download,
        )
        self._sync_manager.sync(force=True)

    def _build_ssh_command(self, extra_args: list | None = None) -> list[str]:
        cmd = ["ssh"]
        cmd.extend(["-o", f"ControlPath={self.control_socket}"])
        cmd.extend(["-o", "ControlMaster=auto"])
        cmd.extend(["-o", "ControlPersist=300"])
        cmd.extend(["-o", "BatchMode=yes"])
        cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])
        cmd.extend(["-o", "ConnectTimeout=10"])
        if self.port != 22:
            cmd.extend(["-p", str(self.port)])
        if self.key_path:
            cmd.extend(["-i", self.key_path])
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(f"{self.user}@{self.host}")
        return cmd

    def _establish_connection(self) -> None:
        cmd = self._build_ssh_command()
        cmd.append("echo 'SSH connection established'")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(f"SSH connection failed: {error_msg}")
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"SSH connection to {self.user}@{self.host} timed out") from e

    def _detect_remote_home(self) -> str:
        try:
            cmd = self._build_ssh_command()
            cmd.append("echo $HOME")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                stdin=subprocess.DEVNULL,
            )
            home = result.stdout.strip()
            if home and result.returncode == 0:
                return home
        except Exception:
            pass
        if self.user == "root":
            return "/root"
        return f"/home/{self.user}"

    def _get_sync_files(self) -> list[tuple[str, str]]:
        files = iter_sync_files(
            sync_base_host=self._sync_base_host,
            sync_base_remote=f"{self._remote_home}/.testai",
        )
        try:
            from .credential_files import iter_skills_files
            for entry in iter_skills_files(container_base=f"{self._remote_home}/.testai"):
                files.append((entry["host_path"], entry["container_path"]))
        except Exception:
            pass
        return files

    def _ensure_remote_dirs(self) -> None:
        base = f"{self._remote_home}/.testai"
        dirs = [base, f"{base}/skills", f"{base}/credentials", f"{base}/cache", f"{base}/mcp"]
        cmd = self._build_ssh_command()
        cmd.append(quoted_mkdir_command(dirs))
        subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )

    def _scp_upload(self, host_path: str, remote_path: str) -> None:
        parent = str(Path(remote_path).parent)
        mkdir_cmd = self._build_ssh_command()
        mkdir_cmd.append(f"mkdir -p {shlex.quote(parent)}")
        subprocess.run(
            mkdir_cmd, capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        scp_cmd = ["scp", "-o", f"ControlPath={self.control_socket}"]
        if self.port != 22:
            scp_cmd.extend(["-P", str(self.port)])
        if self.key_path:
            scp_cmd.extend(["-i", self.key_path])
        scp_cmd.extend([host_path, f"{self.user}@{self.host}:{remote_path}"])
        result = subprocess.run(
            scp_cmd, capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise RuntimeError(f"scp failed: {result.stderr.strip()}")

    def _ssh_bulk_upload(self, files: list[tuple[str, str]]) -> None:
        if not files:
            return

        base = f"{self._remote_home}/.testai"
        parents = unique_parent_dirs(files)
        if parents:
            cmd = self._build_ssh_command()
            cmd.append(quoted_mkdir_command(parents))
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                raise RuntimeError(f"remote mkdir failed: {result.stderr.strip()}")

        with tempfile.TemporaryDirectory(prefix="testai-ssh-bulk-") as staging:
            for host_path, remote_path in files:
                try:
                    rel_remote = os.path.relpath(remote_path, base)
                except ValueError as exc:
                    raise RuntimeError(f"remote path {remote_path!r} not under {base!r}") from exc
                if rel_remote == "." or rel_remote.startswith("../"):
                    raise RuntimeError(f"remote path {remote_path!r} escapes sync base")
                staged = os.path.join(staging, rel_remote)
                os.makedirs(os.path.dirname(staged), exist_ok=True)
                shutil.copy2(host_path, staged)

            tar_cmd = ["tar", "-chf", "-", "-C", staging, "."]
            ssh_cmd = self._build_ssh_command()
            ssh_cmd.append(f"tar xf - --no-overwrite-dir -C {shlex.quote(base)}")

            tar_proc = subprocess.Popen(
                tar_cmd, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                ssh_proc = subprocess.Popen(
                    ssh_cmd, stdin=tar_proc.stdout,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
            except Exception:
                tar_proc.kill()
                tar_proc.wait()
                raise

            tar_proc.stdout.close()
            try:
                _, ssh_stderr = ssh_proc.communicate(timeout=120)
                if tar_proc.poll() is None:
                    tar_proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                tar_proc.kill()
                ssh_proc.kill()
                tar_proc.wait()
                ssh_proc.wait()
                raise RuntimeError("SSH bulk upload timed out")

            if ssh_proc.returncode != 0:
                raise RuntimeError(
                    f"tar extract over SSH failed (rc={ssh_proc.returncode}): "
                    f"{ssh_stderr.decode(errors='replace').strip()}"
                )

        logger.debug("SSH: bulk-uploaded %d file(s) via tar pipe", len(files))

    def _ssh_bulk_download(self, dest: Path) -> None:
        rel_base = f"{self._remote_home}/.testai".lstrip("/")
        ssh_cmd = self._build_ssh_command()
        ssh_cmd.append(f"tar cf - -C / {shlex.quote(rel_base)}")
        with open(dest, "wb") as f:
            result = subprocess.run(
                ssh_cmd, stdin=subprocess.DEVNULL,
                stdout=f, stderr=subprocess.PIPE,
                timeout=120,
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"SSH bulk download failed: {result.stderr.decode(errors='replace').strip()}"
            )

    def _ssh_delete(self, remote_paths: list[str]) -> None:
        cmd = self._build_ssh_command()
        cmd.append(quoted_rm_command(remote_paths))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise RuntimeError(f"remote rm failed: {result.stderr.strip()}")

    def _before_execute(self) -> None:
        self._sync_manager.sync()

    def _run_bash(
        self,
        cmd_string: str,
        *,
        login: bool = False,
        timeout: int = 120,
        stdin_data: str | None = None,
    ) -> ProcessHandle:
        cmd = self._build_ssh_command()
        if login:
            cmd.extend(["bash", "-l", "-c", shlex.quote(cmd_string)])
        else:
            cmd.extend(["bash", "-c", shlex.quote(cmd_string)])

        proc = subprocess.Popen(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        )
        if stdin_data is not None:
            _pipe_stdin(proc, stdin_data)
        return proc

    def cleanup(self) -> None:
        if self._sync_manager:
            try:
                self._sync_manager.sync_back()
            except Exception:
                pass
        if self.control_socket.exists():
            try:
                cmd = [
                    "ssh", "-o", f"ControlPath={self.control_socket}",
                    "-O", "exit", f"{self.user}@{self.host}",
                ]
                subprocess.run(
                    cmd, capture_output=True, timeout=5,
                    stdin=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                self.control_socket.unlink()
            except OSError:
                pass
