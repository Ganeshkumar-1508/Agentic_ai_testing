from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from harness.agent import Agent, AgentDependencies
from harness.events import EventBus, EventSourceSink, LogSink, StreamEventsDBSink, TraceCallbackSink
from harness.tools.registry import registry as tool_registry
from harness.tools.toolsets import CHAT_READONLY_TOOLSET
from harness.tools.chat_introspection import set_introspection_store
from harness.tools.checkpoint import set_checkpoint_db
from harness.jobs.spec import set_job_spec_store, set_proposal_store
from harness.backends.factory import get_backend, resolve_backend_type
from harness.context_compressor import ContextCompressor
from harness.mcp.client import MCPClient
from harness.permissions.manager import PermissionManager
from harness.scheduler.loop import Scheduler
from harness.llm import LLMRouter
from harness.memory.database import Database
from harness.memory.settings_store import SettingsStore
from harness.memory.store import PersistentStore

from . import state
from .agent_routes import agent_routers
from .settings_routes import settings_routers
from .admin_routes import admin_routers
from .integration_routes import integration_routers
# C05: A2A Protocol v1.0 server. Two routers — the spec-mandated
# `/.well-known/agent.json` is mounted at the root (no prefix); the
# JSON-RPC + SSE endpoints are mounted under `/a2a/...`. See
# `harness/a2a/server.py` and `docs/2026-06-21-c05-design.md`.
from harness.a2a.server import a2a_router, agent_card_router
logger = logging.getLogger(__name__)


class StartupTimer:
    """Records elapsed time between startup phases and reports a summary."""

    def __init__(self):
        self._start = time.monotonic()
        self._phases: list[tuple[str, float]] = [("start", 0.0)]
        self._phase_count = 0

    def checkpoint(self, label: str) -> None:
        elapsed = time.monotonic() - self._start
        self._phases.append((label, elapsed))
        self._phase_count += 1
        logger.debug("[startup] %s — %.3fs", label, elapsed)

    def report(self) -> str:
        total = time.monotonic() - self._start
        lines = [f"Startup complete: {len(self._phases)-1} phases in {total:.2f}s"]
        for i in range(1, len(self._phases)):
            label, elapsed = self._phases[i]
            prev_elapsed = self._phases[i - 1][1]
            delta = elapsed - prev_elapsed
            lines.append(f"  {i:2d}. {label:<25s} {elapsed:>7.3f}s ({delta:>+.3f}s)")
        lines.append(f"  -- {'total':<25s} {total:>7.3f}s")
        return "\n".join(lines)


db = Database()
settings_store = SettingsStore(db)
store = PersistentStore(db)
# Wire the chat introspection store before any chat tool runs. The
# chat-readonly tools (list_runs, get_run, get_logs, etc.) read from
# this store. If the wiring is missed the tools return a clear
# "introspection store not initialized" error rather than crashing.
set_introspection_store(store)
from harness.tools.chat_read_tools import set_chat_db
set_chat_db(db)
# Wire the checkpoint db (used by the orchestrator's coordinator for
# crash recovery). Same pattern as set_introspection_store: module-level
# reference set at startup; tools return a clear "not initialised"
# error if wiring is missed.
set_checkpoint_db(db)
# Wire the C4-revised JobSpec/Proposal stores. The chat Role's
# `submit_job` tool writes to JobSpecStore; the orchestrator's Tier-2
# path writes to ProposalStore. Both are protocol-bound; see
# `harness.store.protocols`.
from harness.store.adapters.postgres import PostgresJobSpecStore, PostgresProposalStore
set_job_spec_store(PostgresJobSpecStore(db))
set_proposal_store(PostgresProposalStore(db))
llm: LLMRouter | None = None
agent: Agent | None = None
mcp_client: MCPClient | None = None


async def _trace_handler(event_type: str, data: dict[str, Any]) -> None:
    await state.trace_handler(event_type, data, db)





@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm, agent, mcp_client
    scheduler: Scheduler | None = None
    t = StartupTimer()

    logger.info("=== LIFESPAN START ===")
    print("LIFESPAN START")
    try:
        await asyncio.wait_for(db.connect(), timeout=15)
    except asyncio.TimeoutError:
        logger.error("DB connection timeout in lifespan startup")
        raise
    # Set the global DB accessor so tools can access the DB.
    # Replaces the old Database._instance singleton pattern.
    from harness.memory.db_context import set_db
    set_db(db)
    t.checkpoint("db_connect")

    # Load .env files for API keys before provider init
    from harness.env_loader import load_env
    load_env()
    t.checkpoint("env_loader")

    stored_providers = await settings_store.get_all_providers()
    llm = LLMRouter()
    llm.set_db(db)
    t.checkpoint("providers_load")

    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        env_entry = {
            "provider": "opencode",
            "api_key": env_key,
            "base_url": os.environ.get("OPENAI_BASE_URL", "https://opencode.ai/zen/go/v1"),
            "model": os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash"),
            "enabled": True,
            "options": {"reasoning": {"enabled": True, "effort": "low"}},
        }
        stored_providers = [p for p in stored_providers if p["provider"] != "opencode"]
        stored_providers.insert(0, env_entry)
        await settings_store.upsert_provider("opencode", env_entry)

    if stored_providers:
        llm.configure(stored_providers)
    
    # Set the shared LLM router so tools can access it
    from harness.api.state import set_llm
    set_llm(llm)
    logger.info("Shared LLM router configured with %d providers", len(stored_providers))
    t.checkpoint("llm_configure")

    tool_registry.discover_tools()
    tool_registry.db = db
    logger.info("Tool discovery: %d tools registered", len(tool_registry.list_entries()))
    dt_check = tool_registry.get("delegate_task")
    logger.info("delegate_task registered: %s", "yes" if dt_check else "NO")
    t.checkpoint("tool_discovery")

    # Startup orphan reaper (Hermes-Agent pattern): remove stale
    # Knowledge-graph orphan reaper: remove host-cached KG directories
    # that have no provenance.json (the syncer writes provenance on
    # every successful build).  These are partial builds interrupted by
    # a crash or sandbox kill mid-indexing.  Without this, the dropdown
    # accumulates "empty" graphs (0 nodes / 0 edges) from failed runs.
    #
    # Also dedupes graphs by their normalized (repo_url, branch) key —
    # past runs that hashed different URL forms (e.g. ``rails/rails`` vs
    # ``rails/rails.git``) produced two directories for the same logical
    # repo.  We keep the most-recently-indexed one and remove the rest.
    # Matches the CodeGraph design (one index per project root) that
    # TestAI's host-mirror pattern was supposed to mirror but didn't.
    try:
        from pathlib import Path
        import json
        import shutil
        from harness.codegraph import normalize_repo_url, repo_graph_id
        kg_root = Path(os.environ.get("AGENT_WORKSPACE_MOUNT", "/app/agent_workspace")) / "knowledge-graphs"
        if kg_root.exists():
            # Step 1: drop orphan (partial-build) directories.
            n_orphans = 0
            for entry in kg_root.iterdir():
                if not entry.is_dir():
                    continue
                prov = entry / "provenance.json"
                codegraph_db = entry / "codegraph.db"
                if not (prov.exists() and codegraph_db.exists()):
                    shutil.rmtree(entry, ignore_errors=True)
                    n_orphans += 1
                    logger.info("KG orphan reaper: removed partial %s", entry.name)
            if n_orphans:
                logger.info("KG orphan reaper: removed %d partial graph dir(s)", n_orphans)

            # Step 2: dedupe by canonical (repo_url, branch) key.
            # Build {canonical_id: [candidates]} from the survivors.
            from collections import defaultdict
            by_canonical: dict[str, list[tuple[Path, float]]] = defaultdict(list)
            for entry in kg_root.iterdir():
                if not entry.is_dir():
                    continue
                prov = entry / "provenance.json"
                if not prov.exists():
                    continue
                try:
                    with open(prov) as f:
                        p = json.load(f)
                except Exception:
                    continue
                if not isinstance(p, dict):
                    continue
                repo_url = (p.get("repo_url") or "").strip()
                branch = (p.get("branch") or "main").strip()
                # Canonical id: the same hash the syncer would produce today
                # for this (repo_url, branch) tuple.  Anything not matching
                # is a legacy duplicate.
                canonical = repo_graph_id(repo_url, branch)
                try:
                    mtime = (entry / "codegraph.db").stat().st_mtime
                except OSError:
                    continue
                by_canonical[canonical].append((entry, mtime))

            n_deduped = 0
            for canonical, candidates in by_canonical.items():
                if len(candidates) <= 1:
                    continue
                # Keep the most-recently-modified dir, drop the rest.
                candidates.sort(key=lambda c: c[1], reverse=True)
                winner = candidates[0][0]
                for loser, _ in candidates[1:]:
                    logger.info(
                        "KG dedup: removing %s (dup of %s for canonical=%s)",
                        loser.name, winner.name, canonical,
                    )
                    shutil.rmtree(loser, ignore_errors=True)
                    n_deduped += 1
            if n_deduped:
                logger.info("KG dedup: removed %d duplicate graph dir(s)", n_deduped)
    except Exception as exc:
        logger.debug("KG orphan reaper failed (non-fatal): %s", exc)

    # Initialize pricing cache (loads from DB, refreshes from MCP every 7 days / 168 hours)
    from harness.cost_tracker import init_pricing_cache
    pricing = init_pricing_cache(db)
    try:
        await asyncio.wait_for(pricing.refresh_if_stale(), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Pricing cache refresh timed out (non-fatal)")
    app.state.pricing_cache = pricing
    t.checkpoint("pricing_cache")

    # Initialize context compressor for the root agent (optional — no compressor if unconfigured)
    context_compressor = None
    compressor_model = llm.get_model_for_role("default")
    if compressor_model:
        try:
            rates = await asyncio.wait_for(pricing.get_rate(compressor_model), timeout=5)
            ctx_len = rates.get("context_length")
            if ctx_len:
                from harness._compressor_utils import get_compaction_threshold
                context_compressor = ContextCompressor(
                    model=compressor_model,
                    config_context_length=int(ctx_len),
                    threshold_percent=get_compaction_threshold(),
                    quiet_mode=False,
                )
        except asyncio.TimeoutError:
            logger.info("Context compression disabled — pricing rate timed out")
        except Exception:
            logger.info("Context compression disabled — could not resolve context length for %s", compressor_model)
    app.state.context_compressor = context_compressor
    t.checkpoint("context_compressor")

    # Background loops — wrapped in ManagedTask for structured lifecycle
    # (error propagation, restart with backoff, clean shutdown)
    from harness.lifecycle import ManagedTask

    managed_tasks: list[ManagedTask] = []

    async def _digest_loop():
        while True:
            try:
                from harness.daily_digest import run_digest_for_configs
                delivery = getattr(app.state, "delivery_router", None)
                if delivery:
                    await run_digest_for_configs(db, delivery)
            except Exception as exc:
                logger.debug("Digest check failed: %s", exc)
            await asyncio.sleep(3600)

    async def _curator_loop():
        while True:
            try:
                from harness.curator import maybe_run_curator, run_evolution
                report = await maybe_run_curator(db)
                if report.get("archived"):
                    logger.info("Curator archived %d skills", len(report["archived"]))
                evolved = await run_evolution(db, llm=llm)
                if evolved:
                    logger.info("Curator evolved %d new skills", len(evolved))
            except Exception as exc:
                logger.debug("Curator loop failed: %s", exc)
            await asyncio.sleep(3600)

    async def _discovery_loop():
        """Poll for new Issues/PRs on connected repos every 15 min."""
        from harness.ci.git_providers import get_provider_from_url, get_provider
        while True:
            try:
                for provider_name in ("github", "gitlab"):
                    row = await db.fetchrow(
                        "SELECT config FROM integration_configs WHERE platform = $1 AND enabled = true LIMIT 1",
                        provider_name,
                    )
                    if not row:
                        continue
                    cfg = row["config"]
                    if isinstance(cfg, str):
                        import json as _j
                        cfg = _j.loads(cfg)
                    token = cfg.get("token", "") if isinstance(cfg, dict) else ""
                    if not token:
                        continue
                    tracked = await db.fetch(
                        "SELECT DISTINCT repo_url FROM pr_tracker WHERE repo_provider = $1",
                        provider_name,
                    )
                    provider = get_provider(provider_name)
                    for row in tracked:
                        raw = row["repo_url"]
                        detected = get_provider_from_url(raw)
                        repo_path = detected[1] if detected else raw
                        try:
                            issues = await provider.list_open_issues(repo_path, token)
                            base_url = f"https://{provider_name}.com/{repo_path}"
                            for issue in issues:
                                existing = await db.fetchrow(
                                    "SELECT id FROM pr_tracker WHERE repo_url = $1 AND pr_number = $2",
                                    base_url, issue["number"],
                                )
                                if not existing:
                                    await db.execute(
                                        "INSERT INTO pr_tracker (repo_url, repo_provider, pr_number, title, "
                                        "description, status, source_branch, target_branch, author, "
                                        "files_changed, additions, deletions, labels, risk_score) "
                                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)",
                                        base_url, provider_name, issue["number"],
                                        issue["title"], issue["body"], "open",
                                        f"issue-{issue['number']}", "main", issue["user"],
                                        0, 0, 0, issue["labels"], 10,
                                    )
                                    logger.info("Discovered new %s issue #%d: %s", provider_name, issue["number"], issue["title"][:60])
                        except Exception as e:
                            logger.debug("Issue discovery failed for %s (%s): %s", raw, provider_name, e)
            except Exception as exc:
                logger.debug("Discovery loop error: %s", exc)
            await asyncio.sleep(900)  # 15 minutes

    # Resume abandoned orchestrations on startup
    from harness.orchestrator import OrchestratorEngine
    try:
        resumed = await asyncio.wait_for(OrchestratorEngine.resume_abandoned(db), timeout=10)
        if resumed:
            logger.info("Resumed %d abandoned session(s)", len(resumed))
    except asyncio.TimeoutError:
        logger.warning("Resume abandoned timed out (non-fatal)")
    except Exception as exc:
        logger.debug("Resume abandoned check failed: %s", exc)

    # Start background tasks with ManagedTask lifecycle
    for name, coro, interval in [
        ("digest", _digest_loop, 3600),
        ("curator", _curator_loop, 3600),
        ("discovery", _discovery_loop, 900),
    ]:
        mt = ManagedTask(name, coro, interval=interval)
        await mt.start()
        managed_tasks.append(mt)

    t.checkpoint("background_loops")

    # Discover plugins (bundled + user + project directories)
    # Phase-8 P1 #6: log the number of plugins loaded, and capture the
    # registry size delta as a proxy for "what was actually picked up".
    # Wrapped in try/except so a single broken plugin does not crash
    # startup (matches the existing graceful-degradation policy).
    try:
        from harness.hooks import discover_plugins, get_hook_registry
        _reg_before = sum(len(v) for v in get_hook_registry()._handlers.values())  # type: ignore[attr-defined]
        discover_plugins()
        _reg_after = sum(len(v) for v in get_hook_registry()._handlers.values())  # type: ignore[attr-defined]
        loaded = max(0, _reg_after - _reg_before)
        logger.info("discover_plugins: loaded %d plugin(s)", loaded)
    except Exception as exc:
        logger.warning("Plugin discovery failed: %s", exc)
    t.checkpoint("plugin_discovery")

    cronjob_tool = tool_registry.get("cronjob")
    if cronjob_tool:
        cronjob_tool.db = db
    test_exec_tool = tool_registry.get("test_executor")
    if test_exec_tool:
        test_exec_tool.db = db
    t.checkpoint("tool_wiring")

    # Backend factory — creates per-session execution environments
    # (LocalEnvironment, DockerEnvironment, SSHEnvironment) based
    # on sessions.backend_type and session_backend_configs.config.
    from harness.backends.factory import get_backend, resolve_backend_type

    def backend_factory(session_id, *, backend_type=None, config=None, cwd="", timeout=120, env=None):
        return get_backend(
            db, session_id,
            backend_type=backend_type, config=config,
            cwd=cwd, timeout=timeout, env=env,
        )

    app.state.backend_factory = backend_factory
    app.state.orchestrator_engine = OrchestratorEngine()

    # Wire the sudo password callback to the terminal read_password_thread
    try:
        from harness.backends.base import read_password_thread as _rpt
        from harness.backends.factory import set_sudo_password_callback as _set_spc
        _set_spc(_rpt)
    except Exception:
        pass

    # Wire backend_factory into tool modules so they can create
    # per-session backends without a sandbox_manager.
    try:
        from harness.tools.file_tools import set_backend_factory as _set_ft_bf
        _set_ft_bf(backend_factory)
    except Exception:
        pass
    try:
        from harness.tools.docker_tool import set_backend_factory as _set_dt_bf
        _set_dt_bf(backend_factory)
    except Exception:
        pass
    try:
        from harness.tools.execute_code import set_backend_factory as _set_ec_bf
        _set_ec_bf(backend_factory)
    except Exception:
        pass

    t.checkpoint("backend_factory")

    mcp_client = MCPClient()
    # Phase-8 P1 #5: wire the LLM router for MCP sampling support.
    # Without this call, MCP servers requesting ``sampling/createMessage``
    # get a stub "LLM not available" response and the entire sampling
    # subsystem is dead.
    try:
        mcp_client.set_llm(llm)
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("MCPClient.set_llm wiring failed: %s", exc)

    # Store DB reference for stream events module (already set above via set_db)

    # Sync mcp.json (filesystem source of truth) to DB on startup
    from harness.mcp.config_manager import load_config, sync_to_db
    file_servers = load_config()
    if file_servers:
        await sync_to_db(db, file_servers)
        mcp_rows = file_servers
    else:
        mcp_rows_data = await db.fetch("SELECT * FROM mcp_configs WHERE enabled = true")
        mcp_rows = [dict(r) for r in mcp_rows_data]

    if mcp_rows:
        mcp_servers = []
        for srv in mcp_rows:
            entry = {"id": srv.get("id", f"file-{srv['name']}"), "name": srv["name"], "url": srv.get("server_url", ""), "enabled": srv.get("enabled", True)}
            cfg_str = srv.get("config") or ""
            if cfg_str:
                try:
                    cfg = json.loads(cfg_str) if isinstance(cfg_str, str) else cfg_str
                    for k in ("command", "args", "env", "transport", "timeout", "connect_timeout"):
                        if k in cfg: entry[k] = cfg[k]
                except json.JSONDecodeError:
                    pass
            mcp_servers.append(entry)
        # MCP init as managed task (was fire-and-forget)
        async def _mcp_init():
            await mcp_client.initialize(mcp_servers)
        mcp_mt = ManagedTask("mcp-init", _mcp_init, interval=86400)
        await mcp_mt.start()
        managed_tasks.append(mcp_mt)
    t.checkpoint("mcp_client")

    from harness.delivery.router import DeliveryRouter
    delivery_router = DeliveryRouter(db=db)
    app.state.delivery_router = delivery_router
    t.checkpoint("delivery_router")

    base_deps = AgentDependencies(
        llm=llm, store=store, permissions=PermissionManager(mode="auto"),
        db=db, mcp=mcp_client,
    )

    def agent_factory(
        allowed_tools, session_id="",
        system_prompt_override=None, model_override=None, backend_factory=None,
        delegation=None, recipe_name="chat", max_tool_rounds=20,
    ) -> Agent:
        from harness.tools.toolsets import translate_short_tool_names
        allowed_tools = translate_short_tool_names(allowed_tools)
        agent = Agent(deps=base_deps, mode="auto", allowed_tools=allowed_tools, max_tool_rounds=max_tool_rounds,
                      system_prompt_override=system_prompt_override, model_override=model_override,
                      delegation=delegation, recipe_name=recipe_name)
        agent.session_id = session_id
        agent.context_compressor = context_compressor

        return agent
    app.state.agent_factory = agent_factory
    # Wire agent_factory to shared state for orchestrator use
    from harness.api.state import set_agent_factory as _set_af
    _set_af(agent_factory)
    logger.info("Agent factory set: %s", "yes" if agent_factory else "NO")
    t.checkpoint("agent_factory")

    # Kanban dispatcher — removed in favor of coordinator agent (Model B).
    # The coordinator (delegate_task) uses kanban tools to manage the
    # board directly via kanban_start/kanban_complete/kanban_block.
    # The reconcile-only Dispatcher below handles stale claims and
    # orphan sweep without conflicting with the coordinator's claims.
    # See hermès-agent kanban docs: one dispatcher for state, not workers.

    shared_bus = EventBus()
    shared_bus.add_sink(TraceCallbackSink(_trace_handler))
    shared_bus.add_sink(LogSink())
    event_source_sink = EventSourceSink()
    shared_bus.add_sink(event_source_sink)
    shared_bus.add_sink(StreamEventsDBSink())
    from harness.observability import register_observability_sinks
    register_observability_sinks(shared_bus)
    app.state.event_source_sink = event_source_sink
    base_deps = dataclasses.replace(base_deps, event_bus=shared_bus)
    from harness.api.state import set_event_bus, set_event_source_sink
    set_event_bus(shared_bus)
    # C03: expose the sink to non-FastAPI callers (BoardWaiter).
    set_event_source_sink(event_source_sink)
    t.checkpoint("event_bus")

    # Sync filesystem agent definitions to DB on startup
    try:
        from harness.agent_config import AgentStore
        from harness.store.adapters.postgres import PostgresAgentStore
        fs_store = AgentStore()
        agent_db = PostgresAgentStore(db)
        synced = await fs_store.sync_to_db(agent_db)
        logger.info("Synced %d agent definitions to DB", synced)
    except Exception as e:
        logger.warning("Agent sync failed (non-fatal): %s", e)
    t.checkpoint("agent_sync")

    agent = Agent(
        deps=base_deps, mode="chat",
        allowed_tools=list(CHAT_READONLY_TOOLSET),
    )
    agent.context_compressor = context_compressor
    scheduler = Scheduler(db, llm, agent_factory)
    scheduler.start()

    app.state.db = db
    app.state.llm = llm
    app.state.agent = agent
    app.state.mcp_client = mcp_client
    app.state.settings_store = settings_store
    app.state.store = store
    app.state.tool_registry = tool_registry
    app.state.scheduler = scheduler

    # C2.1: TestPlan store. The Postgres adapter is a follow-up
    # (`test_plan.py:25-28`); for now we wire a process-local
    # `InMemoryTestPlanStore` so the HTTP routes in
    # `routers/test_plans.py` are immediately usable. Mirrors the
    # "one store per domain" convention used by settings_store,
    # kanban_store, etc.
    try:
        from harness.test_plan import InMemoryTestPlanStore
        app.state.test_plan_store = InMemoryTestPlanStore()
    except Exception as e:
        logger.warning("TestPlan store init failed (non-fatal): %s", e)
    t.checkpoint("scheduler_start")

    try:
        from harness.services.kanban_service import start_review_agent
        start_review_agent(app)
    except Exception as e:
        logger.warning("Review agent not started: %s", e)
    # P0 audit fix 2026-06-23: run the artifact janitor on a 24h
    # schedule. Implements the documented retention policy
    # (committed test files = permanent, trajectories = 30d, LLM
    # transcripts = 7d). See ``harness/services/artifact_janitor.py``.
    try:
        from harness.services.artifact_janitor import run_janitor_once, run_periodic
        janitor_interval = int(os.environ.get("ARTIFACT_JANITOR_INTERVAL_SECONDS", str(24 * 3600)))
        async def _janitor_loop():
            await run_periodic(db, interval_seconds=janitor_interval)
        janitor_mt = ManagedTask("artifact_janitor", _janitor_loop, interval=janitor_interval)
        await janitor_mt.start()
        managed_tasks.append(janitor_mt)
        # Run once at startup so a long-lived restart benefits immediately.
        try:
            initial = await run_janitor_once(db)
            logger.info("artifact janitor initial pass: %s", initial)
        except Exception as e:
            logger.warning("artifact janitor initial pass failed: %s", e)
    except Exception as e:
        logger.warning("Artifact janitor not started: %s", e)
    # C02: team auto-sweeper — auto-dissolves teams where every
    # member has finished. Mirrors the kanban review agent pattern.
    try:
        from harness.services.team_sweeper import start_team_sweeper
        start_team_sweeper(app)
    except Exception as e:
        logger.warning("Team sweeper not started: %s", e)
    # Kanban dispatcher removed in favor of coordinator agent (Model B).
    # The kanban API (board/task CRUD) remains for human visibility in the UI.
    # The dispatcher's worker-spawning role is replaced by the coordinator
    # agent which uses delegate_task + todo for task management.
    #
    # Q4-D: 60s reconciliation dispatcher. The previous kanban dispatcher
    # spawned workers; this one only reconciles state (reclaims stale
    # claims, auto-blocks spin-loops, sweeps orphans). The coordinator
    # agent still owns work creation; the dispatcher is the structural
    # fix for the orphan-task problem (e2e4: coordinator finished but
    # left an `in_progress` task). See harness/dispatcher.py.
    dispatcher = None
    try:
        from harness.dispatcher import Dispatcher
        # 60s tick by default; lower for E2E tests via env var.
        interval = float(os.environ.get("TESTAI_DISPATCHER_INTERVAL_SECONDS", "60"))
        dispatcher = Dispatcher(db, sweep_interval_seconds=interval)
        await dispatcher.start()
        app.state.dispatcher = dispatcher
        logger.info("dispatcher started (interval=%.1fs)", interval)
    except Exception as e:
        logger.warning("Dispatcher not started: %s", e)

    # Memory monitor — periodic RSS logging for leak detection (Hermes pattern)
    try:
        from harness.services.memory_monitor import start as start_mem_monitor
        start_mem_monitor(interval_seconds=300)
        logger.info("[MEMORY] memory monitor started (interval=300s)")
    except Exception as e:
        logger.debug("[MEMORY] memory monitor not started: %s", e)

    # Shutdown forensics — capture process state on SIGTERM/SIGINT
    try:
        from harness.services.shutdown_forensics import install_shutdown_handler
        install_shutdown_handler()
        logger.info("[FORENSICS] shutdown handler installed")
    except Exception as e:
        logger.debug("[FORENSICS] shutdown handler not installed: %s", e)

    logger.info("\n" + t.report())
    yield

    # Shutdown — stop all managed tasks, cleanup backends, then infrastructure
    try:
        from harness.backends.factory import shutdown_factory
        shutdown_factory()
    except Exception:
        pass
    for mt in reversed(managed_tasks):
        try:
            await mt.stop()
        except Exception as e:
            logger.warning("ManagedTask '%s' stop error: %s", mt.name, e)
    try:
        if dispatcher is not None:
            await dispatcher.stop()
    except Exception as e:
        logger.warning("dispatcher stop error: %s", e)
    try:
        if scheduler is not None:
            await scheduler.stop()
    except Exception as e:
        logger.warning("scheduler stop error: %s", e)
    try:
        await db.disconnect()
    except Exception as e:
        logger.warning("db disconnect error: %s", e)


app = FastAPI(
    title="TestAI Harness",
    lifespan=lifespan,
)

# CORS: allow all origins for local dev (frontend on :3001 talks to backend on :8001)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def root_health():
    return {"status": "ok"}

@app.get("/api/debug/registry")
async def debug_registry():
    from harness.tools.registry import registry as _r
    entries = _r.list_entries()
    return {
        "entries": len(entries),
        "names": sorted([e.name for e in entries]),
        "has_delegate_task": _r.get("delegate_task") is not None,
    }
for r in agent_routers:
    app.include_router(r)
for r in settings_routers:
    app.include_router(r)
for r in admin_routers:
    app.include_router(r)
for r in integration_routers:
    app.include_router(r)
# C05: A2A server. `agent_card_router` serves
# `/.well-known/agent.json` (the spec-mandated discovery
# location); `a2a_router` mounts under `/a2a/...` for
# JSON-RPC + SSE.
app.include_router(agent_card_router)
app.include_router(a2a_router)
# F04: observability status (OTel opt-in + span counts).
from .routers.observability import router as observability_router
app.include_router(observability_router)
# Q3 / Q6: chat surface (REST + SSE).
from .routers.chat import router as chat_router
app.include_router(chat_router)
# Phase 2: repo summary endpoint (read-side entry point).
from .routers.repos import router as repos_router
app.include_router(repos_router)

# F3: sandbox visibility surface (12+ read/write endpoints).
from .routers.sandbox import router as sandbox_router
app.include_router(sandbox_router)
# C08 / history: runs + sessions + coverage API.
from .routers.runs import router as runs_router
app.include_router(runs_router)
# Delegate API (SSE stream + actions for live runs).
from .routers.delegate import router as delegate_router
app.include_router(delegate_router)
# Phase 3: persistent memory add + search (Mem0 shape).
from .routers.memory import router as memory_router
app.include_router(memory_router)
# Kanban board API (used by the dashboard's kanban view).
from .routers.kanban import router as kanban_router
app.include_router(kanban_router)
# Dashboard widgets API (KPI cards, aggregation endpoints).
from .routers.dashboard_api import router as dashboard_router
app.include_router(dashboard_router)
# Digest/pipeline-summary API (morning-report style aggregation).
from .routers.digest_api import router as digest_router
app.include_router(digest_router)
# Artifacts API (per-session file metadata + download).
from .routers.artifacts_api import router as artifacts_router
app.include_router(artifacts_router)

from .routers.search_providers import router as search_providers_router
app.include_router(search_providers_router)

from .routers.slash_commands import router as slash_commands_router
app.include_router(slash_commands_router)

from .routers.evaluate_api import router as evaluate_router
app.include_router(evaluate_router)

from .routers.notifications import router as notifications_router
app.include_router(notifications_router)

from .routers.audit import router as audit_router
app.include_router(audit_router)

from .routers.blueprints import router as blueprints_router
app.include_router(blueprints_router)

from .routers.workflows import router as workflows_router
app.include_router(workflows_router)



