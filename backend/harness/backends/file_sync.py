"""Shared file sync manager for remote execution backends.

Tracks local file changes via mtime+size, detects deletions, and
syncs to remote environments. Used by SSH and future cloud backends.
Docker uses bind mounts and doesn't need this.

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import hashlib
import logging
import os
import posixpath
import shlex
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_sleep = time.sleep

_SYNC_INTERVAL_SECONDS = 5.0
_SYNC_BACK_MAX_RETRIES = 3
_SYNC_BACK_BACKOFF = (2, 4, 8)
_SYNC_BACK_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

UploadFn = Callable[[str, str], None]
BulkUploadFn = Callable[[list[tuple[str, str]]], None]
BulkDownloadFn = Callable[[Path], None]
DeleteFn = Callable[[list[str]], None]
GetFilesFn = Callable[[], list[tuple[str, str]]]


def _file_mtime_key(host_path: str) -> tuple[float, int] | None:
    try:
        st = Path(host_path).stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def quoted_rm_command(remote_paths: list[str]) -> str:
    return "rm -f " + " ".join(shlex.quote(p) for p in remote_paths)


def quoted_mkdir_command(dirs: list[str]) -> str:
    return "mkdir -p " + " ".join(shlex.quote(d) for d in dirs)


def unique_parent_dirs(files: list[tuple[str, str]]) -> list[str]:
    return sorted({posixpath.dirname(remote) for _, remote in files})


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_sync_files(
    sync_base_host: str = "",
    sync_base_remote: str = "/root/.testai",
) -> list[tuple[str, str]]:
    """Enumerate files to sync to a remote environment.

    Combines registered credential files + files under *sync_base_host*.
    Returns ``(host_path, remote_path)`` pairs.
    """
    files: list[tuple[str, str]] = []
    try:
        from .credential_files import get_credential_file_mounts, iter_skills_files, iter_cache_files
        for entry in get_credential_file_mounts():
            remote = entry["container_path"].replace("/root/.testai", sync_base_remote, 1)
            files.append((entry["host_path"], remote))
    except Exception:
        pass
    if sync_base_host and os.path.isdir(sync_base_host):
        for dirpath, _dirnames, filenames in os.walk(sync_base_host):
            for fname in filenames:
                host_path = os.path.join(dirpath, fname)
                rel = os.path.relpath(host_path, sync_base_host)
                remote_path = posixpath.join(sync_base_remote, rel.replace("\\", "/"))
                files.append((host_path, remote_path))
    return files


class FileSyncManager:
    def __init__(
        self,
        get_files_fn: GetFilesFn,
        upload_fn: UploadFn,
        delete_fn: DeleteFn,
        sync_interval: float = _SYNC_INTERVAL_SECONDS,
        bulk_upload_fn: BulkUploadFn | None = None,
        bulk_download_fn: BulkDownloadFn | None = None,
    ):
        self._get_files_fn = get_files_fn
        self._upload_fn = upload_fn
        self._bulk_upload_fn = bulk_upload_fn
        self._bulk_download_fn = bulk_download_fn
        self._delete_fn = delete_fn
        self._synced_files: dict[str, tuple[float, int]] = {}
        self._pushed_hashes: dict[str, str] = {}
        self._last_sync_time: float = 0.0
        self._sync_interval = sync_interval

    def sync(self, *, force: bool = False) -> None:
        if not force:
            now = time.monotonic()
            if now - self._last_sync_time < self._sync_interval:
                return

        current_files = self._get_files_fn()
        current_remote_paths = {remote for _, remote in current_files}

        to_upload: list[tuple[str, str]] = []
        new_files = dict(self._synced_files)
        for host_path, remote_path in current_files:
            file_key = _file_mtime_key(host_path)
            if file_key is None:
                continue
            if self._synced_files.get(remote_path) == file_key:
                continue
            to_upload.append((host_path, remote_path))
            new_files[remote_path] = file_key

        to_delete = [p for p in self._synced_files if p not in current_remote_paths]

        if not to_upload and not to_delete:
            self._last_sync_time = time.monotonic()
            return

        prev_files = dict(self._synced_files)
        prev_hashes = dict(self._pushed_hashes)

        try:
            if to_upload and self._bulk_upload_fn is not None:
                self._bulk_upload_fn(to_upload)
                logger.debug("file_sync: bulk-uploaded %d file(s)", len(to_upload))
            else:
                for host_path, remote_path in to_upload:
                    self._upload_fn(host_path, remote_path)

            if to_delete:
                self._delete_fn(to_delete)

            for host_path, remote_path in to_upload:
                self._pushed_hashes[remote_path] = _sha256_file(host_path)
            for p in to_delete:
                new_files.pop(p, None)
                self._pushed_hashes.pop(p, None)

            self._synced_files = new_files
            self._last_sync_time = time.monotonic()

        except Exception as exc:
            self._synced_files = prev_files
            self._pushed_hashes = prev_hashes
            self._last_sync_time = time.monotonic()
            logger.warning("file_sync: sync failed, rolled back: %s", exc)

    def sync_back(self, hermes_home: Path | None = None) -> None:
        """Pull remote changes back to the host filesystem."""
        if self._bulk_download_fn is None:
            return
        if not self._pushed_hashes and not self._synced_files:
            logger.debug("sync_back: no prior push state — skipping")
            return

        last_exc: Exception | None = None
        for attempt in range(_SYNC_BACK_MAX_RETRIES):
            try:
                self._sync_back_once()
                return
            except Exception as exc:
                last_exc = exc
                if attempt < _SYNC_BACK_MAX_RETRIES - 1:
                    delay = _SYNC_BACK_BACKOFF[attempt]
                    _sleep(delay)

        logger.warning("sync_back: all %d attempts failed: %s", _SYNC_BACK_MAX_RETRIES, last_exc)

    def _sync_back_once(self) -> None:
        if self._bulk_download_fn is None:
            raise RuntimeError("_sync_back_once called without bulk_download_fn")

        try:
            file_mapping = list(self._get_files_fn())
        except Exception:
            file_mapping = []

        with tempfile.NamedTemporaryFile(suffix=".tar") as tf:
            self._bulk_download_fn(Path(tf.name))
            try:
                tar_size = os.path.getsize(tf.name)
            except OSError:
                tar_size = 0
            if tar_size > _SYNC_BACK_MAX_BYTES:
                logger.warning("sync_back: tar %d bytes exceeds cap", tar_size)
                return

            with tempfile.TemporaryDirectory(prefix="testai-sync-back-") as staging:
                with tarfile.open(tf.name) as tar:
                    tar.extractall(staging, filter="data")

                applied = 0
                for dirpath, _dirnames, filenames in os.walk(staging):
                    for fname in filenames:
                        staged_file = os.path.join(dirpath, fname)
                        rel = os.path.relpath(staged_file, staging)
                        remote_path = "/" + rel
                        pushed_hash = self._pushed_hashes.get(remote_path)
                        if pushed_hash is not None:
                            remote_hash = _sha256_file(staged_file)
                            if remote_hash == pushed_hash:
                                continue

                        host_path = self._resolve_host_path(remote_path, file_mapping)
                        if host_path is None:
                            host_path = self._infer_host_path(remote_path, file_mapping)
                            if host_path is None:
                                continue

                        os.makedirs(os.path.dirname(host_path), exist_ok=True)
                        shutil.copy2(staged_file, host_path)
                        applied += 1

                if applied:
                    logger.info("sync_back: applied %d changed file(s)", applied)

    def _resolve_host_path(self, remote_path: str, file_mapping: list[tuple[str, str]] | None = None) -> str | None:
        mapping = file_mapping if file_mapping is not None else []
        for host, remote in mapping:
            if remote == remote_path:
                return host
        return None

    def _infer_host_path(self, remote_path: str, file_mapping: list[tuple[str, str]] | None = None) -> str | None:
        mapping = file_mapping if file_mapping is not None else []
        for host, remote in mapping:
            remote_dir = str(Path(remote).parent)
            if remote_path.startswith(remote_dir + "/"):
                host_dir = str(Path(host).parent)
                suffix = remote_path[len(remote_dir):]
                return host_dir + suffix
        return None
