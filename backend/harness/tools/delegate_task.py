"""Subagent delegation tool. Spawn, fan-out, and background subagents."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from harness.context import manager as scope_manager
from harness.delegation import DelegationContext
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry
from harness.tools.toolsets import resolve_toolsets, toolsets_for_mode

# Import extracted module components
from harness.tools.budget import (
    BudgetAction,
    BudgetEnforcer,
    TokenUsage,
    get_budget_policy,
    get_token_ledger,
)
from harness.tools.circuit_breaker import get_circuit_breakers
from harness.tools.cancellation import get_cancellation_tree
from harness.tools.collect_tool import CollectResultsTool
from harness.tools.subagent import (
    DEFAULT_MAX_CONCURRENT_CHILDREN,
    CHILD_TIMEOUT_SECONDS,
    DELEGATE_BLOCKED_TOOLS,
    SubagentResult,
    _AgentResult,
    _active_subagents,
    _active_subagents_lock,
    _pending_results,
    _pending_results_lock,
    _build_child_system_prompt,
    _build_child_progress_callback,
    _expand_parent_toolsets,
    _preserve_parent_mcp_toolsets,
    _strip_blocked_tools,
    _call_child_with_enhancements,
    stream_fan_out,
    _persist_delegation,
    cancel_subagent,
    collect_results,
    active_subagents,
    drain_pending_results,
    interrupt_subagent,
    is_spawn_paused,
    set_spawn_paused,
    MAX_SPAWN_DEPTH_CAP,
)
from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C02 helpers — built on the C00 wirings. These are private to the
# delegate_task tool but live at module scope so the tests can hit them
# directly (the wiring is the test surface).
# ---------------------------------------------------------------------------


async def _collect_evidence_async(session_id: str) -> list:
    """Read L0 artifacts for a subagent's session and return EvidenceClaims.

    F6 deepening: the writer side (harness.evidence.capture_evidence)
    runs after every tool call. By the time the subagent returns,
    ``agent_artifacts`` is full of bash scripts, browser screenshots,
    and tool results. This function translates that table into
    :class:`EvidenceClaim` objects the parent agent (and the
    dashboard) can verify before acting on the subagent's output.
    """
    if not session_id:
        return []
    try:
        from harness.memory.db_context import get_db
        from harness.tools.subagent import EvidenceClaim
        db = get_db()
        if not db or not getattr(db, "_pool", None):
            return []
        rows = await db.fetch(
            "SELECT kind, tool_name, payload::text, path "
            "FROM agent_artifacts WHERE session_id = $1 "
            "AND kind IN ('tool_call', 'tool_result', 'screenshot') "
            "ORDER BY id ASC",
            session_id,
        )
    except Exception as exc:
        logger.debug("_collect_evidence_async failed: %s", exc)
        return []
    claims = []
    for r in rows or []:
        tool = r["tool_name"] or "tool"
        kind = r["kind"] or ""
        path = r["path"] or ""
        if kind == "tool_call":
            claim = f"Subagent invoked {tool}"
        elif kind == "tool_result":
            claim = f"Subagent received result from {tool}"
        elif kind == "screenshot":
            claim = f"Subagent captured screenshot {path}"
        else:
            claim = f"Subagent artifact ({kind})"
        claims.append(EvidenceClaim(
            claim=claim,
            artifact_path=path or f"agent_artifacts://{session_id}/{kind}",
            mime="text/plain" if kind != "screenshot" else "image/png",
            captured_at=time.time(),
        ))
    return claims


def _apply_success_detector(output: Any, success: bool) -> str:
    """Run the RunSuccessDetector on a subagent's output.

    C02 + F12 deepening: the orchestrator's ``_derive_run_success``
    was rewired to use :class:`RunSuccessDetector` in C00-C-5. The
    subagent tool uses the same detector so a subagent that "succeeds"
    by string match but the detector says flaky is correctly
    classified here. Returns the detector name (e.g. ``"string_match"``)
    or empty string when the detector was bypassed.
    """
    if output is None and success:
        return ""
    try:
        from harness.services.run_success_detector import RunSuccessDetector
        detector = RunSuccessDetector()
        is_failure, _reason = detector.detect(output)
        if is_failure and success:
            # The detector caught a failure that the success path
            # missed (e.g. "max tool rounds" hidden in a long
            # response). Caller will see the detector_name in the
            # SubagentResult and can react.
            return detector.strategies[0].name if detector.strategies else "string_match"
    except Exception as exc:
        logger.debug("_apply_success_detector failed: %s", exc)
    return ""


def _record_model_outcome(model: str, success: bool, duration_ms: float, error_type: str = "") -> None:
    """F15/CC6 deepening: feed the subagent's model outcome into the
    shared provider-quality tracker so the router can prefer
    higher-quality models for the next subagent. C00-C-3 added the
    tracker; this is the subagent-side call site.
    """
    if not model:
        return
    try:
        from harness.api.state import get_llm
        router = get_llm()
        if router is not None and hasattr(router, "record_provider_outcome"):
            router.record_provider_outcome(
                model=model, success=success,
                latency_ms=duration_ms, error_type=error_type,
            )
    except Exception as exc:
        logger.debug("_record_model_outcome failed: %s", exc)


def role_for_session(tool: "DelegateTaskTool", toolsets: list[str] | None) -> str:
    """Pick the effective role for a spawned subagent.

    Mirrors the role-resolution in ``DelegateTaskTool._run_single_enhanced``:
    if the subagent is given the ``delegate_task`` toolset and is
    within the depth cap, it stays an orchestrator; otherwise it
    is a leaf (execution-only). The default is ``"chat"`` because
    the recipe registry expects one of the known roles.
    """
    if toolsets and "delegate_task" in toolsets:
        depth = tool.delegation.depth + 1
        if depth <= tool._max_spawn_depth:
            return "orchestrator"
    return "leaf"


class DelegateTaskTool(BaseTool):
    """Spawn subagents in Sync, Fan-Out, or Background mode.

    Three lifecycle modes:
      - Sync (default):     Parent blocks until subagent returns result.
      - Fan-Out (batch):    Parent spawns N tasks, calls collect_results() to wait.
      - Background:         Parent gets subagent_id immediately, polls later.
    """

    name = "delegate_task"
    description = (
        "Spawn one or more subagents to work on tasks in isolated contexts. "
        "Each subagent gets a fresh conversation, restricted tools, and its "
        "own session. Three modes: Sync (goal, blocks until done), "
        "Fan-Out (tasks array, spawns N in parallel, collect later), "
        "Background (run_in_background=true, returns subagent_id immediately)."
    )

    def __init__(self, agent_factory: Callable | None = None):
        super().__init__()
        self._agent_factory = agent_factory
        self._backend_factory = None
        self._session_id = ""
        self._max_children = DEFAULT_MAX_CONCURRENT_CHILDREN
        self._max_spawn_depth = MAX_SPAWN_DEPTH_CAP
        self.delegation: DelegationContext = DelegationContext()

    def _get_agent_factory(self) -> Callable | None:
        """Get agent factory, falling back to global/app.state if not set."""
        if self._agent_factory:
            return self._agent_factory
        # Try global state first
        from harness.api.state import get_agent_factory
        af = get_agent_factory()
        if af:
            return af
        # Try app.state (set during lifespan)
        try:
            from api.main import app
            return getattr(app.state, 'agent_factory', None)
        except Exception:
            return None

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Single task for one subagent (Sync mode)",
                    },
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": f"Batch mode: up to {self._max_children} parallel tasks (Fan-Out)",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context prepended to the subagent's goal",
                    },
                    "toolsets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Toolsets the subagent may use (default: read)",
                    },
                    "role": {
                        "type": "string",
                        "enum": ["leaf", "orchestrator"],
                        "description": "'leaf' (default) cannot delegate further. 'orchestrator' retains delegate_task.",
                    },
                    "run_in_background": {
                        "type": "boolean",
                        "description": "If true, return subagent_id immediately. Parent calls collect_results later.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Override the model used for this subagent (e.g. 'haiku' for cheap tasks)",
                    },
                    "mcp_servers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "MCP server names to grant to this subagent (allow-list, not inherited)",
                    },
                    "agent": {
                        "type": "string",
                        "description": "Agent definition name (e.g. 'explore', 'fix', 'verify'). Uses agent .md file from harness/agents/ or ~/.testai/agents/",
                    },
                    "team_id": {
                        "type": "string",
                        "description": "C02: optional team id. If set, the new subagent is added to the team (role=member by default; role=lead if is_team_lead=true). The subagent's toolset is augmented with the appropriate team_* tools.",
                    },
                    "is_team_lead": {
                        "type": "boolean",
                        "default": False,
                        "description": "C02: when team_id is set, set this true to make the new subagent the team's lead. Lead gets the full team_* toolset (create/messaging/dissolve).",
                    },
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        goal = kwargs.get("goal", "")
        tasks = kwargs.get("tasks", None)
        context = kwargs.get("context", "")
        toolsets = kwargs.get("toolsets", None) or ["read", "intelligence"]
        role = kwargs.get("role", "leaf")
        run_in_background = kwargs.get("run_in_background", False)
        model_override = kwargs.get("model", None)
        mcp_servers = kwargs.get("mcp_servers", None)
        agent_name = kwargs.get("agent", None)
        max_tool_rounds = kwargs.get("max_tool_rounds", None)
        # C02: when team_id is set, the spawned subagent is added
        # to the team and gets the appropriate ``team_*`` toolset
        # (lead = full surface, member = read+reply). When the
        # subagent finishes, its member status is updated to
        # ``done`` so the system can auto-dissolve the team.
        team_id = kwargs.get("team_id", "") or ""
        is_team_lead = bool(kwargs.get("is_team_lead", False))

        if not goal and not tasks:
            return ToolResult(success=False, output="Provide goal or tasks", error="missing_input")

        if is_spawn_paused():
            return ToolResult(success=False, output="Subagent spawning is paused", error="spawn_paused")

        agent_factory = self._get_agent_factory()
        if not agent_factory:
            return ToolResult(success=False, output="Agent factory not configured", error="no_factory")

        # Resolve toolsets: intersection with parent, strip blocked, retain MCP
        parent_toolsets = self._resolve_parent_toolsets()
        expanded_parent = _expand_parent_toolsets(parent_toolsets)
        resolved = [t for t in resolve_toolsets(toolsets) if t in expanded_parent]
        resolved = _strip_blocked_tools(resolved)
        if mcp_servers:
            for ms in mcp_servers:
                if ms not in resolved:
                    resolved.append(ms)
        else:
            resolved = _preserve_parent_mcp_toolsets(resolved, parent_toolsets)
        if role == "orchestrator" and "delegate_task" not in resolved:
            resolved.append("delegate_task")
        # Scope tools by role: leaf workers get execution-only tools
        if role == "leaf":
            allowed_leaf = {"bash", "read_file", "write_file", "edit_file", "apply_patch",
                            "glob", "grep", "list_files", "web_fetch", "web_search",
                            "codegraph_explore", "codegraph_search", "codegraph_node",
                            "codegraph_callers", "codegraph_callees", "memory",
                            "tool_search", "todo", "skills_list", "skill_view"}
            resolved = [t for t in resolved if t in allowed_leaf]

        if goal:
            if run_in_background:
                subagent_id = await self._run_background(goal, context, resolved, model_override, role)
                return ToolResult(
                    success=True,
                    output=f"Background subagent started: {subagent_id}",
                    data={"mode": "background", "subagent_id": subagent_id},
                )
            result = await self._run_single(
                goal, context, resolved, 0, model_override, role,
                agent_name=agent_name, max_tool_rounds=max_tool_rounds,
                team_id=team_id, is_team_lead=is_team_lead,
            )
            return ToolResult(success=True, output=result, data={"mode": "sync"})

        if tasks:
            cap = min(len(tasks), self._max_children)
            if run_in_background:
                ids = await self._run_batch_background(tasks[:cap], context, resolved, model_override, role)
                ids_str = ", ".join(ids)
                return ToolResult(
                    success=True,
                    output=f"{len(ids)} background subagents started. IDs: [{ids_str}]. Call collect_results(subagent_ids=[{ids_str}]) to wait for results.",
                    data={"mode": "background_batch", "subagent_ids": ids},
                )
            results = await self._run_batch(tasks[:cap], context, resolved, model_override, role, agent_name=agent_name, max_tool_rounds=max_tool_rounds)
            summary = "\n\n".join(
                f"## Task {i + 1}: {(tasks[i][:80] if isinstance(tasks[i], str) else tasks[i].get('goal', str(tasks[i]))[:80])}\n{r}"
                for i, r in enumerate(results)
            )
            return ToolResult(success=True, output=summary, data={"mode": "fanout", "count": len(results)})

        return ToolResult(success=False, output="No work", error="empty")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_parent_toolsets(self) -> set[str]:
        from harness.tools.toolsets import TOOLSETS
        from harness.tools.registry import registry as _reg

        parent_tools: set[str] = set()
        if self.delegation.allowed_tools:
            parent_tools = set(self.delegation.allowed_tools)
        elif hasattr(_reg, "list_entries"):
            try:
                parent_tools = {entry.name for entry in _reg.list_entries()}
            except Exception:
                parent_tools = set()
        elif hasattr(_reg, "_tools"):
            parent_tools = set(getattr(_reg, "_tools", {}).keys())
        if not parent_tools:
            # Fall back to the chat toolset when the parent's tools
            # can't be discovered. The chat toolset is the safest
            # read-only baseline; the orchestrator's coordinator
            # always has its own `toolsets` override anyway.
            return set(toolsets_for_mode("chat"))
        derived: set[str] = set()
        for ts_name, ts_def in TOOLSETS.items():
            ts_tools = set(ts_def.get("tools", []))
            if ts_tools and ts_tools.issubset(parent_tools):
                derived.add(ts_name)
        return parent_tools | derived

    def _get_child_depth(self) -> int:
        return self.delegation.depth + 1

    def _check_depth(self, child_depth: int) -> str | None:
        if child_depth > self._max_spawn_depth:
            return f"Max spawn depth ({self._max_spawn_depth}) exceeded at depth {child_depth}"
        return None

    # ------------------------------------------------------------------
    # Sync mode
    # ------------------------------------------------------------------

    async def _run_single(
        self,
        goal: str,
        context: str,
        allowed: list[str],
        index: int = 0,
        model_override: str | None = None,
        role: str = "leaf",
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
        team_id: str = "",
        is_team_lead: bool = False,
    ) -> str:
        """Backward-compat string-returning wrapper. New code should call
        `_run_single_enhanced` and use the SubagentResult directly."""
        result = await self._run_single_enhanced(
            goal=goal,
            context=context,
            allowed=allowed,
            index=index,
            model_override=model_override,
            role=role,
            agent_name=agent_name,
            max_tool_rounds=max_tool_rounds,
            team_id=team_id,
            is_team_lead=is_team_lead,
        )
        if result.status == "ok":
            return result.output or ""
        if result.status == "cancelled":
            return "Cancelled"
        return f"Error: {result.error or 'unknown'}"

    async def _run_single_enhanced(
        self,
        goal: str,
        context: str,
        allowed: list[str],
        index: int = 0,
        model_override: str | None = None,
        role: str = "leaf",
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
        parent_session_id: str | None = None,
        team_id: str = "",
        is_team_lead: bool = False,
    ) -> SubagentResult:
        """Single-subagent runner with all 5 enhancements wired in.

        Order of checks:
          1. depth
          2. budget pre-check (parent session) — if HARD_STOP, return early
          3. register in cancellation tree
          4. spawn child agent
          5. invoke child.run(goal) via _call_child_with_enhancements
             (retry + backoff + jitter, circuit-breaker)
          6. budget post-check after each step
          7. record token usage in TokenLedger
          8. emit SubagentResult with full metadata
        """
        child_depth = self._get_child_depth()
        depth_error = self._check_depth(child_depth)
        started_at = time.time()
        subagent_worktree_info = None  # Initialize early for Python 3.13+ scoping
        heartbeat_stop = asyncio.Event()  # Initialize early for Python 3.13+ scoping
        heartbeat_task = None  # Initialize early for Python 3.13+ scoping
        if depth_error:
            return SubagentResult(
                subagent_id=f"sa-{index}-depth",
                status="error",
                error=depth_error,
                started_at=started_at,
                finished_at=time.time(),
                duration_sec=time.time() - started_at,
            )

        subagent_id = f"sa-{index}-{uuid.uuid4().hex[:8]}"
        effective_role = role if (role == "orchestrator" and child_depth < self._max_spawn_depth) else "leaf"
        parent_id = self.delegation.subagent_id

        # C02: register the subagent with the team (if team_id is
        # set). Done BEFORE create_child_session so a TeamNotFoundError
        # surfaces early rather than after the session row exists.
        team_member_role = None
        if team_id:
            try:
                from harness.services.team_service import (
                    TeamService, MemberRole, TeamNotFoundError,
                )
                from harness.memory.db_context import get_db
                db = get_db()
                if db is not None and getattr(db, "_pool", None) is not None:
                    svc = TeamService(db)
                    member_role = (
                        MemberRole.LEAD if is_team_lead else MemberRole.MEMBER
                    )
                    await svc.add_member(
                        team_id, subagent_id,
                        role=member_role, role_name=agent_name or "",
                    )
                    team_member_role = member_role
                    logger.info(
                        "team member added: team_id=%s subagent_id=%s role=%s",
                        team_id, subagent_id, member_role.value,
                    )
            except TeamNotFoundError as exc:
                return SubagentResult(
                    subagent_id=subagent_id,
                    status="error",
                    error=f"team_not_found: {exc}",
                    started_at=started_at,
                    finished_at=time.time(),
                    duration_sec=time.time() - started_at,
                )
            except Exception as exc:
                # Team registration is best-effort — the subagent
                # still runs even if the team store is unavailable.
                logger.debug(
                    "team add_member failed (continuing without): %s", exc,
                )

        # Create sessions row BEFORE subagent starts
        child_session_id = f"subagent-{subagent_id}"
        from harness.tools.subagent import create_child_session, persist_delegation, check_budget_pre, check_budget_post
        effective_parent = parent_session_id if parent_session_id else (self._session_id if self._session_id else None)
        await create_child_session(child_session_id, child_depth, goal, model_override, effective_parent, started_at)

        # Pre-flight budget check on parent session
        if not check_budget_pre(self._session_id or "global"):
            return SubagentResult(
                subagent_id=subagent_id,
                status="error",
                error="session_budget_exhausted",
                started_at=started_at,
                finished_at=time.time(),
                duration_sec=time.time() - started_at,
            )

        record = {
            "id": subagent_id,
            "goal": goal[:120],
            "depth": child_depth,
            "role": effective_role,
            "status": "running",
            "interrupted": False,
            "started_at": started_at,
            "tool_count": 0,
        }
        with _active_subagents_lock:
            _active_subagents[subagent_id] = record

        cancel_node = None
        try:
            # 1. Register in cancellation tree
            tree = get_cancellation_tree()
            cancel_node = await tree.register(subagent_id, parent_id)

            child_prompt = _build_child_system_prompt(
                goal, context,
                role=effective_role,
                max_spawn_depth=self._max_spawn_depth,
                child_depth=child_depth,
                agent_name=agent_name,
            )

            child_ctx = DelegationContext(
                subagent_id=subagent_id,
                parent_id=parent_id,
                depth=child_depth,
                max_depth=self._max_spawn_depth or 5,
                role=effective_role,
                model_override=model_override,
                allowed_tools=allowed,
                budget_policy=getattr(self, '_budget_policy', None),
                cancel_event=asyncio.Event(),
                system_prompt_override=child_prompt,
                backend_factory=self._backend_factory,
                session_id=self._session_id or "",
            )

            # Inherit parent's volume key so child shares the same /workspace
            if self._backend_factory and self._session_id:
                parent_env = self._backend_factory(self._session_id)
                if parent_env and getattr(parent_env, 'workspace_volume_key', None):
                    child_ctx.volume_key = parent_env.workspace_volume_key

            _factory = self._get_agent_factory()
            if not _factory:
                return SubagentResult(
                    subagent_id=subagent_id,
                    status="error",
                    error="Agent factory not configured",
                    started_at=started_at,
                    finished_at=time.time(),
                    duration_sec=time.time() - started_at,
                )
            child = _factory(
                allowed_tools=allowed,
                backend_factory=self._backend_factory,
                session_id=child_session_id,
                system_prompt_override=child_prompt,
                model_override=model_override,
                delegation=child_ctx,
                recipe_name=effective_role if effective_role in ("chat", "orchestrator") else "chat",
                max_tool_rounds=max_tool_rounds or 20,
            )

            # Set task_id for per-subagent cost tracking
            child._task_id = subagent_id

            _parent_sid = self._session_id or ""
            if _parent_sid and child_session_id != _parent_sid:
                try:
                    from harness.api.state import get_event_source_sink
                    sink = get_event_source_sink()
                    if sink is not None:
                        sink.register_child(child_session_id, _parent_sid)
                except Exception:
                    pass

            # C01: per-subagent worktree (per C01 Q3 branch naming).
            # The subagent gets its own branch off the main repo
            # so its commits don't clobber siblings' work. The
            # worktree is best-effort — if creation fails (e.g.
            # the main repo isn't a git repo, or git isn't on
            # PATH), the subagent still runs in the shared
            # container.
            #
            # C01 contextvar: ``WorktreeManager()`` with no
            # explicit runner falls back to
            # ``get_current_git_runner()`` — the orchestrator's
            # ``set_current_git_runner(sandbox_git_runner(sandbox))``
            # makes the subagent inherit the sandbox runner
            # (production: git inside the container). Tests: the
            # default ``local_git_runner`` is used.
            try:
                from harness.services.worktree_manager import (
                    WorktreeManager,
                    subagent_branch,
                    subagent_slug,
                )
                # The orchestrator's bootstrap (orchestrator.py)
                # already created a per-session worktree at
                # ``<repo>/.testai-worktrees/session-<id>``. We use
                # the same ``base_dir`` here so per-subagent
                # worktrees live alongside the per-session one.
                # If the per-session worktree doesn't exist (the
                # orchestrator was started in a non-git env), the
                # per-subagent worktree falls back to the main
                # repo path.
                wt_manager = WorktreeManager()
                wt_base_path = Path("/workspace/repo")
                subagent_worktree_info = await wt_manager.create_worktree(
                    wt_base_path,
                    subagent_slug(subagent_id),
                    branch=subagent_branch(subagent_id),
                    agent_id=subagent_id,
                )
                logger.info(
                    "Per-subagent worktree created: slug=%s path=%s branch=%s",
                    subagent_worktree_info.slug,
                    subagent_worktree_info.path,
                    subagent_worktree_info.branch,
                )
            except Exception as exc:
                logger.debug(
                    "Per-subagent worktree creation failed (continuing without): %s",
                    exc,
                )

            # Enable shield mode for orchestrator subagents — auto-allow all tools
            if effective_role == "orchestrator" or child_depth > 0:
                child._deps.permissions.set_shield(True)

            # Emit stream event for subagent spawn — typed SubagentSpawned
            # (F25) so the frontend can both filter by class name and read
            # the structured fields.  Falls back to GenericStreamEvent on
            # the rare missing-import path so the legacy string shape still
            # surfaces on the wire.
            try:
                from harness.core.events import SubagentSpawned as _SubagentSpawned
                _ev = _SubagentSpawned(
                    subagent_id=subagent_id,
                    goal=goal[:200],
                    depth=child_depth,
                    role=effective_role,
                    model=model_override,
                    parent_subagent_id=parent_id,
                    session_id=self._session_id or "",
                )
                await self._event_bus.emit(_ev)
            except Exception:
                try:
                    from harness.api.state import emit_stream_event
                    await emit_stream_event(self._session_id or "", "subagent.spawned", {
                        "subagent_id": subagent_id,
                        "goal": goal[:200],
                        "depth": child_depth,
                        "role": effective_role,
                        "model": model_override,
                        "allowed_tools": allowed[:10],
                        "parent_subagent_id": parent_id,
                        "started_at": started_at,
                    })
                except Exception:
                    pass

            # 2. Circuit breaker
            provider_name = (model_override or "default")
            breaker = get_circuit_breakers().for_provider(provider_name)

            # 3. Cancellation watcher — race child.run() against cancel event
            cancel_task = asyncio.create_task(cancel_node.cancel_event.wait())

            async def _run_child() -> _AgentResult:
                logger.info("Subagent %s: starting child.run(goal=%s)", subagent_id, goal[:80])
                async with scope_manager.scope():
                    raw = await child.run(goal, model=model_override or None)
                logger.info("Subagent %s: child.run returned type=%s len=%d", subagent_id, type(raw).__name__, len(str(raw)) if raw else 0)
                model = getattr(child, "_last_model", "") or model_override or ""
                usage = getattr(child, "_last_usage", {}) or {}
                # Count tool calls from child's messages
                tool_count = 0
                try:
                    msgs = getattr(child, "_messages", []) or []
                    for msg in msgs:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            tool_count += len(msg.tool_calls)
                except Exception:
                    pass
                if isinstance(raw, _AgentResult):
                    raw.model = raw.model or model
                    raw.prompt_tokens = raw.prompt_tokens or usage.get("prompt_tokens", 0)
                    raw.completion_tokens = raw.completion_tokens or usage.get("completion_tokens", 0)
                    raw.tool_calls_count = tool_count
                    return raw
                return _AgentResult(
                    output=str(raw),
                    model=model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    tool_calls_count=tool_count,
                )

            child_task = asyncio.create_task(
                _call_child_with_enhancements(
                    _run_child,
                    subagent_id=subagent_id,
                    model=model_override,
                    breaker=breaker,
                ),
                name=f"subagent-{subagent_id}",
            )

            # C06: spawn a heartbeat task alongside the child. Two
            # purposes:
            #   1. Touch the parent's gateway activity timestamp so
            #      the upstream gateway inactivity timeout doesn't
            #      fire while the child is doing legitimately slow
            #      work (apt-get, web_fetch, etc).
            #   2. Detect stuckness — if neither ``api_call_count``
            #      nor ``current_tool`` advances for the configured
            #      threshold, raise SubagentStuckError and let the
            #      parent's existing error path turn it into a
            #      user-readable failure.
            # NOTE: ``heartbeat_stop`` is initialized BEFORE the try
            # block so the ``finally`` clause can reference it even
            # if heartbeat init failed.
            try:
                from harness.services.heartbeat import (
                    SubagentHeartbeat,
                    SubagentStuckError,
                )

                async def _emit_heartbeat_event(
                    *,
                    subagent_id: str,
                    current_iter: int,
                    current_tool: str | None,
                    last_activity_desc: str,
                    stale_count: int,
                    elapsed_seconds: float,
                ) -> None:
                    """SubagentHeartbeat callback: publish a
                    ``subagent.heartbeat`` event on the EventBus.
                    """
                    try:
                        from harness.api.state import emit_stream_event
                        await emit_stream_event(self._session_id or "", "subagent.heartbeat", {
                            "subagent_id": subagent_id,
                            "api_call_count": current_iter,
                            "current_tool": current_tool,
                            "last_activity_desc": last_activity_desc,
                            "stale_count": stale_count,
                            "elapsed_seconds": round(elapsed_seconds, 1),
                        })
                    except Exception as exc:
                        logger.debug("subagent.heartbeat emit failed: %s", exc)

                heartbeat = SubagentHeartbeat(
                    subagent_id=subagent_id,
                    target=child,
                    on_heartbeat=_emit_heartbeat_event,
                )
                heartbeat_task = asyncio.create_task(
                    heartbeat.run(heartbeat_stop),
                    name=f"heartbeat-{subagent_id}",
                )
            except Exception as exc:
                # The heartbeat is best-effort. If import or
                # instantiation fails, log and continue without it.
                logger.debug(
                    "subagent_heartbeat init failed subagent_id=%s err=%s",
                    subagent_id, exc,
                )

            done, pending = await asyncio.wait(
                {child_task, cancel_task} | ({heartbeat_task} if heartbeat_task else set()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done and not child_task.done():
                child_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await child_task
                raise asyncio.CancelledError()

            # C06: if the heartbeat finished first, it means
            # SubagentStuckError fired. The child is presumed hung;
            # cancel it and translate to a structured error.
            if heartbeat_task is not None and heartbeat_task in done and not child_task.done():
                try:
                    outcome = heartbeat_task.result()
                except Exception as exc:
                    outcome = exc
                # Cancel the hung child.
                child_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await child_task
                # The ``done`` set may have the heartbeat's exception
                # but our ``pending`` set should also be cleared.
                for p in list(pending):
                    p.cancel()
                heartbeat_stop.set()
                if isinstance(outcome, Exception):
                    # The heartbeat run() returns HeartbeatOutcome on
                    # stuck; if it raised, that's an internal bug.
                    logger.error("heartbeat raised: %s", outcome)
                else:
                    # Stuck. Build the SubagentStuckError and return
                    # it as a structured error to the parent LLM.
                    stuck_err = SubagentStuckError(
                        subagent_id=subagent_id,
                        last_iter=outcome.last_iter,
                        last_tool=outcome.last_tool,
                        stale_seconds=outcome.stuck_at_seconds or 0.0,
                    )
                    finished_at = time.time()
                    record["status"] = "stuck"
                    record["error"] = str(stuck_err)
                    await persist_delegation(
                        parent_session_id=self._session_id or None,
                        subagent_id=subagent_id,
                        goal=goal,
                        status="error",
                        started_at=started_at,
                        finished_at=finished_at,
                        error=str(stuck_err),
                        depth=child_depth,
                        parent_subagent_id=parent_id,
                    )
                    _record_model_outcome(
                        model=model_override or "",
                        success=False,
                        duration_ms=(time.time() - started_at) * 1000.0,
                        error_type="SubagentStuckError",
                    )
                    return SubagentResult(
                        subagent_id=subagent_id,
                        status="error",
                        error=f"SubagentStuckError: {stuck_err}",
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_sec=finished_at - started_at,
                        # C1: the stuckness verdict pattern is the detector
                    # name. Today all heartbeat timeouts produce
                    # "heartbeat_stale"; future adapters (InProcessAdapter)
                    # will populate this with the specific pattern
                    # (repeating_hash, monologue, ping_pong, etc.).
                    detector_name="heartbeat_stale",
                    )

            result_inner: _AgentResult = await child_task
            for p in pending:
                p.cancel()
            # C06: stop the heartbeat cleanly once the child returns.
            heartbeat_stop.set()
            if heartbeat_task is not None and not heartbeat_task.done():
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await heartbeat_task

            # 4. Record token usage
            if result_inner.prompt_tokens or result_inner.completion_tokens or result_inner.cost_usd:
                usage = TokenUsage(
                    prompt_tokens=result_inner.prompt_tokens,
                    completion_tokens=result_inner.completion_tokens,
                    cost_usd=result_inner.cost_usd,
                    model=result_inner.model or model_override or "",
                )
                get_token_ledger().record(
                    self._session_id or "global",
                    subagent_id,
                    usage,
                )

            # 5. Budget post-check on subagent
            budget_ok, truncation_suffix = check_budget_post(subagent_id)
            output = (result_inner.output or "") + truncation_suffix if not budget_ok else (result_inner.output or "")

            finished_at = time.time()
            record["status"] = "completed"
            record["result"] = output[:500]

            # Persist to DB for real-time visibility
            await persist_delegation(
                parent_session_id=self._session_id or None,
                subagent_id=subagent_id,
                goal=goal,
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                output=output,
                prompt_tokens=result_inner.prompt_tokens,
                completion_tokens=result_inner.completion_tokens,
                cost_usd=result_inner.cost_usd,
                model=result_inner.model or model_override or "",
                depth=child_depth,
                parent_subagent_id=parent_id,
                tool_calls_count=result_inner.tool_calls_count,
            )

            # F15/CC6: feed the subagent's outcome into the shared
            # provider-quality tracker. Done before the return so the
            # call actually executes.
            _record_model_outcome(
                model=result_inner.model or model_override or "",
                success=True,
                duration_ms=(time.time() - started_at) * 1000.0,
            )

            return SubagentResult(
                subagent_id=subagent_id,
                status="ok",
                output=output,
                started_at=started_at,
                finished_at=finished_at,
                duration_sec=finished_at - started_at,
                prompt_tokens=result_inner.prompt_tokens,
                completion_tokens=result_inner.completion_tokens,
                total_tokens=result_inner.prompt_tokens + result_inner.completion_tokens,
                cost_usd=result_inner.cost_usd,
                model=result_inner.model or model_override or "",
                evidence=await _collect_evidence_async(child_session_id),
                detector_name=_apply_success_detector(
                    result_inner.output, success=True,
                ),
            )

        except asyncio.CancelledError:
            finished_at = time.time()
            record["status"] = "cancelled"
            await persist_delegation(
                parent_session_id=self._session_id or None,
                subagent_id=subagent_id,
                goal=goal,
                status="cancelled",
                started_at=started_at,
                finished_at=finished_at,
                error="cancelled",
                depth=child_depth,
                parent_subagent_id=parent_id,
            )
            return SubagentResult(
                subagent_id=subagent_id,
                status="cancelled",
                error="cancelled",
                started_at=started_at,
                finished_at=finished_at,
                duration_sec=finished_at - started_at,
            )
        except Exception as e:
            finished_at = time.time()
            record["status"] = "failed"
            record["error"] = str(e)
            logger.error("Subagent %s failed: %s", subagent_id, e)
            await persist_delegation(
                parent_session_id=self._session_id or None,
                subagent_id=subagent_id,
                goal=goal,
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                error=str(e),
                depth=child_depth,
                parent_subagent_id=parent_id,
            )
            # F15/CC6: feed the failed outcome into the provider-quality tracker.
            _record_model_outcome(
                model=model_override or "",
                success=False,
                duration_ms=(time.time() - started_at) * 1000.0,
                error_type=type(e).__name__,
            )
            return SubagentResult(
                subagent_id=subagent_id,
                status="error",
                error=f"{type(e).__name__}: {e}",
                started_at=started_at,
                finished_at=finished_at,
                duration_sec=finished_at - started_at,
                detector_name=_apply_success_detector(str(e), success=False),
            )
        finally:
            with _active_subagents_lock:
                _active_subagents.pop(subagent_id, None)
            if cancel_node is not None:
                get_cancellation_tree().cleanup(subagent_id)
            # C01: auto-remove the per-subagent worktree after the
            # subagent finishes (per Q6 of the C01 decision tree).
            # The branch is on origin (the draft PR is its evidence);
            # the worktree's only job was to host the commits.
            # Best-effort: errors are logged but don't fail the run.
            if subagent_worktree_info is not None:
                try:
                    from harness.services.worktree_manager import (
                        WorktreeManager,
                        subagent_slug,
                    )
                    wt_manager = WorktreeManager()
                    removed = await wt_manager.remove_worktree(
                        Path("/workspace/repo"),
                        subagent_slug(subagent_id),
                    )
                    if removed:
                        logger.info(
                            "Per-subagent worktree removed: subagent_id=%s",
                            subagent_id,
                        )
                except Exception as exc:
                    logger.debug(
                        "Per-subagent worktree cleanup failed: %s", exc,
                    )
            # C02: mark the team member as done (or failed) so
            # TeamService.cleanup_completed can auto-dissolve the
            # team when every member finishes. Best-effort.
            if team_id and team_member_role is not None:
                try:
                    from harness.services.team_service import (
                        TeamService, MemberStatus,
                    )
                    from harness.memory.db_context import get_db
                    db = get_db()
                    if db is not None and getattr(db, "_pool", None) is not None:
                        svc = TeamService(db)
                        # Decide done vs failed from the subagent's
                        # final status. The status was set in the
                        # try/except blocks above; we use the
                        # ``record["status"]`` mirror.
                        final_status = record.get("status", "active")
                        new_status = (
                            MemberStatus.FAILED
                            if final_status in ("failed", "error")
                            else MemberStatus.DONE
                        )
                        await svc.update_member_status(
                            team_id, subagent_id, new_status,
                        )
                except Exception as exc:
                    logger.debug(
                        "team update_member_status failed: %s", exc,
                    )
            # C01: auto-remove the per-subagent worktree after the
            # subagent finishes (per Q6 of the C01 decision tree).
            # The branch is on origin (the draft PR is its evidence);
            # the worktree's only job was to host the commits.
            # Best-effort: errors are logged but don't fail the run.
            if subagent_worktree_info is not None:
                try:
                    from harness.services.worktree_manager import (
                        WorktreeManager,
                        subagent_slug,
                    )
                    wt_manager = WorktreeManager()
                    removed = await wt_manager.remove_worktree(
                        Path("/workspace/repo"),
                        subagent_slug(subagent_id),
                    )
                    if removed:
                        logger.info(
                            "Per-subagent worktree removed: subagent_id=%s",
                            subagent_id,
                        )
                except Exception as exc:
                    logger.debug(
                        "Per-subagent worktree cleanup failed: %s", exc,
                    )
            # C06: best-effort stop the heartbeat. The stop_event
            # is set so the loop exits; we don't await it here so
            # the cancel/exception path doesn't block.
            heartbeat_stop.set()
            if heartbeat_task is not None and not heartbeat_task.done():
                heartbeat_task.cancel()

    # ------------------------------------------------------------------
    # Fan-Out (batch sync) — delegates to Subagent.spawn_many() so the
    # depth/budget/rate/retry/circuit-breaker checks live in one place.
    # The tool-specific glue (DelegationContext, volume key, stream
    # event, evidence, F15) is wired in via the factory_wrapper hook
    # so Subagent stays sandbox-agnostic.
    # ------------------------------------------------------------------

    async def _run_batch(
        self,
        tasks: list[str | dict],
        context: str,
        allowed: list[str],
        model_override: str | None = None,
        role: str = "leaf",
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
    ) -> list[str]:
        from harness.tools.subagent import Subagent
        from harness.tools.toolsets import resolve_toolsets

        sub = Subagent(
            agent_factory=self._get_agent_factory(),
            session_id=self._session_id or "",
            max_spawn_depth=self._max_spawn_depth,
        )

        async def _spawn_with_glue(task: str | dict) -> "SubagentResult":
            if isinstance(task, dict):
                task_goal = task.get("goal", "")
                task_raw_toolsets = task.get("toolsets", None)
                if task_raw_toolsets:
                    task_toolsets = resolve_toolsets(task_raw_toolsets)
                else:
                    task_toolsets = allowed
                task_role = task.get("role", role)
            else:
                task_goal = task
                task_toolsets = allowed
                task_role = role
            return await sub.spawn(
                goal=task_goal,
                role=task_role,
                context=context,
                toolsets=task_toolsets,
                model_override=model_override,
                agent_name=agent_name,
                max_tool_rounds=max_tool_rounds,
                parent_session_id=self._session_id or None,
                factory_wrapper=lambda f: self._wrap_factory_for_tool(f, allowed),
            )

        coros = {
            f"sa-fanout-{i}-{uuid.uuid4().hex[:6]}": _spawn_with_glue(t)
            for i, t in enumerate(tasks)
        }
        results = await stream_fan_out(coros, on_complete=None)
        return [r.output or "" for r in results]

    def _wrap_factory_for_tool(
        self,
        base_factory: Callable,
        allowed: list[str],
    ) -> Callable:
        """Wrap the agent factory with the tool-specific DelegationContext setup.

        Subagent.spawn() only knows about the basic agent factory
        contract. ``DelegateTaskTool`` has tool-specific glue
        (DelegationContext, parent volume key inheritance,
        child._task_id, shield mode for orchestrator subagents)
        that the Subagent class shouldn't know about. The
        wrapper is the seam: the tool's factory is wrapped to
        add the tool-specific setup around the child's creation.
        """
        tool_self = self
        parent_id = tool_self.delegation.subagent_id

        def wrapped_factory(
            *,
            system_prompt: str,
            toolsets: list[str] | None,
            session_id: str,
            max_tool_rounds: int,
            model: str | None,
        ) -> Any:
            # Build the DelegationContext that the child's
            # ``AgentDeps`` expects. Subagent.spawn() doesn't know
            # about this; it's a tool-specific concern.
            from harness.delegation import DelegationContext
            from harness.tools.budget import get_budget_policy
            child_ctx = DelegationContext(
                subagent_id=session_id.replace("subagent-", ""),
                parent_id=parent_id,
                depth=tool_self.delegation.depth + 1,
                max_depth=tool_self._max_spawn_depth or 5,
                role=role_for_session(tool_self, toolsets),
                model_override=model,
                allowed_tools=allowed,
                budget_policy=get_budget_policy(),
                cancel_event=asyncio.Event(),
                system_prompt_override=system_prompt,
                backend_factory=tool_self._backend_factory,
                session_id=tool_self._session_id or "",
            )
            # Inherit parent's volume key so child shares /workspace
            if tool_self._backend_factory and tool_self._session_id:
                parent_env = tool_self._backend_factory(tool_self._session_id)
                if parent_env and getattr(parent_env, 'workspace_volume_key', None):
                    child_ctx.volume_key = parent_env.workspace_volume_key
            child = base_factory(
                allowed_tools=allowed,
                backend_factory=tool_self._backend_factory,
                session_id=session_id,
                system_prompt_override=system_prompt,
                model_override=model,
                delegation=child_ctx,
                recipe_name="chat",
                max_tool_rounds=max_tool_rounds or 20,
            )
            # Mark the child for per-subagent cost tracking
            child._task_id = session_id.replace("subagent-", "")
            # Orchestrator subagents get shield mode (auto-allow all tools)
            if child_ctx.role == "orchestrator" or child_ctx.depth > 0:
                if hasattr(child, "_deps") and hasattr(child._deps, "permissions"):
                    child._deps.permissions.set_shield(True)
            return child
        return wrapped_factory

    # ------------------------------------------------------------------
    # Background mode — also delegates to Subagent for the
    # depth/budget/rate/retry checks, then stores the future in
    # _pending_results so collect_results can pick it up.
    # ------------------------------------------------------------------

    async def _run_background(
        self,
        goal: str,
        context: str,
        allowed: list[str],
        model_override: str | None = None,
        role: str = "leaf",
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
    ) -> str:
        from harness.tools.subagent import Subagent

        subagent_id = f"sa-bg-{uuid.uuid4().hex[:8]}"
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        with _pending_results_lock:
            _pending_results[subagent_id] = future

        # Pre-register for cancellation
        parent_id = self.delegation.subagent_id
        await get_cancellation_tree().register(subagent_id, parent_id)

        # Capture session_id before creating the task to avoid closure issues
        captured_session_id = self._session_id

        sub = Subagent(
            agent_factory=self._get_agent_factory(),
            session_id=captured_session_id,
            max_spawn_depth=self._max_spawn_depth,
        )

        async def _worker() -> None:
            try:
                result = await sub.spawn(
                    goal=goal,
                    role=role,
                    context=context,
                    toolsets=allowed,
                    model_override=model_override,
                    agent_name=agent_name,
                    max_tool_rounds=max_tool_rounds,
                    parent_session_id=captured_session_id or None,
                    factory_wrapper=lambda f: self._wrap_factory_for_tool(f, allowed),
                )
                if not future.done():
                    future.set_result(result)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)

        asyncio.create_task(_worker(), name=f"bg-subagent-{subagent_id}")
        return subagent_id

    async def _run_batch_background(
        self,
        tasks: list[str | dict],
        context: str,
        allowed: list[str],
        model_override: str | None = None,
        role: str = "leaf",
        agent_name: str | None = None,
        max_tool_rounds: int | None = None,
    ) -> list[str]:
        ids: list[str] = []
        for t in tasks:
            if isinstance(t, dict):
                t_goal = t.get("goal", "")
            else:
                t_goal = t
            sid = await self._run_background(
                t_goal, context, allowed, model_override, role,
                agent_name=agent_name, max_tool_rounds=max_tool_rounds,
            )
            ids.append(sid)
        return ids


# Register tools at module import time (discovered by registry.discover_tools())
_collect_results_tool = CollectResultsTool()
from harness.tools.registry import registry as _registry
_registry.register(_collect_results_tool, toolset="delegate")
# DelegateTaskTool is also registered here (agent_factory is set later in lifespan)
_registry.register(DelegateTaskTool(), toolset="delegate")
