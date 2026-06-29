"""Managed lifecycle for background tasks and startup phases.

Provides:
- ManagedTask: wraps an async loop with error handling, restart, and clean shutdown.
- StartupPhase: protocol for subsystem initialization with acquire/release.

Usage:
    from harness.lifecycle import ManagedTask, StartupPhase

    # Background tasks with proper lifecycle
    digest = ManagedTask("digest", _digest_loop, interval=3600)
    await digest.start()
    # ... later on shutdown:
    await digest.stop()

    # Startup phases
    class DatabasePhase(StartupPhase):
        async def start(self, ctx): ...
        async def stop(self): ...
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Protocol

logger = logging.getLogger(__name__)


class StartupPhase(Protocol):
    """A subsystem that can be started and stopped in order."""

    async def start(self, ctx: "StartupContext") -> None: ...
    async def stop(self) -> None: ...


@dataclass
class StartupContext:
    """Mutable context passed through startup phases.

    Phases store their outputs here so downstream phases can reference them.
    """
    db: Any = None
    llm: Any = None
    settings_store: Any = None
    store: Any = None
    event_bus: Any = None
    app: Any = None
    extras: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.extras[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)


class ManagedTask:
    """A background async loop with structured lifecycle.

    Features:
    - Exponential backoff restart on crash (max 5 retries)
    - Graceful shutdown with configurable drain timeout
    - Health check via is_healthy property
    - Error count tracking
    """

    def __init__(
        self,
        name: str,
        coro_factory: Callable[..., Coroutine],
        interval: float = 60.0,
        drain_timeout: float = 5.0,
        max_restarts: int = 5,
    ):
        self.name = name
        self._coro_factory = coro_factory
        self._interval = interval
        self._drain_timeout = drain_timeout
        self._max_restarts = max_restarts
        self._task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._restart_count = 0
        self._error_count = 0
        self._last_error: Exception | None = None
        self._started_at: float | None = None

    @property
    def is_healthy(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def error_count(self) -> int:
        return self._error_count

    async def start(self) -> None:
        """Start the managed task."""
        if self._task and not self._task.done():
            logger.warning("ManagedTask '%s' already running", self.name)
            return
        self._shutdown_event.clear()
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self._run_loop(), name=f"managed-{self.name}")
        logger.info("ManagedTask '%s' started", self.name)

    async def stop(self) -> None:
        """Gracefully stop the task with drain timeout."""
        if self._task is None or self._task.done():
            return
        self._shutdown_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=self._drain_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "ManagedTask '%s' did not stop within %.1fs, cancelling",
                self.name, self._drain_timeout,
            )
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            "ManagedTask '%s' stopped (ran %.1fs, %d errors)",
            self.name,
            time.monotonic() - (self._started_at or time.monotonic()),
            self._error_count,
        )

    async def _run_loop(self) -> None:
        """Main loop with restart logic."""
        while not self._shutdown_event.is_set():
            try:
                await self._coro_factory()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._error_count += 1
                self._last_error = exc
                self._restart_count += 1
                if self._restart_count > self._max_restarts:
                    logger.error(
                        "ManagedTask '%s' exceeded max restarts (%d), giving up: %s",
                        self.name, self._max_restarts, exc,
                    )
                    break
                backoff = min(2 ** self._restart_count, 300)
                logger.warning(
                    "ManagedTask '%s' crashed (attempt %d/%d), restarting in %.0fs: %s",
                    self.name, self._restart_count, self._max_restarts, backoff, exc,
                )
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=backoff
                    )
                    break  # shutdown requested during backoff
                except asyncio.TimeoutError:
                    pass  # backoff elapsed, restart

    def __repr__(self) -> str:
        status = "running" if self.is_healthy else "stopped"
        return f"ManagedTask({self.name!r}, {status}, errors={self._error_count})"
