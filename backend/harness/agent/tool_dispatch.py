"""ToolDispatcher — owns execute-a-tool-call flow.

Two hard-coded dispatch paths remain (`delegate_task` and `tool_search`)
because their execution mutates agent state OR bridges to another part
of the system. All job-control tools (submit/cancel/pause/resume/list/
status/comment) are dispatched via a dict lookup instead of an if/elif
chain — they share the same handler signature and could be extracted to
standalone BaseTool subclasses when the dispatcher is further decomposed.

The dispatcher is always role-gated: the Agent's `allowed_tools` is the
sole authority for which special tools the LLM can call. The dispatcher
never falls back to "allow all special tools" — there is no unfiltered path.

Product shift: the chat Role is read-only. Its ONE allowed mutation is
`submit_job`, which produces a `JobSpec` and hands it to the
orchestrator. The orchestrator Role has `delegate_task` (to fan out
work to sub-agents) and `tool_search` (for lazy tool discovery).
`submit_job` is not in the orchestrator Role — orchestrators don't
submit jobs; they ARE the jobs.

The closed set of special tools (no others are special-cased):
  - delegate_task — spawns a sub-agent (orchestrator's coordinator)
  - tool_search   — registers newly-discovered tools into the agent's
                    local tool set (lazy tool catalog)
  - submit_job    — chat Role's only mutation; produces a JobSpec and
                    hands it to the autonomous orchestrator
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any, Callable

import httpx

from harness.agent.deps import AgentDependencies
from harness.core.events import (
    ToolExecutionCompleted, ToolExecutionStarted, ApprovalRequired,
)
from harness.delegation import DelegationContext
from harness.events import EventBus
from harness.permissions.manager import PermissionManager
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


# Transient errors that are safe to retry once. Network blips, timeouts,
# and connection drops fall into this bucket. We do NOT retry logic
# errors (ValueError, KeyError, etc.) — those won't fix themselves with
# a second try. httpx.TimeoutException and httpx.NetworkError are the
# parents of all the per-operation sub-types (ConnectTimeout,
# ReadTimeout, ConnectError, ReadError, ...). asyncio.TimeoutError is
# an alias for the built-in TimeoutError in Python 3.11+.
_TRANSIENT_TOOL_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.NetworkError,
    ConnectionError,
    TimeoutError,
)


import bisect
import statistics
import time
from collections import defaultdict
from typing import Callable


class ToolCostTracker:
    """Per-tool cost and token tracking across runs."""

    def __init__(self):
        self._data: dict[str, dict] = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})

    def record(self, tool_name: str, prompt_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0) -> None:
        entry = self._data[tool_name]
        entry["calls"] += 1
        entry["prompt_tokens"] += prompt_tokens
        entry["output_tokens"] += output_tokens
        entry["cost_usd"] += cost_usd

    def summary(self, tool_name: str) -> dict:
        return {"tool": tool_name, **self._data.get(tool_name, {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})}

    def all_summaries(self) -> list[dict]:
        return [self.summary(name) for name in sorted(self._data)]


_tool_cost = ToolCostTracker()


def get_tool_cost_tracker() -> ToolCostTracker:
    return _tool_cost


class ToolLatencyTracker:
    """Per-tool latency tracking with p50/p95 from a sliding window."""

    def __init__(self, window_size: int = 100):
        self._data: dict[str, list[float]] = defaultdict(list)
        self._window = window_size

    def record(self, tool_name: str, duration_s: float) -> None:
        buf = self._data[tool_name]
        buf.append(duration_s)
        if len(buf) > self._window:
            buf.pop(0)

    def p50(self, tool_name: str) -> float | None:
        buf = self._data.get(tool_name)
        if not buf:
            return None
        return statistics.median(buf)

    def p95(self, tool_name: str) -> float | None:
        buf = self._data.get(tool_name)
        if not buf:
            return None
        sorted_buf = sorted(buf)
        idx = min(int(len(sorted_buf) * 0.95), len(sorted_buf) - 1)
        return sorted_buf[idx]

    def summary(self, tool_name: str) -> dict:
        buf = self._data.get(tool_name, [])
        if not buf:
            return {"tool": tool_name, "samples": 0}
        return {
            "tool": tool_name,
            "samples": len(buf),
            "p50": round(self.p50(tool_name), 3),
            "p95": round(self.p95(tool_name), 3),
            "avg": round(sum(buf) / len(buf), 3),
        }

    def all_summaries(self) -> list[dict]:
        return [self.summary(name) for name in sorted(self._data)]


_tool_latency = ToolLatencyTracker()


def get_tool_latency_tracker() -> ToolLatencyTracker:
    return _tool_latency


async def execute_tool_with_retry(
    name: str,
    args: dict,
    *,
    session_id: str | None,
    tool_call_id: str,
    backend_factory: Any | None = None,
    max_retries: int = 1,
    retry_delay_seconds: float = 0.25,
) -> Any:
    """Execute a tool via the registry, retrying once on transient errors.

    The first call awaits ``registry.execute(name, args, ...)``. If it
    raises a transient exception (network timeout, connection drop),
    we wait ``retry_delay_seconds`` and try once more. On the second
    failure, the exception is re-raised so the caller's try/except
    can produce a structured error result.

    Non-transient exceptions are NOT retried — retrying a ValueError
    or KeyError just burns LLM time. The list of transient types is
    :data:`_TRANSIENT_TOOL_EXCEPTIONS`.

    This is a self-healing primitive (Q4-B in the autonomy roadmap).
    It does NOT touch the agent loop or kanban state — a retry is
    transparent to both. The LLM sees either the second-attempt
    success (best case) or a single error message (worst case, same
    as the no-retry path).
    """
    last_exc: BaseException | None = None
    start = time.time()
    for attempt in range(max_retries + 1):
        try:
            result = await registry.execute(
                name, args,
                session_id=session_id,
                tool_call_id=tool_call_id,
                backend_factory=backend_factory,
            )
            _tool_latency.record(name, time.time() - start)
            return result
        except _TRANSIENT_TOOL_EXCEPTIONS as exc:
            last_exc = exc
            if attempt >= max_retries:
                logger.warning(
                    "tool %s transient error after %d attempts: %s — giving up",
                    name, attempt + 1, exc,
                )
                raise
            logger.info(
                "tool %s transient error attempt %d/%d: %s — retrying in %.2fs",
                name, attempt + 1, max_retries + 1, exc, retry_delay_seconds,
            )
            await asyncio.sleep(retry_delay_seconds)
    # Defensive: unreachable because the last iteration either returns
    # or re-raises, but keep the type-checker happy.
    assert last_exc is not None
    raise last_exc


# The closed set of tool names whose execution mutates agent state OR
# bridges to another part of the system. Adding a new entry is a
# deliberate change.
SPECIAL_TOOL_NAMES: frozenset[str] = frozenset({
    "delegate_task", "tool_search",
})

# Typed dispatch table for the chat-side job-control tools (C09).
# The seven tool names are routed to :class:`JobControlDispatcher`
# via ``_dispatch_job_control``. ``JobControlAction`` is the enum
# and ``JobControlDispatcher`` is the deep module in
# :mod:`harness.services.job_control`; this map is the only
# coupling between the dispatcher and the tool-registry.
from harness.services.job_control import JobControlAction  # noqa: E402

_JOB_CONTROL_ACTION_BY_NAME: dict[str, "JobControlAction"] = {
    action.value: action for action in JobControlAction
}

# Re-export the user-tier override helpers from the new home so existing
# callers (chat router, tests) keep working.
from harness.services.job_control import (  # noqa: E402
    set_user_tier_override,
    reset_user_tier_override,
)


# C1.1: User-requested tier override &mdash; the chat UI's tier
# selector is authoritative; the LLM's `tier` arg is a hint. The
# ContextVar, set/reset helpers, and the authoritative-fallback
# logic now live in
# :mod:`harness.services.job_control` (C09 deepening). The re-exports
# above preserve the public surface for any caller that imported
# these names from `harness.agent.tool_dispatch` before C09.


class ToolDispatcher:
    """Handles tool execution including special-cased tools.

    Agent creates one dispatcher per run and delegates every tool call
    to it. The dispatcher is always role-gated: the Agent's
    `allowed_tools` is required and determines which special tools the
    LLM can call. There is no unfiltered path.

    The dispatcher handles:
      - Permission checking (deny/ask/allow)
      - Event emission for tool start/end
      - Special-cased tools (delegate_task, tool_search, submit_job),
        each gated by role membership
      - Regular tool execution via registry
    """

    def __init__(
        self,
        event_bus: EventBus,
        permissions: PermissionManager,
        mode: str,
        session_id: str,
        agent_id: str,
        delegation: DelegationContext,
        allowed_tools: list[str],
        deps: AgentDependencies | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._permissions = permissions
        self.mode = mode
        self.session_id = session_id
        self.agent_id = agent_id
        self.delegation = delegation
        self._deps = deps
        self._role_allowed_tools: frozenset[str] = frozenset(allowed_tools)

    async def _emit(self, event) -> None:
        await self._event_bus.emit(event)

    async def _emit_and_store(self, event) -> None:
        """Emit to EventBus AND directly store to stream_events DB."""
        # Always emit to EventBus
        await self._event_bus.emit(event)
        # Also store directly to DB as fallback for SSE polling
        sid = getattr(event, "session_id", None)
        if sid:
            try:
                from harness.api.state import emit_stream_event
                etype = type(event).__name__
                payload = {"data": event.to_dict() if hasattr(event, 'to_dict') else str(event)[:500]}
                await emit_stream_event(sid, etype, payload)
            except Exception:
                pass

    async def execute(self, tc: dict[str, Any], llm_response_id: str = "",
                      tool_call_index: int = 0) -> str:
        """Execute a single tool call. Returns the output string."""
        name = tc["function"]["name"]
        trace_id = str(uuid.uuid4())
        try:
            args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            args = {}

        await self._emit_and_store(ToolExecutionStarted(
            tool_name=name, tool_input=str(args)[:500], trace_id=trace_id,
            agent_id=self.agent_id, session_id=self.session_id,
            llm_response_id=llm_response_id,
        ))

        # Role-gate: if the name is a special tool and the role does not
        # allow it, reject. The role's `allowed_tools` is the sole
        # authority — there is no unfiltered path.
        if name in SPECIAL_TOOL_NAMES and name not in self._role_allowed_tools:
            return await self._reject_special_tool(
                name, trace_id, llm_response_id,
            )

        if name == "delegate_task":
            return await self._handle_delegate_task(args, trace_id, llm_response_id)
        if name == "tool_search":
            return await self._handle_tool_search(args, trace_id, llm_response_id)
        action = _JOB_CONTROL_ACTION_BY_NAME.get(name)
        if action is not None:
            if name not in self._role_allowed_tools:
                return await self._reject_special_tool(
                    name, trace_id, llm_response_id,
                )
            return await self._dispatch_job_control(
                action, args, trace_id, llm_response_id,
            )
        return await self._handle_regular_tool(name, args, trace_id, llm_response_id)

    async def _reject_special_tool(
        self, name: str, trace_id: str, llm_response_id: str = "",
    ) -> str:
        """A special-cased tool was called by a role that does not allow it.

        Emits a `ToolExecutionCompleted(success=False)` event so the audit
        log shows the rejection, and returns a string the LLM can read.
        """
        message = (
            f"Error: Tool '{name}' is not available in this role's toolset. "
            f"This tool mutates agent state and is restricted to roles that "
            f"declare it in their `allowed_tools` list."
        )
        await self._emit_and_store(ToolExecutionCompleted(
            tool_name=name, output_preview="Rejected by role policy",
            success=False, trace_id=trace_id, agent_id=self.agent_id,
            session_id=self.session_id, llm_response_id=llm_response_id,
            is_error=True,
        ))
        return message

    async def _dispatch_job_control(
        self,
        action: "JobControlAction",
        args: dict[str, Any],
        trace_id: str,
        llm_response_id: str,
    ) -> str:
        """Route a job-control tool call to :class:`JobControlDispatcher`.

        Builds the ``JobControlContext`` from the dispatcher's own
        state, runs the action, and emits exactly one
        ``ToolExecutionCompleted`` event with ``success`` and
        ``is_error`` derived from the structured result. This
        centralises the emit policy that was previously
        inconsistent across the seven inline ``_handle_*_job``
        methods (some only on success, some never on error).
        """
        from harness.jobs.spec import _job_spec_store
        from harness.services.job_control import (
            JobControlContext,
            JobControlDispatcher,
        )

        try:
            store = _job_spec_store()
        except Exception:
            store = None

        ctx = JobControlContext(
            store=store,
            session_id=self.session_id or "",
            agent_id=self.agent_id or "",
            trace_id=trace_id,
            llm_response_id=llm_response_id,
            event_bus=self._event_bus,
            deps=self._deps,
        )
        dispatcher = JobControlDispatcher(ctx)
        result = await dispatcher.dispatch(action, args)

        if result.emit_completed:
            await self._emit_and_store(ToolExecutionCompleted(
                tool_name=action.value,
                output_preview=(result.output or "")[:200],
                success=result.success,
                trace_id=trace_id,
                agent_id=self.agent_id,
                session_id=self.session_id,
                llm_response_id=llm_response_id,
                is_error=not result.success,
            ))
        return result.output or ""

    async def _handle_delegate_task(self, args: dict, trace_id: str, llm_response_id: str = "") -> str:
        result = await self._dispatch_delegate_task(args)
        output = result if isinstance(result, str) else (
            result.output if getattr(result, "success", False)
            else f"Error: {getattr(result, 'error', None) or result}"
        )
        await self._emit_and_store(ToolExecutionCompleted(
            tool_name="delegate_task", output_preview=(output or "")[:200], success=True,
            trace_id=trace_id, agent_id=self.agent_id,
            session_id=self.session_id, llm_response_id=llm_response_id,
        ))
        return output or ""

    async def _handle_tool_search(self, args: dict, trace_id: str, llm_response_id: str = "") -> str:
        result = await registry.execute("tool_search", args, session_id=self.session_id, tool_call_id=trace_id)
        output = result.output if result.success else f"Error: {result.error or result.output}"
        if result.success and result.data and result.data.get("tools"):
            for tool_spec in result.data["tools"]:
                tool_name = tool_spec.get("function", {}).get("name", "")
                if tool_name:
                    self._handle_discovered_tool(tool_name, tool_spec)
        await self._emit_and_store(ToolExecutionCompleted(
            tool_name="tool_search", output_preview=output[:200] if output else "", success=result.success,
            trace_id=trace_id, agent_id=self.agent_id,
            session_id=self.session_id, llm_response_id=llm_response_id,
        ))
        return output

    def _handle_discovered_tool(self, tool_name: str, tool_spec: dict) -> None:
        """Hook for agent to register discovered tools. Override in subclass."""

    async def _handle_regular_tool(self, name: str, args: dict, trace_id: str, llm_response_id: str = "") -> str:
        level = self._permissions.resolve_level(name, args)
        if level == "deny":
            await self._emit_and_store(ToolExecutionCompleted(
                tool_name=name, output_preview="Denied by policy", success=False,
                trace_id=trace_id, agent_id=self.agent_id,
                session_id=self.session_id, llm_response_id=llm_response_id,
            ))
            return f"Error: Tool '{name}' is not permitted in {self.mode} mode"
        if level == "ask":
            approval_id = self._permissions.request_approval(name, args)
            await self._emit(ApprovalRequired(
                approval_id=approval_id, tool_name=name,
                tool_args=str(args)[:500], mode=self.mode,
            ))
            approved = await self._permissions.await_approval(approval_id, timeout=120.0)
            if not approved:
                return f"Tool '{name}' execution denied by user."
        # Q11-E: deterministic pre-tool-call hooks are now handled by the
        # unified HookPipeline (phase 0) in Agent.run_stream. The pipeline's
        # on_before_tool calls gate handlers before tool dispatch. This site
        # kept the old inline check removed to avoid double-evaluation.
        # The block/ask routing below is still owned by PermissionManager.
        try:
            result = await execute_tool_with_retry(
                name, args,
                session_id=self.session_id,
                tool_call_id=trace_id,
                backend_factory=getattr(self._deps, 'backend_factory', None) if self._deps else None,
            )
            output = result.output if result.success else f"Error: {result.error or result.output}"
            success = result.success
        except Exception as e:
            output = f"Error: {e}"
            success = False
        # F23: emit a ToolProgress event with the first 200 chars of the
        # tool output so the UI gets a streaming-style preview between
        # the Started and Completed events.  Long-running tools (bash,
        # kg_refresh, test_executor) become visible mid-execution.
        if output and len(output) > 0:
            try:
                from harness.core.events import ToolProgress as _ToolProgress
                _progress = _ToolProgress(
                    tool_name=name,
                    content=(output or "")[:200],
                    trace_id=trace_id,
                    agent_id=self.agent_id,
                    session_id=self.session_id,
                    kind="stdout" if success else "stderr",
                )
                await self._event_bus.emit(_progress)
            except Exception:
                pass
        await self._emit_and_store(ToolExecutionCompleted(
            tool_name=name, output_preview=(output or "")[:200], success=success,
            trace_id=trace_id, agent_id=self.agent_id,
            is_error=not success, session_id=self.session_id,
            llm_response_id=llm_response_id,
        ))
        return output or ""

    async def _dispatch_delegate_task(self, args: dict) -> str:
        from harness.agent.curation import curate_subagent_context
        from harness.agent.validation import validate_subagent_output
        dt = registry.get("delegate_task")
        if not dt:
            return "Error: delegate_task tool not available"
        dt._backend_factory = getattr(self._deps, 'backend_factory', None) if self._deps else None
        dt._session_id = self.session_id
        dt.delegation = self.delegation
        if not args.get("context"):
            # We need parent messages — the agent must provide them
            pass
        result = await dt.run(**args)
        raw_output = result.output if result.success else f"Error: {result.error or result.output}"
        validation = validate_subagent_output(raw_output)
        if not validation.valid:
            return validation.sanitized + f"\n\n[validation: issues={validation.issues}]"
        return validation.sanitized

