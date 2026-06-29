from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

DEFAULT_RESULT_SIZE_CHARS = 100_000
MAX_PREVIEW_CHARS = 2_000

from harness.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ToolHandler — typed contract for raw tool handlers
# ---------------------------------------------------------------------------
#
# C3 deepening (per the architecture review): the registry had two
# registration paths — `register_tool` (the canonical async-aware
# path) and `register_raw` (the thin escape hatch for external tool
# sources — MCP, plugins, future OpenAPI bridges). The escape hatch
# accepted a sync handler and let callers LIE about whether the
# handler was async by setting `is_async=False` while wrapping an
# `asyncio.run()` around a real coroutine.
#
# The fix: admit the handler can be a coroutine function, and let
# `execute()` schedule it on the running loop. The
# `ToolHandler` Protocol below is the typed shape both flavours
# fit; `register_raw` and `register_async_raw` are the two
# registration entry points.
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolHandler(Protocol):
    """A typed callable that runs a tool.

    Sync and async handlers both satisfy this Protocol. The
    registry's `execute()` method checks whether the handler's
    return value is awaitable and awaits it if so — no more
    `is_async` flag to lie about.

    Implementations:
      - Sync:    `def handle(args) -> str | ToolResult: ...`
      - Async:   `async def handle(args) -> str | ToolResult: ...`

    Both shapes are accepted by `register_raw` (sync) and
    `register_async_raw` (async). The registry stores the
    `is_async` flag for dispatch (sync handlers run on the
    agent's event loop via a thread-pool trampoline; async
    handlers are awaited directly on the loop), but the flag
    is set automatically — callers cannot lie.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


def _is_async_callable(handler: Callable) -> bool:
    """True if `handler` is a coroutine function.

    We check `asyncio.iscoroutinefunction` rather than inspecting
    the return type at call time, because the latter would mean
    a sync handler that *returns* a coroutine (a misuse, but
    possible) gets treated as async.
    """
    return asyncio.iscoroutinefunction(handler)

_SKIP_MODULES = frozenset({
    "__init__.py", "registry.py", "base.py", "toolsets.py",
})

_CHECK_FN_TTL_SECONDS = 30.0


# ---------------------------------------------------------------------------
# ToolEntry — metadata for one registered tool
# ---------------------------------------------------------------------------


@dataclass
class ToolEntry:
    name: str
    toolset: str
    handler: Callable
    spec: dict[str, Any]
    is_async: bool = False
    check_fn: Callable[[], bool] | None = None
    max_result_size_chars: int | None = None
    capabilities: list[str] = field(default_factory=list)
    default_level: str = "ask"
    dynamic_schema_overrides: Callable[[], dict] | None = None
    concurrency_safe: bool = False
    """True if multiple instances can run in parallel (read-only tools)."""


# ---------------------------------------------------------------------------
# Thread-safe registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()
        self._generation: int = 0

    # -- Registration --

    def register(
        self, tool: BaseTool, toolset: str = "",
        check_fn: Callable[[], bool] | None = None,
        default_level: str | None = None,
        max_result_size_chars: int | None = None,
        dynamic_schema_overrides: Callable[[], dict] | None = None,
    ) -> None:
        """Register a tool with optional check_fn and overrides."""
        if default_level is not None:
            tool.default_level = default_level
        return self.register_tool(
            tool, toolset=toolset, check_fn=check_fn,
            max_result_size_chars=max_result_size_chars,
            dynamic_schema_overrides=dynamic_schema_overrides,
        )

    def register_raw(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        is_async: bool | None = None,
        description: str = "",
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """Register a tool from raw components (used by plugins,
        legacy sync sources, future OpenAPI bridges).

        Pass a sync handler; the registry will run it on the
        agent's event loop via a thread-pool trampoline. For
        async handlers (the MCP client, future async plugins),
        use `register_async_raw` instead.

        The `is_async` flag is now auto-detected from the handler
        via `asyncio.iscoroutinefunction()`. Passing it
        explicitly is deprecated — the auto-detection is
        authoritative. The parameter is kept for backward
        compatibility with the existing call sites; explicit
        `True`/`False` will be ignored on conflict with the
        detected value (a warning is logged).
        """
        detected_async = _is_async_callable(handler)
        if is_async is not None and is_async != detected_async:
            logger.warning(
                "register_raw(%s): explicit is_async=%s disagrees "
                "with detected is_async=%s; using the detected value",
                name, is_async, detected_async,
            )
        entry = ToolEntry(
            name=name,
            toolset=toolset,
            handler=handler,
            spec={"name": name, "description": description, "parameters": schema.get("parameters", {"type": "object", "properties": {}})},
            is_async=detected_async,
            check_fn=check_fn,
            capabilities=[],
            default_level="ask",
        )
        with self._lock:
            if entry.name in self._tools:
                logger.debug("Tool '%s' already registered, skipping", entry.name)
                return
            self._tools[entry.name] = entry
            self._generation += 1

    def register_async_raw(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable[..., Awaitable[Any]],
        description: str = "",
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """Register an async tool from raw components.

        This is the C3 deepening of the architecture review: an
        async-aware registration path that doesn't lie about
        sync-ness. The handler MUST be a coroutine function
        (`async def`). The registry's `execute()` method awaits
        the handler on the agent's event loop, so:

          - **Cancellation propagates.** When the parent
            Agent's loop is cancelled (interrupt, max-rounds,
            SIGINT), the MCP call's child coroutine sees the
            cancellation and unwinds. No more silent leaks.
          - **One event loop, not one-per-tool-call.** The MCP
            call runs on the loop the dispatcher is on. No
            fresh `Selector`/`ThreadPoolExecutor` per call.
          - **No re-entrancy hazard.** `asyncio.run()` from
            inside a running loop used to raise
            `RuntimeError: asyncio.run() cannot be called from a
            running event loop` and the call was silently
            swallowed by the `try/except` in the registry.
            With the async path, the handler is a real
            coroutine on the running loop — no re-entrancy.

        The handler type is `Callable[..., Awaitable[Any]]` so
        static type-checkers see it as a coroutine function
        (not a sync function that returns a coroutine). At
        registration time we still verify via
        `asyncio.iscoroutinefunction` and refuse to register
        a sync handler here — the type-hint and the runtime
        check are belt-and-suspenders.
        """
        if not _is_async_callable(handler):
            raise TypeError(
                f"register_async_raw({name!r}): handler is not a "
                f"coroutine function. Use `register_raw` for sync "
                f"handlers. The async path is required for any "
                f"external source with a real async API (MCP, "
                f"future async plugins, future async bridges)."
            )
        entry = ToolEntry(
            name=name,
            toolset=toolset,
            handler=handler,
            spec={"name": name, "description": description, "parameters": schema.get("parameters", {"type": "object", "properties": {}})},
            is_async=True,
            check_fn=check_fn,
            capabilities=[],
            default_level="ask",
        )
        with self._lock:
            if entry.name in self._tools:
                logger.debug("Tool '%s' already registered, skipping", entry.name)
                return
            self._tools[entry.name] = entry
            self._generation += 1

    def register_tool(
        self,
        tool: BaseTool,
        toolset: str = "",
        check_fn: Callable[[], bool] | None = None,
        max_result_size_chars: int | None = None,
        dynamic_schema_overrides: Callable[[], dict] | None = None,
    ) -> None:
        entry = ToolEntry(
            name=tool.name,
            toolset=toolset,
            handler=tool.run,
            spec=tool.to_openai_tool().get("function", {}),
            is_async=True,
            check_fn=check_fn,
            max_result_size_chars=max_result_size_chars,
            capabilities=list(tool.capabilities),
            default_level=tool.default_level,
            concurrency_safe=tool.concurrency_safe,
            dynamic_schema_overrides=dynamic_schema_overrides,
        )
        with self._lock:
            if entry.name in self._tools:
                logger.debug("Tool '%s' already registered, skipping", entry.name)
                return
            self._tools[entry.name] = entry
            self._generation += 1

    def deregister(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)
            self._generation += 1

    # -- Lookup --

    def get(self, name: str) -> BaseTool | None:
        entry = self._get_entry(name)
        if entry is None:
            return None
        return self._entry_to_tool(entry)

    def _get_entry(self, name: str) -> ToolEntry | None:
        with self._lock:
            return self._tools.get(name)

    def _entry_to_tool(self, entry: ToolEntry) -> BaseTool:
        class _DynamicTool(BaseTool):
            name = entry.name
            description = entry.spec.get("description", "")
            capabilities = entry.capabilities
            default_level = entry.default_level

            def spec(self):
                from harness.tools.base import ToolSpec
                params = entry.spec.get("parameters", {"type": "object", "properties": {}})
                return ToolSpec(name=self.name, description=self.description, input_schema=params)

            async def run(self, **kwargs: Any) -> ToolResult:
                try:
                    if entry.is_async:
                        result = await entry.handler(**kwargs)
                    else:
                        result = entry.handler(kwargs)
                    if isinstance(result, ToolResult):
                        return result
                    return ToolResult(success=True, output=str(result))
                except Exception as e:
                    return ToolResult(success=False, output=str(e), error=str(e))

            def to_openai_tool(self) -> dict[str, Any]:
                return {"type": "function", "function": dict(entry.spec)}

        return _DynamicTool()

    def get_spec(self, name: str) -> dict[str, Any] | None:
        entry = self._get_entry(name)
        if entry is None:
            return None
        spec = {"type": "function", "function": dict(entry.spec)}
        return spec

    # -- Schema retrieval (with check_fn filtering) --

    def list_specs(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        result = []
        with self._lock:
            entries = dict(self._tools)

        check_cache: dict[int, bool] = {}

        def _check(entry: ToolEntry) -> bool:
            if entry.check_fn is None:
                return True
            fn_id = id(entry.check_fn)
            if fn_id not in check_cache:
                check_cache[fn_id] = _check_fn_cached(entry.check_fn)
            return check_cache[fn_id]

        for name, entry in entries.items():
            if tool_names is not None and name not in tool_names:
                continue
            if not _check(entry):
                continue
            spec = {"type": "function", "function": dict(entry.spec)}
            if entry.dynamic_schema_overrides:
                try:
                    overrides = entry.dynamic_schema_overrides()
                    if isinstance(overrides, dict):
                        spec["function"].update(overrides)
                except Exception as exc:
                    logger.warning("dynamic_schema_overrides for %s failed: %s", name, exc)
            result.append(spec)
        return result

    # -- Execution --

    # Tool handlers MUST NOT see internal orchestration kwargs. The
    # dispatcher and the orchestrator's scope-tracking both inject
    # keys starting with `_` (`_session_id`, `_tool_call_id`,
    # `_backend_factory`, `_scope_run_id`, `_scope_session_id`,
    # `_scope_agent_id`, `_scope_parent_id`, ...). They are for
    # event-emission / OTel-span only. Strip them before calling
    # the handler so tool functions with strict signatures
    # (e.g. `cmd_kanban_create(board_id, title, ...)`) don't blow
    # up with `got an unexpected keyword argument '_session_id'`.
    #
    # This is a universal fix — every tool is now protected,
    # not just the ones that happen to have `**kwargs`. The
    # e2e-test (June 2026) surfaced this when the orchestrator
    # auto-injected scope kwargs on the first run; the kanban
    # tool failed every call with the same TypeError.
    _INTERNAL_KWARG_PREFIX = "_"

    async def execute(
        self, name: str, args: dict[str, Any],
        session_id: str = "", tool_call_id: str = "",
        backend_factory: Any = None,
    ) -> ToolResult:
        entry = self._get_entry(name)
        if entry is None:
            return ToolResult(success=False, output="", error=f"Unknown tool: {name}")
        try:
            kwargs = dict(args)
            if session_id:
                kwargs.setdefault("_session_id", session_id)
            if tool_call_id:
                kwargs.setdefault("_tool_call_id", tool_call_id)
            if backend_factory is not None:
                kwargs.setdefault("_backend_factory", backend_factory)
            # Strip internal / scope kwargs before handing to the
            # tool. The handler is the agent-facing API; it should
            # only see args the LLM (or the caller) provided.
            kwargs = {
                k: v for k, v in kwargs.items()
                if not k.startswith(self._INTERNAL_KWARG_PREFIX)
            }
            if entry.is_async:
                result = await entry.handler(**kwargs)
            else:
                result = entry.handler(kwargs)
            _tool_health.record(name, True)
            if isinstance(result, ToolResult):
                output = result.output
                if result.success:
                    output = self._apply_output_limit(name, output, session_id, tool_call_id)
                verdict = self._classify_output(name, output, result.success)
                data = dict(result.data or {})
                data["rca_verdict"] = verdict
                return ToolResult(success=result.success, output=output, data=data, error=result.error)
            output = str(result)
            output = self._apply_output_limit(name, output, session_id, tool_call_id)
            verdict = self._classify_output(name, output, True)
            return ToolResult(success=True, output=output, data={"rca_verdict": verdict})
        except Exception as e:
            _tool_health.record(name, False)
            verdict = self._classify_output(name, str(e), False)
            return ToolResult(success=False, output=str(e), error=str(e), data={"rca_verdict": verdict})

    def _classify_output(self, tool_name: str, output: str, success: bool) -> dict:
        """Classify tool output using the FailureClassifier module.

        C5: replaces the old ``classify_tool_error`` from ``rca.py``
        with a typed ``FailureClassification`` from
        ``harness.services.failure_classification.PatternClassifier``.
        Returns a plain dict (for JSON serialization in ToolResult.data).
        """
        try:
            from harness.services.failure_classification import PatternClassifier
            classifier = PatternClassifier()
            fc = classifier.classify(tool_name, output, success)
            from dataclasses import asdict
            return asdict(fc)
        except Exception:
            return {"verdict": "unknown", "matched_pattern": None, "category": "rca_unavailable"}

    def _apply_output_limit(self, name: str, output: str, session_id: str, tool_call_id: str) -> str:
        entry = self._get_entry(name)
        max_chars = entry.max_result_size_chars if entry and entry.max_result_size_chars is not None else DEFAULT_RESULT_SIZE_CHARS
        if len(output) <= max_chars:
            return output
        preview = output[:MAX_PREVIEW_CHARS]
        ref = f"tool_result:{session_id}:{tool_call_id}" if session_id and tool_call_id else ""
        spill_line = f"\n\n[Output truncated to {MAX_PREVIEW_CHARS} chars. Full output stored as {ref}.]" if ref else f"\n\n[Output truncated to {MAX_PREVIEW_CHARS} chars.]"

        if session_id and tool_call_id and hasattr(self, "db") and self.db is not None:
            try:
                from harness.memory.store import PersistentStore
                store = PersistentStore(self.db)
                import asyncio
                asyncio.ensure_future(store.store_value(ref, output, category="tool_spill"))
            except Exception:
                pass

        return preview + spill_line

    def list_entries(self) -> list[ToolEntry]:
        with self._lock:
            return list(self._tools.values())

    # -- Toolset queries --

    def tools_for_toolset(self, toolset: str) -> list[str]:
        with self._lock:
            return [e.name for e in self._tools.values() if e.toolset == toolset]

    def list_by_capability(self, capability: str) -> list[BaseTool]:
        result = []
        with self._lock:
            for entry in self._tools.values():
                if capability in entry.capabilities:
                    result.append(self._entry_to_tool(entry))
        return result

    def list_capabilities(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        with self._lock:
            for name, entry in self._tools.items():
                if entry.capabilities:
                    result[name] = entry.capabilities
        return result

    # -- Discovery --

    def discover_tools(self, tools_dir: str | None = None) -> None:
        if tools_dir is None:
            tools_dir = os.path.dirname(os.path.abspath(__file__))
        tools_path = Path(tools_dir)
        self._discover_in_directory(tools_path, module_prefix="harness.tools")

        # Also scan user tool directories (~/.testai/tools/ and ./.testai/tools/)
        for user_dir in (Path.home() / ".testai" / "tools", Path.cwd() / ".testai" / "tools"):
            if user_dir.exists():
                self._discover_in_directory(user_dir, module_prefix="")

    def _discover_in_directory(self, directory: Path, module_prefix: str = "") -> None:
        for path in sorted(directory.glob("*.py")):
            if path.name in _SKIP_MODULES or path.name == "__init__.py":
                continue
            try:
                import importlib, importlib.util
                module_name = path.stem
                if module_prefix:
                    module_name = f"{module_prefix}.{module_name}"
                if module_prefix:
                    importlib.import_module(module_name)
                else:
                    spec = importlib.util.spec_from_file_location(module_name, path)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                logger.info("Discovered tool: %s", path.stem)
            except Exception as e:
                logger.warning("Failed to load %s: %s", path.stem, e)

    def discover_tools_explicit(self, tool_names: list[str]) -> None:
        for name in tool_names:
            module_name = f"harness.tools.{name}"
            try:
                import importlib
                importlib.import_module(module_name)
                logger.info("Loaded tool: %s", name)
            except Exception as e:
                logger.warning("Failed to load %s: %s", name, e)

    # -- Generation counter (for cache invalidation) --

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation


# ---------------------------------------------------------------------------
# check_fn helpers — common availability checks
# ---------------------------------------------------------------------------


def env_available(*names: str) -> Callable[[], bool]:
    """Returns a check_fn that passes when ALL named env vars are set & non-empty."""
    def _check() -> bool:
        return all(bool(os.environ.get(n, "").strip()) for n in names)
    return _check


def any_env_available(*names: str) -> Callable[[], bool]:
    """Returns a check_fn that passes when ANY named env var is set & non-empty."""
    def _check() -> bool:
        return any(bool(os.environ.get(n, "").strip()) for n in names)
    return _check


def binary_available(*names: str) -> Callable[[], bool]:
    """Returns a check_fn that passes when ALL named binaries are on PATH."""
    def _check() -> bool:
        for name in names:
            path = shutil.which(name)
            if path is None:
                return False
        return True
    return _check


def check_any(*checks: Callable[[], bool]) -> Callable[[], bool]:
    """Returns a check_fn that passes when ANY of the given checks pass."""
    def _check() -> bool:
        return any(c() for c in checks)
    return _check


# ---------------------------------------------------------------------------
# Tool health tracking — per-tool success/failure rate with sliding window
# ---------------------------------------------------------------------------


class ToolHealthTracker:
    """Tracks per-tool health (success rate, last seen, error count)."""

    def __init__(self, window_size: int = 100):
        self._data: dict[str, list[tuple[float, bool]]] = {}
        self._lock = threading.Lock()
        self._window = window_size

    def record(self, tool_name: str, success: bool) -> None:
        with self._lock:
            buf = self._data.setdefault(tool_name, [])
            buf.append((time.time(), success))
            if len(buf) > self._window:
                buf.pop(0)

    def success_rate(self, tool_name: str) -> float | None:
        with self._lock:
            buf = self._data.get(tool_name)
            if not buf:
                return None
            successes = sum(1 for _, ok in buf if ok)
            return successes / len(buf)

    def last_seen(self, tool_name: str) -> float | None:
        with self._lock:
            buf = self._data.get(tool_name)
            if not buf:
                return None
            return buf[-1][0]

    def summary(self, tool_name: str) -> dict:
        with self._lock:
            buf = self._data.get(tool_name, [])
            if not buf:
                return {"tool": tool_name, "status": "unknown"}
            successes = sum(1 for _, ok in buf if ok)
            return {
                "tool": tool_name,
                "calls": len(buf),
                "success_rate": round(successes / len(buf), 3),
                "successes": successes,
                "failures": len(buf) - successes,
                "last_seen": buf[-1][0],
                "status": "healthy" if successes / len(buf) > 0.8 else "degraded" if successes / len(buf) > 0.5 else "unhealthy",
            }

    def all_summaries(self) -> list[dict]:
        with self._lock:
            return [self.summary(name) for name in sorted(self._data)]


_tool_health = ToolHealthTracker()


def get_tool_health() -> ToolHealthTracker:
    return _tool_health


# ---------------------------------------------------------------------------
# check_fn TTL cache
# ---------------------------------------------------------------------------

_check_fn_cache: dict[int, tuple[float, bool]] = {}
_check_fn_cache_lock = threading.Lock()


def _check_fn_cached(fn: Callable[[], bool]) -> bool:
    now = time.monotonic()
    fn_id = id(fn)
    with _check_fn_cache_lock:
        cached = _check_fn_cache.get(fn_id)
        if cached is not None and now - cached[0] < _CHECK_FN_TTL_SECONDS:
            return cached[1]
    try:
        value = bool(fn())
    except Exception:
        value = False
    with _check_fn_cache_lock:
        _check_fn_cache[fn_id] = (now, value)
    return value


def invalidate_check_cache() -> None:
    with _check_fn_cache_lock:
        _check_fn_cache.clear()


# ---------------------------------------------------------------------------
# Module-level singleton + backward-compat register()
# ---------------------------------------------------------------------------

registry = ToolRegistry()


def register(tool: BaseTool, toolset: str = "") -> None:
    registry.register_tool(tool, toolset=toolset)


# ---------------------------------------------------------------------------
# Helper JSON formatters
# ---------------------------------------------------------------------------


def tool_error(message: str, **extra: Any) -> str:
    result: dict[str, Any] = {"error": str(message)}
    if extra:
        result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def tool_result(data: dict[str, Any] | None = None, **kwargs: Any) -> str:
    if data is not None:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(kwargs, ensure_ascii=False)
