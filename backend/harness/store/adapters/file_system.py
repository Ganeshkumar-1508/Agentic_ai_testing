"""FileSystem Protocol — abstraction over file I/O.

Two adapters: RealFileSystem (production via pathlib) and
MemoryFileSystem (testing via in-memory dict). Lets any module
that reads/writes files be tested without touching the real disk.

This is NOT a domain store Protocol (those live in protocols.py).
It is a lower-level I/O primitive that domain stores USE.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import BinaryIO, Optional, Protocol


class FileSystem(Protocol):
    """Low-level file I/O. Implementations: real disk or in-memory."""

    def read_text(self, path: str | Path) -> str | None:
        """Read text file. Returns None if not found."""
        ...

    def read_bytes(self, path: str | Path) -> bytes | None:
        """Read binary file. Returns None if not found."""
        ...

    def write_text(self, path: str | Path, content: str) -> None:
        """Write text file. Creates parent directories."""
        ...

    def write_bytes(self, path: str | Path, content: bytes) -> None:
        """Write binary file. Creates parent directories."""
        ...

    def append_text(self, path: str | Path, content: str) -> None:
        """Append text to file. Creates parent directories."""
        ...

    def delete(self, path: str | Path) -> bool:
        """Delete file. Returns True if deleted, False if not found."""
        ...

    def exists(self, path: str | Path) -> bool:
        ...

    def is_file(self, path: str | Path) -> bool:
        ...

    def mkdir(self, path: str | Path, parents: bool = True) -> None:
        ...

    def atomic_write(self, path: str | Path, content: str) -> None:
        """Write atomically via temp file + rename. Protects against
        partial writes on crash."""
        ...


class RealFileSystem:
    """Production adapter — delegates to pathlib."""

    def read_text(self, path: str | Path) -> str | None:
        p = Path(path)
        if not p.exists():
            return None
        try:
            return p.read_text("utf-8")
        except OSError:
            return None

    def read_bytes(self, path: str | Path) -> bytes | None:
        p = Path(path)
        if not p.exists():
            return None
        try:
            return p.read_bytes()
        except OSError:
            return None

    def write_text(self, path: str | Path, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")

    def write_bytes(self, path: str | Path, content: bytes) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def append_text(self, path: str | Path, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)

    def delete(self, path: str | Path) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        try:
            p.unlink()
            return True
        except OSError:
            return False

    def exists(self, path: str | Path) -> bool:
        return Path(path).exists()

    def is_file(self, path: str | Path) -> bool:
        return Path(path).is_file()

    def mkdir(self, path: str | Path, parents: bool = True) -> None:
        Path(path).mkdir(parents=parents, exist_ok=True)

    def atomic_write(self, path: str | Path, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(content, "utf-8")
        tmp.replace(p)


class MemoryFileSystem:
    """Testing adapter — in-memory dict. No disk I/O, fast, isolated."""

    def __init__(self) -> None:
        self._files: dict[str, str | bytes] = {}
        self._dirs: set[str] = set()

    def read_text(self, path: str | Path) -> str | None:
        key = str(path)
        val = self._files.get(key)
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val

    def read_bytes(self, path: str | Path) -> bytes | None:
        key = str(path)
        val = self._files.get(key)
        if val is None:
            return None
        if isinstance(val, str):
            return val.encode("utf-8")
        return val

    def write_text(self, path: str | Path, content: str) -> None:
        key = str(path)
        self._files[key] = content
        self._dirs.add(str(Path(path).parent))

    def write_bytes(self, path: str | Path, content: bytes) -> None:
        key = str(path)
        self._files[key] = content
        self._dirs.add(str(Path(path).parent))

    def append_text(self, path: str | Path, content: str) -> None:
        key = str(path)
        existing = self._files.get(key)
        if isinstance(existing, str):
            self._files[key] = existing + content
        elif isinstance(existing, bytes):
            self._files[key] = existing.decode("utf-8") + content
        else:
            self._files[key] = content
        self._dirs.add(str(Path(path).parent))

    def delete(self, path: str | Path) -> bool:
        key = str(path)
        if key in self._files:
            del self._files[key]
            return True
        return False

    def exists(self, path: str | Path) -> bool:
        return str(path) in self._files

    def is_file(self, path: str | Path) -> bool:
        return str(path) in self._files

    def mkdir(self, path: str | Path, parents: bool = True) -> None:
        self._dirs.add(str(path))

    def atomic_write(self, path: str | Path, content: str) -> None:
        self._files[str(path)] = content
        self._dirs.add(str(Path(path).parent))

    def snapshot(self) -> dict[str, str | bytes]:
        """Return copy of all files for test assertions."""
        return dict(self._files)

    def clear(self) -> None:
        self._files.clear()
        self._dirs.clear()
