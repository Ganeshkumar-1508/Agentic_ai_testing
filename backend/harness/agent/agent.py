"""Agent — unified query engine. Runs the LLM tool-calling loop.

This is a single-class agent combining all functionality that was
previously split across 6 mixin files. Sequencing (Interrupts →
Emitters → Reflexion → Tools → Loop) is handled via method calls
in `run()` rather than MRO ordering.

Key entry points:
  - `run(user_input)` — blocking call, returns final response string
  - `run_stream(user_input)` — async generator for SSE
  - `interrupt()` — cooperative cancel signal

Owned separately (not merged):
  - `ReflexionMemory` — persistent cross-session reflexion store
  - `AgentDependencies` — dependency container dataclass
  - `validate_subagent_output` / `curate_subagent_context` — standalone fns
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any, AsyncGenerator

from harness.agent.deps import AgentDependencies
from harness.agent.tool_dispatch import ToolDispatcher
from harness.core.events import (
    AgentCompleted,
    AgentStarted,
    ErrorEvent,
    LLMCallCompleted,
    LLMCallStarted,
    ReflexionInjected,
    RoundCompleted,
    RoundStarted,
    StatusEvent,
    StreamEvent,
    TokenGenerated,
    ReasoningGenerated,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from harness.delegation import DelegationContext
from harness.events import EventBus
from harness.llm import ChatMessage, LLMRouter
from harness.mcp.client import MCPClient
from harness.memory.store import PersistentStore
from harness.permissions.manager import PermissionManager
from harness.prompt_builder import build_subagent_prompt, build_system_prompt
from harness.tools.registry import registry

__all__ = ["Agent", "AgentDependencies"]

logger = logging.getLogger(__name__)

MAX_REFLECTIONS_PER_RUN: int = 3
MAX_REFLECTIONS_PER_TOOL: int = 2
ERROR_MARKERS: tuple[str, ...] = ("Error:", "Exception:", "Traceback")


class Agent:
    """Single LLM-driven agent. Owns its own run loop and tool dispatch."""

    def __init__(
        self,
        deps: AgentDependencies,
        allowed_tools: list[str],
        mode: str = "auto",
        max_tool_rounds: int = 20,
        system_prompt: str | None = None,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        delegation: DelegationContext | None = None,
        recipe_name: str = "chat",
        recovery: Any = None,
        middlewares: list | None = None,
    ):
        self._deps = deps
        self.mode = mode
        self._allowed_tools = list(allowed_tools)
        self.max_tool_rounds = max_tool_rounds
        self._recipe_name = recipe_name
        from harness.recovery.config import RecoveryConfig
        self.recovery: RecoveryConfig = recovery if isinstance(recovery, RecoveryConfig) else RecoveryConfig()

        from harness.hook.pipeline import HookPipeline
        self._middleware_chain = HookPipeline()
        if middlewares:
            for mw in middlewares:
                self._middleware_chain.add_middleware(mw)
        # Wire deterministic pre-tool gates (phase 0) into the pipeline.
        # Gates use check_pre(name, args) → {"action": "block"|"allow"|"ask", ...}
        # The adapter handles block→False, and ask→approval-modal→block/allow.
        _gates_wired = False
        if not _gates_wired:
            try:
                from harness.hook_registry import get_hooks as _get_gates
                _gate_registry = _get_gates()
                _orig_check = _gate_registry.check_pre
                async def _gate_adapter(name: str, args: dict) -> bool | None:
                    try:
                        decision = _orig_check(name, args)
                        action = decision.get("action", "allow")
                        if action == "block":
                            logger.info("gate blocked tool=%s rule=%s reason=%s",
                                        name, decision.get("rule"), decision.get("reason"))
                            return False
                        if action == "ask":
                            approval_id = self._deps.permissions.request_approval(name, args)
                            approved = await self._deps.permissions.await_approval(approval_id, timeout=120.0)
                            if not approved:
                                logger.info("gate ask denied tool=%s", name)
                                return False
                    except Exception:
                        pass
                    return None
                self._middleware_chain.add_gate(_gate_adapter)
                _gates_wired = True
            except Exception:
                pass
        # Wire plugin hooks (phase 2) from _hook_system for middleware-compatible
        # events. The _hook_system.HookRegistry.invoke() dispatches to multiple
        # plugin handlers internally. We register it as a single pipeline handler
        # that delegates to the plugin registry.
        # Note: on_session_start/on_session_end have different kwargs than the
        # pipeline events (before_run/after_run) and are kept as explicit calls.
        _plugins_wired = False
        if not _plugins_wired:
            try:
                from harness.hooks import hook_registry as _plugin_registry
                _EVENT_MAP = {
                    "before_llm": "pre_llm_call",
                    "after_llm": "post_llm_call",
                    "before_tool": "pre_tool_call",
                    "after_tool": "post_tool_call",
                }
                for _pipe_ev, _plugin_ev in _EVENT_MAP.items():
                    reg_ref = _plugin_registry
                    async def _plugin_wrapper(reg=reg_ref, ev=_plugin_ev, **kw):
                        await reg.invoke(ev, **kw)
                    self._middleware_chain.add_plugin(_pipe_ev, _plugin_wrapper)
                _plugins_wired = True
            except Exception:
                pass

        self._interrupt: threading.Event = threading.Event()
        self._messages: list = []
        self.sandbox: Any | None = None
        self.session_id: str = ""
        self.model_override = model_override
        from harness.agent.iteration_budget import IterationBudget
        self.iteration_budget: IterationBudget = IterationBudget(max_tool_rounds)
        # 30-turn memory-nudge counter (per hermes pattern: a prompt-only
        # hint that fires every N turns; never mutates messages, so the
        # prompt cache stays valid). Set interval to 0 to disable.
        self._memory_nudge_interval: int = 30
        self._turns_since_memory: int = 0

        self._event_bus: EventBus = deps.event_bus
        self.context_compressor: Any = None

        if delegation is not None:
            self.delegation = delegation
        else:
            self.delegation = DelegationContext()

        self._reflection_count: int = 0
        self._reflection_per_tool: dict[str, int] = {}
        from harness.agent.reflexion_memory import ReflexionMemory
        self._reflexion_memory: ReflexionMemory = ReflexionMemory()
        self._last_reflection: str | None = None
        self._last_reflection_errors: list[tuple[str, str]] = []

        self._checkpoint_mgr: Any = None
        self._last_model: str = ""
        self._last_usage: dict = {}
        self._task_id: str = ""

        # C06: heartbeat + stale-detection support. ``_api_call_count``
        # is incremented at the start of each LLM call inside
        # ``run_stream``; ``_current_tool`` is set just before a tool
        # call is dispatched and cleared after the last tool result
        # arrives. Both fields are also derived on-demand by
        # ``get_activity_summary`` so the heartbeat (which runs in a
        # separate asyncio task) sees a consistent view.
        self._api_call_count: int = 0
        self._current_tool: str | None = None
        self._last_activity_desc: str = ""

        # Q6-C: per-run budget tracker. Set via ``set_budget_tracker``
        # from the orchestrator (or left as None for backward
        # compat). When set, ``_record_cost`` feeds it the per-LLM
        # call costs and the orchestrator can call
        # ``check_soft_cap()`` to drive the auto-throttle ladder.
        self._budget_tracker: Any = None

        self._hitl_gate: bool = False
        self._sequential_only: bool = False

        from harness.services.stuckness import InProcessAdapter
        self._stuckness: InProcessAdapter = InProcessAdapter()

        self._discovered_tool_names: set[str] = set()
        self._discovered_tool_schemas: list[dict[str, Any]] = []

        # system_prompt must be set regardless of params
        if system_prompt_override:
            self.system_prompt = system_prompt_override
        elif system_prompt:
            self.system_prompt = system_prompt
        else:
            tools_list = list(allowed_tools)
            self.system_prompt = build_system_prompt(mode=mode, toolsets=tools_list)

    def set_budget_tracker(self, tracker: Any) -> None:
        """Attach a per-run budget tracker (Q6-C)."""
        self._budget_tracker = tracker

    def set_hitl_gate(self, value: bool) -> None:
        self._hitl_gate = bool(value)
        try:
            self._deps.permissions.set_force_approval(bool(value))
        except Exception:
            pass

    def set_sequential_only(self, value: bool) -> None:
        self._sequential_only = bool(value)

    @property
    def hitl_gate_active(self) -> bool:
        return bool(getattr(self, "_hitl_gate", False))

    @property
    def sequential_only_active(self) -> bool:
        return bool(getattr(self, "_sequential_only", False))

    # ------------------------------------------------------------------ #
    # C06: heartbeat + stale-detection
    # ------------------------------------------------------------------ #

    def get_activity_summary(self) -> dict[str, Any]:
        """Return a small snapshot of the agent's current activity.

        C06 (per docs/2026-06-21-architecture-decision-tree.md#c06):
        the heartbeat running in ``delegate_task`` polls this method
        every 5 seconds to decide whether the child is making
        progress. The dict shape matches Hermes' ``get_activity_summary``
        so the two harnesses can share a future cross-harness monitor.

        Returns a fresh dict each call (callers should not mutate the
        agent's internal state from it). The ``current_tool`` field is
        ``None`` when the agent is between rounds (e.g. waiting for the
        next LLM response).

        All fields are safe to read from a different asyncio task —
        they are simple attribute reads with no internal locking. The
        only edge case is torn reads during a mid-update from
        ``run_stream``; the heartbeat treats that as "no progress" and
        bumps its stale counter, which is the right conservative
        behavior.
        """
        # Re-derive from _messages in case the explicit counters drifted
        # (e.g. resumed session). The explicit counters are still
        # authoritative for "is the agent currently inside a tool call
        # RIGHT NOW" — the message-list check is the fallback.
        api_call_count = self._api_call_count
        if not api_call_count and self._messages:
            api_call_count = sum(1 for m in self._messages if m.role == "assistant")
        current_tool = self._current_tool
        if current_tool is None and self._messages:
            # Fallback: look at the most recent assistant message that
            # had tool_calls. We don't bother searching the whole list
            # because only the latest one can be "in flight".
            for m in reversed(self._messages):
                if m.role == "assistant" and getattr(m, "tool_calls", None):
                    try:
                        current_tool = m.tool_calls[-1]["function"]["name"]
                    except (KeyError, IndexError, TypeError):
                        current_tool = None
                    break
        return {
            "current_tool": current_tool,
            "api_call_count": api_call_count,
            "max_iterations": self.max_tool_rounds,
            "last_activity_desc": self._last_activity_desc or "",
        }

    def _set_current_tool(self, name: str | None) -> None:
        """Internal: set the current tool name (called by ``run_stream``
        when dispatching a tool call). C06 uses this for in-tool vs
        idle stale thresholds.
        """
        self._current_tool = name
        if name:
            self._last_activity_desc = f"running tool {name}"

    def _bump_api_call(self) -> None:
        """Internal: increment the LLM-call counter (called at the
        start of each round in ``run_stream``). C06 uses this to
        detect iteration progress in the heartbeat.
        """
        self._api_call_count += 1
        if not self._last_activity_desc or self._last_activity_desc.startswith("running tool"):
            self._last_activity_desc = "calling LLM"

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def interrupt(self) -> None:
        self._interrupt.set()

    def _check_interrupt(self) -> None:
        if self._interrupt.is_set():
            self._interrupt.clear()
            raise RuntimeError("Agent execution interrupted")

    @property
    def llm(self) -> LLMRouter:
        return self._deps.llm

    @property
    def store(self) -> PersistentStore | None:
        return self._deps.store

    @property
    def mcp(self) -> MCPClient | None:
        return self._deps.mcp

    @mcp.setter
    def mcp(self, value: MCPClient | None) -> None:
        self._deps.mcp = value

    @property
    def permissions(self) -> PermissionManager:
        return self._deps.permissions

    def create_subagent(self, allowed_tools: list[str]) -> Agent:
        sub_permissions = PermissionManager(mode=self.mode)
        sub_permissions.set_allowed_tools(allowed_tools)
        sub_deps = AgentDependencies(
            llm=self._deps.llm,
            store=self._deps.store,
            permissions=sub_permissions,
            mcp=self._deps.mcp,
            event_bus=self._deps.event_bus,
        )
        system_prompt = build_subagent_prompt(goal="", context="", allowed_tools=allowed_tools)
        return Agent(
            deps=sub_deps, mode="auto",
            allowed_tools=allowed_tools, max_tool_rounds=5,
            system_prompt=system_prompt,
        )

    def _hooks(self):
        from harness.hooks import hooks as _hooks_fn
        return _hooks_fn()

    # ------------------------------------------------------------------ #
    # Unified typed emitter
    # ------------------------------------------------------------------ #

    async def _emit(self, event: StreamEvent) -> None:
        """Emit a typed StreamEvent to the event bus."""
        await self._event_bus.emit(event)

    # ------------------------------------------------------------------ #
    # Tool dispatch
    # ------------------------------------------------------------------ #

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        schemas = registry.list_specs(self._allowed_tools)
        if self._deps.mcp and self._deps.mcp.has_tools():
            mcp_allowed = [a for a in self._allowed_tools if a.startswith("mcp_")]
            for ot in self._deps.mcp.get_openai_tools():
                name = ot.get("function", ot).get("name", "")
                if not mcp_allowed:
                    schemas.append(ot)
                elif any(name.startswith(a) for a in mcp_allowed):
                    schemas.append(ot)
        return schemas

    def _add_message(
        self, role: str, content: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> None:
        msg = ChatMessage(
            role=role, content=content,
            tool_call_id=tool_call_id,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
        )
        self._messages.append(msg)
        if hasattr(self, '_recorder') and self._recorder is not None:
            try:
                if role == "user":
                    self._recorder.record_user_message(content or "")
                elif role == "assistant":
                    self._recorder.record_assistant_message(
                        content or "", tool_calls=tool_calls,
                    )
                elif role == "tool":
                    self._recorder.record_tool_result(
                        "", content or "", True, 0.0,
                    )
            except Exception:
                pass

    def _strip_orphan_tool_calls(self, messages: list) -> list:
        """Drop assistant tool_calls that have no matching tool response.

        The OpenAI/DeepSeek API rejects the next request with
        ``invalid_request_error: An assistant message with
        'tool_calls' must be followed by tool messages`` if a
        tool_calls row has no matching tool message. Belt-and-
        suspenders: even though ``_execute_with_recovery`` now
        always returns a string, a historical session resumed
        from a checkpoint could still carry orphans. Pattern
        adapted from langgraph's ``ToolNode.handle_tool_errors``
        and OpenHands' stuck-detector.
        """
        result: list = []
        for m in messages:
            tcs = getattr(m, "tool_calls", None) or []
            if getattr(m, "role", "") == "assistant" and tcs:
                ids = []
                for tc in tcs:
                    if isinstance(tc, dict):
                        tid = tc.get("id")
                    else:
                        tid = getattr(tc, "id", None)
                    if tid:
                        ids.append(tid)
                if not ids:
                    result.append(m)
                    continue
                kept = []
                for mm in messages:
                    if getattr(mm, "role", "") != "tool":
                        continue
                    tcid = getattr(mm, "tool_call_id", None)
                    if tcid and tcid in ids and tcid not in kept:
                        kept.append(tcid)
                if set(kept) != set(ids):
                    logger.warning(
                        "strip_orphan_tool_calls: dropping assistant turn with %d tool_calls (%d responses); ids missing=%s",
                        len(ids), len(kept), sorted(set(ids) - set(kept)),
                    )
                    continue
            result.append(m)
        return result

    def _make_dispatcher(self) -> ToolDispatcher:
        dispatcher = ToolDispatcher(
            event_bus=self._event_bus,
            permissions=self._deps.permissions,
            mode=self.mode,
            session_id=self.session_id,
            agent_id=self.delegation.subagent_id or '',
            delegation=self.delegation,
            deps=self._deps,
            allowed_tools=self._allowed_tools,
        )
        original_discovered = dispatcher._handle_discovered_tool
        def _on_discovered(name: str, spec: dict) -> None:
            if name not in self._discovered_tool_names:
                self._discovered_tool_names.add(name)
                self._discovered_tool_schemas.append(spec)
        dispatcher._handle_discovered_tool = _on_discovered
        return dispatcher

    def _drain_background_results(self) -> None:
        from harness.tools.delegate_task import drain_pending_results
        results = drain_pending_results()
        if not results:
            return
        summary_parts = []
        for sid, result in results.items():
            summary_parts.append(f"Background agent [{sid}] completed:\n{result[:500]}")
        self._add_message(role="user", content="\n\n---\n".join(summary_parts))

    # ------------------------------------------------------------------ #
    # Reflexion
    # ------------------------------------------------------------------ #

    def _is_error_result(self, result: str) -> bool:
        head = (result or "")[:200]
        return any(marker in head for marker in ERROR_MARKERS)

    def _should_reflect(self, tool_results: list[tuple[str, str, str]]) -> bool:
        errored_names = [name for _tid, name, result in tool_results if self._is_error_result(result)]
        if not errored_names:
            return False
        if self._reflection_count >= MAX_REFLECTIONS_PER_RUN:
            return False
        for name in errored_names:
            if self._reflection_per_tool.get(name, 0) >= MAX_REFLECTIONS_PER_TOOL:
                return False
        return True

    def _build_reflection(self, tool_results: list[tuple[str, str, str]]) -> str:
        for _tid, name, result in tool_results:
            if not self._is_error_result(result):
                continue
            saved = self._reflexion_memory.lookup(name, result)
            if saved:
                return f"## Self-critique (from prior memory)\n\nThis failure mode has been seen before. Prior advice:\n\n{saved}"
        lines = ["## Self-critique", "", "Some tool calls failed in the previous round. Before retrying, reflect briefly:", ""]
        for _tid, name, result in tool_results:
            if not self._is_error_result(result):
                continue
            snippet = result[:300] if len(result) > 300 else result
            lines.append(f"- **{name}** failed: `{snippet}`")
        lines.extend(["", "Consider:", "- Is the tool name correct?", "- Are the arguments valid and well-formed?", "- Did you check the tool's required inputs first?", "- Would a different approach avoid this error?"])
        return "\n".join(lines)

    def _record_reflection(self, tool_results: list[tuple[str, str, str]]) -> None:
        self._reflection_count += 1
        for _tid, name, result in tool_results:
            if self._is_error_result(result):
                self._reflection_per_tool[name] = self._reflection_per_tool.get(name, 0) + 1

    # ------------------------------------------------------------------ #
    # Per-tool post-call hook (P0 audit fix 2026-06-23)
    # ------------------------------------------------------------------ #
    _KG_REFRESH_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})

    async def _post_tool_call_hook(self, tool_name: str, result: str, tc: dict) -> None:
        """Fire-and-forget post-tool work.

        - Always: invokes any ``post_tool_call`` hooks the user
          registered (in-process callbacks or filesystem scripts).
        - For write/edit/patch tools: schedules a ``kg_refresh`` so the
          next ``codegraph_*`` query in this run sees the new symbol.
          The refresh is debounced to 60 s and never blocks the agent.
        """
        try:
            hooks = self._hooks()
            await hooks.invoke(
                "post_tool_call",
                tool_name=tool_name,
                result_preview=str(result)[:200],
                tool_call=tc,
            )
        except Exception as exc:
            logger.debug("post_tool_call hook failed (non-fatal): %s", exc)
        if tool_name not in self._KG_REFRESH_TOOLS:
            return
        try:
            import asyncio as _asyncio
            _asyncio.create_task(self._schedule_kg_refresh())
        except RuntimeError:
            pass

    async def _schedule_kg_refresh(self) -> None:
        """Debounced KG refresh. Idempotent across overlapping calls."""
        try:
            from harness.tools.kg_refresh_tool import KgRefreshTool
            tool = KgRefreshTool()
            await tool.run(force=False)
        except Exception as exc:
            logger.debug("kg_refresh after file edit failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Cost estimation for streaming path
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Recovery — retry / replan / degrade on tool failure
    # ------------------------------------------------------------------ #

    async def _execute_with_recovery(
        self, tc: dict[str, Any], llm_response_id: str, tool_call_index: int,
    ) -> str:
        """Execute a tool with configurable retry recovery.

        Respects ``self.recovery`` settings from Role YAML.

        Returns a string (success or error). **Never raises** — the
        OpenAI/DeepSeek API rejects the next request with
        ``invalid_request_error: An assistant message with
        'tool_calls' must be followed by tool messages`` if a
        tool_calls row has no matching tool response. Hard
        exceptions used to leak past this function and produce
        exactly that 400. We now trap every exception and return
        an error string so the caller's ``_add_message(role="tool",
        tool_call_id=tc["id"])`` always runs (LangGraph ToolNode
        pattern, see ``handle_tool_errors=True`` in their docs).
        """
        cfg = self.recovery
        tc_name = tc["function"]["name"]
        last_result: str | None = None
        max_attempts = 1 if not cfg.tool_retry_enabled else (1 + cfg.tool_max_retries)
        for attempt in range(max_attempts):
            self._check_interrupt()
            try:
                result = await self._dispatcher.execute(
                    tc, llm_response_id=llm_response_id, tool_call_index=tool_call_index,
                )
            except Exception as exc:
                # Hard exception (vs soft error string). Convert to
                # error result so the conversation stays well-formed.
                err = f"[tool {tc_name!r} raised {type(exc).__name__}: {exc}]"
                logger.warning(
                    "tool %s attempt %d/%d raised %s — converting to tool error",
                    tc_name, attempt + 1, max_attempts, type(exc).__name__,
                )
                result = err
            last_result = result
            is_error = self._is_error_result(result)
            if not is_error:
                return result
            if attempt < (max_attempts - 1):
                logger.info(
                    "Tool %s failed (attempt %d/%d), retrying in %.1fs",
                    tc_name, attempt + 1, max_attempts, cfg.tool_retry_delay,
                )
                try:
                    await asyncio.sleep(cfg.tool_retry_delay)
                except Exception:
                    pass
        # All attempts produced an error result. Optionally inject
        # a replan hint (the original "self._add_message" bug
        # path lives here, but it's safer to leave that to the
        # post-tool-hook so the LLM sees both: a real tool error
        # message AND a user-style replan hint).
        if cfg.replan_enabled and last_result is not None and self._is_error_result(last_result):
            self._add_message(
                role="user",
                content="[replan] %s Tool `%s` failed after %d attempts. %s" % (
                    cfg.replan_prompt, tc_name, max_attempts,
                    "The error was: %s" % last_result[:200],
                ),
            )
        return last_result or f"[tool {tc_name!r} returned no result]"

    async def _promote_l1(self) -> None:
        """Fire-and-forget L1 promotion: write L0 artifacts → KG nodes."""
        try:
            db = getattr(self._deps.store, "db", None) if self._deps.store else None
            if db and self.session_id:
                from harness.services.artifact_store import L1Indexer
                await L1Indexer(db).promote(self.session_id)
        except Exception as exc:
            logger.debug("L1 promotion failed: %s", exc)

    async def _record_cost_est(self, agent_id: str) -> None:
        if not self.session_id:
            return
        try:
            estimated_tokens = len(str([m.content for m in self._messages])) // 4
            if estimated_tokens <= 0:
                return

            # Try to get pricing, but don't fail if unavailable
            cost_est = 0.0
            model_name = getattr(self, "_last_model", "") or self.model_override or ""
            try:
                from harness.cost_tracker import get_pricing_cache
                cache = get_pricing_cache()
                rates = await cache.get_rate(model_name)
                if rates:
                    input_rate = rates.get("input", 0.0)
                    output_rate = rates.get("output", 0.0)
                    cost_est = (estimated_tokens / 1000) * (input_rate + output_rate)
            except Exception:
                pass  # Pricing unavailable, track tokens only

            # Always record token usage, even without cost
            await self._deps.store.db.execute(
                "INSERT INTO token_usage (session_id, model, input_tokens, output_tokens, estimated_cost_usd) VALUES ($1,$2,$3,$4,$5)",
                self.session_id, model_name, estimated_tokens, estimated_tokens, round(cost_est, 6),
            )
            await self._deps.store.db.execute(
                "UPDATE sessions SET total_tokens = total_tokens + $1, total_cost = total_cost + $2, updated_at = NOW() WHERE id = $3",
                estimated_tokens, round(cost_est, 6), self.session_id,
            )
        except Exception as e:
            print(f"DEBUG: _record_cost_est failed: {e}")

    async def _save_messages_to_db(self) -> None:
        if not self.session_id or not self._deps or not self._deps.store:
            return
        try:
            db = getattr(self._deps.store, "db", None)
            if not db:
                return
            for m in self._messages:
                role = getattr(m, "role", "") or ""
                content = getattr(m, "content", None) or ""
                tool_call_id = getattr(m, "tool_call_id", None)
                raw_tool_calls = getattr(m, "tool_calls", None)
                reasoning = getattr(m, "reasoning_content", None)
                if not role:
                    continue
                tc_json = json.dumps(raw_tool_calls) if raw_tool_calls else None
                await db.execute(
                    "INSERT INTO messages (session_id, role, content, tool_call_id, tool_calls, reasoning) "
                    "VALUES ($1, $2, to_jsonb($3::text), $4, $5::jsonb, $6)",
                    self.session_id, role, content, tool_call_id, tc_json, reasoning,
                )
        except Exception as e:
            logger.debug("Failed to save messages to DB: %s", e)

    async def _feed_budget_tracker(self) -> None:
        tracker = getattr(self, "_budget_tracker", None)
        if tracker is None:
            return
        try:
            estimated_tokens = max(
                1, len(str([m.content for m in self._messages])) // 4,
            )
            model_name = (
                getattr(self, "_last_model", "")
                or self.model_override
                or "default"
            )
            await tracker.add_cost(
                model=model_name,
                input_tokens=estimated_tokens,
                output_tokens=estimated_tokens,
            )
            await tracker.observe(
                agent=self,
                llm_router=getattr(self, "_deps", None)
                and getattr(self._deps, "llm", None),
                event_bus=getattr(self, "_event_bus", None),
            )
        except Exception as exc:
            logger.debug(
                "budget tracker feed failed: %s", exc,
            )

    # ------------------------------------------------------------------ #
    # run() — thin non-streaming wrapper over run_stream()
    # ------------------------------------------------------------------ #

    async def run(self, user_input: str, model: str | None = None) -> str:
        import logging
        _log = logging.getLogger(__name__)
        _log.info("Agent.run ENTERED: session=%s model=%s input=%s", self.session_id, model, user_input[:50])
        agent_id = str(uuid.uuid4())
        self._recorder = None
        try:
            from harness.recording import SessionRecorder
            self._recorder = SessionRecorder(
                self.session_id or agent_id,
                metadata={"mode": self.mode, "agent_id": agent_id, "user_input": user_input[:200]},
            )
        except Exception:
            pass
        hooks = self._hooks()
        try:
            await hooks.invoke("on_session_start", agent_id=agent_id, mode=self.mode, input=user_input[:200])
        except Exception:
            pass
        await self._middleware_chain.on_before_run(user_input)
        final_text: list[str] = []
        completed = False
        try:
            async for event in self.run_stream(user_input):
                if isinstance(event, AgentCompleted):
                    final_text.append(event.output_preview)
                    completed = True
                elif isinstance(event, TokenGenerated):
                    final_text.append(event.content)
            result = "".join(final_text)
            if not completed and result:
                result = "Max tool rounds reached without final response."
            await self._middleware_chain.on_after_run(result, None)
            await hooks.invoke("on_session_end", agent_id=agent_id, output=result[:200], rounds=0)
            self._save_reflections(was_successful=completed)
            if self.session_id:
                await self._promote_l1()
            if self._recorder:
                self._recorder.close(status="completed" if completed else "failed")
            return result
        except Exception as e:
            self._save_reflections(was_successful=False)
            await self._middleware_chain.on_after_run(None, str(e))
            await hooks.invoke("on_session_end", agent_id=agent_id, error=str(e)[:200])
            if self._recorder:
                self._recorder.close(status="failed")
            raise

    async def _init_messages(self, user_input: str) -> None:
        if not self.system_prompt:
            from harness.prompt_builder import build_system_prompt
            self.system_prompt = build_system_prompt(
                mode=self.mode, toolsets=self._allowed_tools,
            )
        self._messages = [ChatMessage(role="system", content=self.system_prompt)]
        if self._deps.store:
            context = await self._deps.store.get_recent_context()
            if context:
                self._messages.append(ChatMessage(role="system", content=f"Relevant context:\n{context}"))
        self._add_message(role="user", content=user_input)

    def _init_checkpoint_mgr(self) -> None:
        db = getattr(self._deps.store, "db", None) if self._deps.store else None
        if db is None:
            self._checkpoint_mgr = None
            return
        from harness.checkpoint import CheckpointManager
        self._checkpoint_mgr = CheckpointManager(db, self.session_id)

    def _save_reflections(self, was_successful: bool) -> None:
        # Q7-B: write the run's tool-call history to L0. This is the
        # raw artifact store; the L1 indexer (follow-up) promotes
        # interesting facts. Without L0 writes, the system has no
        # institutional memory of what the agent actually did.
        if self._deps and getattr(self._deps, "store", None) is not None:
            try:
                from harness.services.artifact_store import (
                    ArtifactStore, derive_l0_items_from_messages,
                )
                store_db = getattr(self._deps.store, "db", None)
                if store_db is not None and self.session_id:
                    items = derive_l0_items_from_messages(
                        self._messages,
                        last_reflection=self._last_reflection,
                    )
                    if items:
                        # Fire-and-forget: create a task so the L0
                        # write doesn't block the return path. A
                        # transient DB failure here just means the
                        # next run starts without L0 history — the
                        # agent's `memory` tool writes its own L2
                        # reflection, so the *lesson* is still
                        # captured even if the *receipts* aren't.
                        import asyncio
                        async def _write_l0() -> int:
                            try:
                                return await ArtifactStore(store_db).write_batch(
                                    self.session_id, items,
                                )
                            except Exception as exc:
                                logger.warning(
                                    "L0 write failed session=%s: %s",
                                    self.session_id, exc,
                                )
                                return 0
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(_write_l0())
                            else:
                                loop.run_until_complete(_write_l0())
                        except RuntimeError:
                            # No running loop (called from sync path)
                            pass
            except Exception as exc:
                logger.debug("L0 write setup failed: %s", exc)

        if not self._last_reflection or not self._last_reflection_errors:
            return
        for tool_name, error_result in self._last_reflection_errors:
            try:
                self._reflexion_memory.save(tool_name=tool_name, error=error_result, reflection=self._last_reflection, was_successful=was_successful)
            except Exception as exc:
                logger.debug("ReflexionMemory.save failed: %s", exc)

# ------------------------------------------------------------------ #
# run_stream() — async generator for SSE
    # ------------------------------------------------------------------ #

    async def run_stream(self, user_input: str) -> AsyncGenerator[StreamEvent, None]:
        from harness.agent.turn_context import build_turn_context, emit_startup_event
        mgr = __import__("harness.context", fromlist=["manager"]).manager
        agent_id = str(uuid.uuid4())
        async with mgr.scope(agent_id=agent_id):
            ctx = await build_turn_context(self, user_input, agent_id)
            yield emit_startup_event(self, ctx)
            schemas = self._get_tool_schemas()
            for round_num in range(ctx.resume_turn, self.max_tool_rounds):
                if not self.iteration_budget.consume():
                    logger.info(
                        "run_stream: iteration budget exhausted at round %d", round_num,
                    )
                    break
                self._check_interrupt()
                full_content = ""
                full_reasoning = ""
                current_tool_calls: dict[int, dict[str, Any]] = {}
                tool_results_in_round: list[tuple[str, str, str]] = []
                llm_call_id = str(uuid.uuid4())
                # C06: bump the LLM-call counter at the start of each
                # round so the heartbeat can detect iteration progress
                # (vs being stuck between rounds).
                self._bump_api_call()
                await self._emit(RoundStarted(
                    round=round_num, message_count=len(self._messages),
                ))
                # Wire of harness.compaction (C00-C-2). Pattern from
                # LangChain anatomy + OpenHarness: keep the message
                # list small with a free pre-pass before each LLM
                # call, then react to a "too long" error by dropping
                # the oldest third of non-system messages and retrying
                # once. The free pre-pass is what keeps us off the
                # reactive path 95% of the time.
                from harness.compaction import (
                    estimate_tokens,
                    is_prompt_too_long_error,
                    micro_compact,
                    reactive_compact,
                )
                _approx_tokens = sum(
                    estimate_tokens(str(getattr(m, "content", "") or "")) for m in self._messages
                )
                if len(self._messages) > 30 or _approx_tokens > 80_000:
                    self._messages = micro_compact(self._messages, max_turns=20)
                self._messages = self._strip_orphan_tool_calls(self._messages)
                # Middleware: on_before_llm
                try:
                    mutated = await self._middleware_chain.on_before_llm(self._messages, round_num)
                    if mutated is not None:
                        self._messages = mutated
                except Exception as exc:
                    logger.debug("middleware on_before_llm failed: %s", exc)
                stuck_warnings: list = getattr(self, "_stuckness_warnings", [])
                if stuck_warnings:
                    from harness.llm import ChatMessage
                    self._messages.append(ChatMessage(
                        role="user", content="\n\n".join(stuck_warnings),
                    ))
                    self._stuckness_warnings = []
                compact_retry_done = False
                _llm_model = getattr(self, "model_override", None) or "default"
                await self._event_bus.emit(LLMCallStarted(
                    call_id=llm_call_id, model=_llm_model, round=round_num,
                    session_id=self.session_id,
                ))
                while True:
                    try:
                        chunk_iter = self._deps.llm.chat_stream(
                            messages=self._messages, tools=schemas if schemas else None,
                        )
                        async for chunk in chunk_iter:
                            # process chunk below
                            delta = chunk.choices[0].delta if chunk.choices else None
                            # Set _last_model from model_override if not already set
                            if not self._last_model and self.model_override:
                                self._last_model = self.model_override
                            if not delta:
                                continue
                            # Handle both dict (OpenCode Zen relay) and SimpleNamespace (OpenAI SDK) deltas
                            def _delta_get(d, key, default=None):
                                if isinstance(d, dict):
                                    return d.get(key, default)
                                return getattr(d, key, default)
                            dc = _delta_get(delta, "content")
                            if dc:
                                full_content += dc
                                tok = TokenGenerated(agent_id=agent_id, content=dc, session_id=self.session_id)
                                await self._event_bus.emit(tok)
                                yield tok
                            rc = _delta_get(delta, "reasoning_content")
                            if rc:
                                full_reasoning += rc
                                reas = ReasoningGenerated(agent_id=agent_id, content=rc, session_id=self.session_id)
                                await self._event_bus.emit(reas)
                                yield reas
                            tcs = _delta_get(delta, "tool_calls")
                            if tcs:
                                print(f"DEBUG: Got {len(tcs)} tool_calls in delta")
                                for tc in tcs:
                                    idx = tc.index
                                    if idx not in current_tool_calls:
                                        current_tool_calls[idx] = {"id": tc.id or "", "function": {"name": "", "arguments": ""}}
                                    if tc.id:
                                        current_tool_calls[idx]["id"] = tc.id
                                    if tc.function:
                                        if tc.function.name:
                                            current_tool_calls[idx]["function"]["name"] = tc.function.name
                                        if tc.function.arguments:
                                            current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments
                        # Stream finished normally — break the retry loop
                        break
                    except Exception as llm_exc:
                        # F24: classify the LLM error and surface it as an
                        # ErrorEvent so the activity feed can show
                        # "rate limit" / "context overflow" / "auth" with
                        # the classified category and recovery hint.
                        try:
                            from harness.tools.error_classifier import classify_error as _classify
                            _cls = _classify(str(llm_exc) or type(llm_exc).__name__)
                            await self._event_bus.emit(ErrorEvent(
                                message=str(llm_exc)[:300],
                                recoverable=bool(_cls.get("retryable")),
                                session_id=self.session_id,
                                agent_id=agent_id,
                                category=str(_cls.get("category") or "unknown"),
                            ))
                        except Exception:
                            pass
                        if compact_retry_done or not is_prompt_too_long_error(llm_exc):
                            raise
                        compacted = reactive_compact(self._messages, llm_exc)
                        if compacted is None:
                            raise
                        self._messages = compacted
                        compact_retry_done = True
                        full_content = ""
                        full_reasoning = ""
                        current_tool_calls = {}
                        tool_results_in_round = []
                        llm_call_id = str(uuid.uuid4())
                        await self._emit(RoundStarted(
                            round=round_num, message_count=len(self._messages),
                        ))
                        # retry the stream
                await self._feed_budget_tracker()
                _est_prompt = sum(len(str(getattr(m, "content", "") or "")) for m in self._messages) // 4
                _est_completion = len(full_content) // 4
                await self._event_bus.emit(LLMCallCompleted(
                    call_id=llm_call_id, model=_llm_model, round=round_num,
                    prompt_tokens=_est_prompt, completion_tokens=_est_completion,
                    total_tokens=_est_prompt + _est_completion, session_id=self.session_id,
                ))
                if not current_tool_calls:
                    self._add_message(role="assistant", content=full_content, reasoning_content=full_reasoning)
                    if self._deps.store:
                        await self._deps.store.store_interaction(user_input, full_content)
                    await self._record_cost_est(agent_id)
                    await self._save_messages_to_db()
                    ev_done = AgentCompleted(
                        agent_id=agent_id, output_preview=full_content[:200],
                        rounds=round_num + 1, cancelled=False,
                    )
                    await self._event_bus.emit(ev_done)
                    yield ev_done
                    return
                sorted_indices = sorted(current_tool_calls.keys())
                tool_calls_list = [
                    {"id": current_tool_calls[i]["id"], "type": "function", "function": current_tool_calls[i]["function"]}
                    for i in sorted_indices
                ]

                # Middleware: on_after_llm
                try:
                    mw_result = await self._middleware_chain.on_after_llm(tool_calls_list, round_num)
                    if mw_result is not None:
                        mw_calls, mw_forced_text = mw_result
                        if mw_forced_text:
                            tool_calls_list = []
                            full_content = full_content or mw_forced_text
                            logger.info("Middleware forced text answer: %s", mw_forced_text[:100])
                        elif mw_calls is not None:
                            tool_calls_list = mw_calls
                except Exception as exc:
                    logger.debug("middleware on_after_llm failed: %s", exc)

                self._add_message(role="assistant", content=full_content or None, tool_calls=tool_calls_list, reasoning_content=full_reasoning)

                stuck_verdict = self._stuckness.observe_after_llm(tool_calls_list)
                if stuck_verdict.severity == "hard":
                    logger.warning(
                        "Stuckness detector: pattern=%s msg=%s",
                        stuck_verdict.pattern, stuck_verdict.message[:100],
                    )
                    ev_hard = AgentCompleted(
                        agent_id=agent_id,
                        output_preview=stuck_verdict.message[:200],
                        rounds=round_num + 1,
                        cancelled=True,
                    )
                    await self._event_bus.emit(ev_hard)
                    yield ev_hard
                    return
                if stuck_verdict.severity == "warning":
                    self._stuckness_warnings = getattr(
                        self, "_stuckness_warnings", [],
                    )
                    self._stuckness_warnings.append(stuck_verdict.message)

                # Concurrent tool execution (Hermes pattern):
                # - Single tool: execute directly
                # - Multiple non-interactive tools: execute concurrently
                # - Interactive tools (question, clarify, computer_use): force sequential
                INTERACTIVE_TOOLS = {"question", "clarify", "computer_use", "vision_analyze"}
                has_interactive = any(
                    tc["function"]["name"] in INTERACTIVE_TOOLS
                    for tc in tool_calls_list
                )
                
                if len(tool_calls_list) == 1 or has_interactive:
                    # Sequential execution
                    for idx, tc in enumerate(tool_calls_list):
                        self._check_interrupt()
                        tc_name = tc["function"]["name"]
                        tc_args = tc["function"].get("arguments", {})

                        # Middleware: on_before_tool
                        allowed = await self._middleware_chain.on_before_tool(tc_name, tc_args)
                        if not allowed:
                            result = f"[Blocked by middleware: tool {tc_name}]"
                            self._add_message(role="tool", content=result, tool_call_id=tc["id"])
                            tool_results_in_round.append((tc["id"], tc_name, result))
                            continue

                        # C06: stamp the current tool so the heartbeat
                        # knows the agent is "in a tool" (long stale
                        # threshold) vs "between tools" (short threshold).
                        self._set_current_tool(tc_name)
                        ev_started = ToolExecutionStarted(
                            tool_name=tc_name, tool_input=str(tc_args)[:200],
                            trace_id=f"{llm_call_id}-{idx}", agent_id=agent_id, session_id=self.session_id,
                            llm_response_id=llm_call_id,
                        )
                        await self._event_bus.emit(ev_started)
                        yield ev_started
                        result = await self._execute_with_recovery(tc, llm_call_id, idx)

                        # Middleware: on_after_tool
                        try:
                            mw_result = await self._middleware_chain.on_after_tool(tc_name, result)
                            if mw_result is not None:
                                result = mw_result
                        except Exception as exc:
                            logger.debug("middleware on_after_tool failed: %s", exc)

                        try:
                            self._stuckness.observe_after_tool(tc_name, result)
                        except Exception as exc:
                            logger.debug("stuckness after_tool failed: %s", exc)

                        self._add_message(role="tool", content=result, tool_call_id=tc["id"])
                        is_error = self._is_error_result(result)
                        ev_completed = ToolExecutionCompleted(
                            tool_name=tc_name, output_preview=str(result)[:200],
                            success=not is_error, trace_id=f"{llm_call_id}-{idx}",
                            agent_id=agent_id, session_id=self.session_id,
                            llm_response_id=llm_call_id,
                            is_error=is_error,
                        )
                        await self._event_bus.emit(ev_completed)
                        yield ev_completed
                        await self._post_tool_call_hook(tc_name, result, tc)
                        tool_results_in_round.append((tc["id"], tc_name, result))
                else:
                    # Concurrent execution (Hermes pattern)
                    results_map = {}
                    # C06: stamp "in tool" for the first tool in the
                    # concurrent batch. The heartbeat polls coarsely so
                    # the exact tool name doesn't matter much; "some
                    # tool is running" is enough.
                    if tool_calls_list:
                        self._set_current_tool(tool_calls_list[0]["function"]["name"])

                    async def exec_one(idx, tc):
                        self._check_interrupt()
                        tc_name = tc["function"]["name"]
                        tc_args = tc["function"].get("arguments", {})

                        # Middleware: on_before_tool
                        allowed = await self._middleware_chain.on_before_tool(tc_name, tc_args)
                        if not allowed:
                            result = f"[Blocked by middleware: tool {tc_name}]"
                            self._add_message(role="tool", content=result, tool_call_id=tc["id"])
                            results_map[idx] = (tc["id"], tc_name, result)
                            return

                        # C06: refresh the current tool name per
                        # concurrent call so a tool transition is
                        # visible to the heartbeat.
                        self._set_current_tool(tc_name)
                        ev_started_c = ToolExecutionStarted(
                            tool_name=tc_name, tool_input=str(tc_args)[:200],
                            trace_id=f"{llm_call_id}-{idx}", agent_id=agent_id, session_id=self.session_id,
                            llm_response_id=llm_call_id,
                        )
                        await self._event_bus.emit(ev_started_c)
                        yield ev_started_c
                        result = await self._execute_with_recovery(tc, llm_call_id, idx)

                        # Middleware: on_after_tool
                        try:
                            mw_result = await self._middleware_chain.on_after_tool(tc_name, result)
                            if mw_result is not None:
                                result = mw_result
                        except Exception as exc:
                            logger.debug("middleware on_after_tool failed: %s", exc)

                        # C1: feed tool result to stuckness detector.
                        try:
                            self._stuckness.observe_after_tool(tc_name, result)
                        except Exception as exc:
                            logger.debug("stuckness after_tool failed: %s", exc)

                        self._add_message(role="tool", content=result, tool_call_id=tc["id"])
                        is_error = self._is_error_result(result)
                        ev_completed_c = ToolExecutionCompleted(
                            tool_name=tc_name, output_preview=str(result)[:200],
                            success=not is_error, trace_id=f"{llm_call_id}-{idx}",
                            agent_id=agent_id, session_id=self.session_id,
                            llm_response_id=llm_call_id,
                            is_error=is_error,
                        )
                        await self._event_bus.emit(ev_completed_c)
                        yield ev_completed_c
                        # P0 audit fix 2026-06-23: per-edit KG refresh.
                        await self._post_tool_call_hook(tc_name, result, tc)
                        results_map[idx] = (tc["id"], tc_name, result)
                    
                    # Run all tools (async generators can't use as_completed,
                    # so we run them sequentially but still yield events)
                    for idx, tc in enumerate(tool_calls_list):
                        async for event in exec_one(idx, tc):
                            yield event
                    # Refund the iteration for ``execute_code`` rounds:
                    # programmatic tool calling does not require a fresh
                    # LLM decision on every call, so consuming budget for
                    # the round would prematurely throttle long-running
                    # code-execution flows. Pattern from
                    # hermes-agent `agent/conversation_loop.py:4122`.
                    if (
                        tool_calls_list
                        and all(
                            (tc.get("function", {}) or {}).get("name") == "execute_code"
                            for tc in tool_calls_list
                        )
                    ):
                        self.iteration_budget.refund()
                # Middleware: on_end_of_round
                try:
                    await self._middleware_chain.on_end_of_round(round_num)
                except Exception as exc:
                    logger.debug("middleware on_end_of_round failed: %s", exc)
                try:
                    self._stuckness.observe_end_of_round()
                except Exception as exc:
                    logger.debug("stuckness end_of_round failed: %s", exc)

                # C06: clear the current-tool marker between rounds so
                # the heartbeat knows the agent is now "between rounds"
                # (waiting for the next LLM response) and applies the
                # short idle stale threshold.
                self._set_current_tool(None)
                # F22: emit RoundCompleted so the UI can pair it with the
                # RoundStarted event and show round-by-round progress.
                # Without this, the dashboard never knows when a round
                # actually finished — the next RoundStarted just appears
                # with no "completed" marker in between.
                ev_round_done = RoundCompleted(
                    round=round_num,
                    tool_calls=len(tool_results_in_round),
                    session_id=self.session_id,
                )
                await self._event_bus.emit(ev_round_done)
                yield ev_round_done
                if self._should_reflect(tool_results_in_round):
                    reflection = self._build_reflection(tool_results_in_round)
                    self._add_message(role="user", content=reflection)
                    self._record_reflection(tool_results_in_round)
                    self._last_reflection = reflection
                    self._last_reflection_errors = [
                        (name, result) for _tid, name, result in tool_results_in_round if self._is_error_result(result)
                    ]
                    await self._emit(ReflexionInjected(
                        round=round_num, tool_count=len(tool_results_in_round),
                        reflection_count=self._reflection_count,
                    ))
                if self._checkpoint_mgr is None:
                    self._init_checkpoint_mgr()
                if self._checkpoint_mgr:
                    try:
                        msgs = [
                            {"role": m.role, "content": m.content or ""}
                            for m in self._messages
                        ]
                        await self._checkpoint_mgr.checkpoint(
                            "turn_complete", messages_snapshot=msgs, turn_count=round_num + 1,
                        )
                    except Exception as ckpt_exc:
                        logger.warning("Checkpoint failed: %s", ckpt_exc)
                if self.context_compressor:
                    prompt_tokens_est = len(str([m.content for m in self._messages])) // 4
                    if self.context_compressor.should_compress(prompt_tokens_est):
                        try:
                            dict_messages = [{"role": m.role, "content": m.content} for m in self._messages]
                            compressed = await self.context_compressor.compress(
                                dict_messages, session_id=self.session_id,
                            )
                            self._messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in compressed]
                            logger.info("Stream context compressed: %d -> %d messages (trigger: %d est. tokens)",
                                        len(dict_messages), len(compressed), prompt_tokens_est)
                        except Exception as exc:
                            logger.warning("Stream context compression failed: %s", exc)
            await self._record_cost_est(agent_id)
            await self._save_messages_to_db()
            from harness.agent.turn_finalizer import finalize_turn
            finalizer = finalize_turn(
                self,
                agent_id=agent_id,
                rounds_completed=round_num + 1,
                cancelled=False,
                max_rounds_reached=True,
            )
            ev_max = finalizer.agent_completed_event
            if ev_max is not None:
                await self._event_bus.emit(ev_max)
                yield ev_max
            if finalizer.cleanup_errors:
                logger.warning(
                    "run_stream: turn finalizer recorded %d cleanup error(s): %s",
                    len(finalizer.cleanup_errors),
                    [label for label, _ in finalizer.cleanup_errors],
                )
