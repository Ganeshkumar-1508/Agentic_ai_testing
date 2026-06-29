"""Base class for execution environment backends — adapted from Hermes.

Unified model: every command spawns a fresh process. CWD persists via
in-band stdout markers. Env vars are captured once and re-sourced per command.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from harness.tools.interrupt import is_interrupted

logger = logging.getLogger(__name__)


def get_testai_home() -> str:
    return str(Path.home() / ".testai")


_activity_callback_local = threading.local()


def set_activity_callback(cb: Callable | None) -> None:
    _activity_callback_local.callback = cb


def _get_activity_callback() -> Callable | None:
    return getattr(_activity_callback_local, "callback", None)


class BaseEnvironment(ABC):
    """Base class for execution environments with CWD tracking and env management."""

    def __init__(self, cwd: str = ".", timeout: int = 120):
        self._cwd = cwd
        self._timeout = timeout
        self._env: dict[str, str] = {}
        self._activity_state = {"last_touch": 0, "start": 0, "interval": 10}

    @property
    def cwd(self) -> str:
        return self._cwd

    @cwd.setter
    def cwd(self, value: str) -> None:
        self._cwd = value

    @abstractmethod
    async def execute(self, command: str, timeout: int | None = None, **kwargs) -> str:
        ...

    def _touch_activity(self, label: str) -> None:
        now = time.monotonic()
        if now - self._activity_state["last_touch"] < self._activity_state["interval"]:
            return
        self._activity_state["last_touch"] = now
        cb = _get_activity_callback()
        if cb:
            elapsed = int(now - self._activity_state["start"])
            cb(f"{label} ({elapsed}s elapsed)")

    def _build_env(self, extra_env: dict | None = None) -> dict:
        env = os.environ.copy()
        env.update(self._env)
        if extra_env:
            env.update(extra_env)
        return env


class LocalEnvironment(BaseEnvironment):
    """Local machine execution."""

    async def execute(self, command: str, timeout: int | None = None, **kwargs) -> str:
        timeout = timeout or self._timeout
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._build_env(),
                cwd=self._cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
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
