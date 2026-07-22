"""CoordinatorSpawnPhase &mdash; spawn the coordinator agent and capture its result.

C09: extracted from ``OrchestratorEngine.run_single``. This is
the *coding agent* in Anthropic's two-agent pattern (the
initializer agent is the earlier SandboxPreparePhase + clone +
bootstrap + worktree + KG). The coordinator drives the actual
work: it reads the goal + the board + the explore findings and
spawns subagents via ``delegate_task``.

The phase attaches the coordinator's raw result to
``ctx.coordinator_result["raw_result"]`` and the
budget/board contextvars to the orchestrator's state. The
final ``RunResult`` is built by the orchestrator after the
pipeline returns.
"""
from __future__ import annotations

import asyncio
import logging
import os

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class CoordinatorSpawnPhase(RunPhase):
    """Spawn the coordinator agent and capture its result."""

    phase_name = "coordinator_spawn"
    can_skip = False  # the whole point of the run

    async def execute(self, ctx: RunContext) -> RunContext:
        orchestrator = ctx.orchestrator
        if orchestrator is None:
            raise RuntimeError("CoordinatorSpawnPhase requires orchestrator")

        from dataclasses import replace
        from harness.tools.registry import registry

        # Always use the registry singleton — it has backend_factory,
        # event_bus, and all infrastructure properly wired.
        # Creating a fresh DelegateTaskTool(agent_factory=...) misses
        # _backend_factory and causes child agents to fail silently.
        dt = registry.get("delegate_task")
        if not dt or not hasattr(dt, "run"):
            raise RuntimeError("delegate_task not available")

        # Attach orchestrator session_id so the delegate_task tool
        # can parent subagent sessions in the sessions table.
        dt._session_id = ctx.session_id
        # Propagate continue_on_failure to the delegate task tool so
        # spawned subagents don't abort the entire batch on error.
        dt._continue_on_failure = bool(ctx.test_config and ctx.test_config.get("continue_on_failure"))

        # Build the coordinator's goal string.
        memory_section = (
            f"\nCROSS-RUN MEMORY (from previous sessions):\n"
            f"{ctx.memory_block}\n"
            if ctx.memory_block else ""
        )
        kg_node_count = (
            getattr(getattr(ctx, "kg_ctx", None), "node_count", 0) or 0
        )
        try:
            from harness.agent_discovery import get_agent
            orch_agent = get_agent("orchestrator")
            orch_body = (
                orch_agent.prompt
                if orch_agent and orch_agent.prompt
                else (
                    "You are a coordinator. Spawn 5+ workers in parallel using "
                    "fan-out mode (delegate_task with tasks array). Never write "
                    "code yourself — delegate all work to specialist agents."
                )
            )
        except Exception:
            orch_body = (
                "You are a coordinator. Spawn 5+ workers in parallel using "
                "fan-out mode (delegate_task with tasks array). Never write "
                "code yourself — delegate all work to specialist agents."
            )

        coord_goal = (
            f"{orch_body}\n\n"
            f"REPO: {ctx.repo_url} (branch: {ctx.branch or 'main'})\n"
            f"WORKSPACE: /workspace/repo  KG: {kg_node_count} symbols\n"
            f"KANBAN BOARD: {ctx.board_id or 'not created'}\n\n"
            f"## GOAL\n\n{ctx.goal}\n\n"
            f"## Explore findings\n"
            f"{ctx.explore_findings[:3000] if ctx.explore_findings else 'No explore data'}"
            f"{memory_section}"
        )

        # Inject advanced pipeline config into the goal if present
        if ctx.test_config:
            tc = ctx.test_config
            config_lines = ["\n## Advanced Pipeline Configuration\n"]
            if tc.get("timeout_seconds"):
                config_lines.append(f"- Timeout: {tc['timeout_seconds']}s per command")
            if tc.get("max_retries"):
                config_lines.append(f"- Max retries: {tc['max_retries']}")
            if tc.get("retry_on_failure") is False:
                config_lines.append("- Retry on failure: DISABLED")
            if tc.get("fail_fast"):
                config_lines.append("- Fail fast: YES (stop on first failure)")
            if tc.get("parallelism") and tc["parallelism"] > 1:
                config_lines.append(f"- Parallelism: {tc['parallelism']} containers")
            if tc.get("shard_count") and tc["shard_count"] > 1:
                config_lines.append(f"- Shards: {tc['shard_count']}")
            if tc.get("pre_commands"):
                config_lines.append(f"- Pre-commands: {', '.join(tc['pre_commands'])}")
            if tc.get("post_commands"):
                config_lines.append(f"- Post-commands: {', '.join(tc['post_commands'])}")
            if tc.get("os"):
                config_lines.append(f"- Target OS: {tc['os']}")
            if tc.get("runtime_version"):
                config_lines.append(f"- Runtime: {tc['runtime_version']}")
            if tc.get("browser"):
                config_lines.append(f"- Browser: {tc['browser']}")
            if tc.get("cache_directories"):
                config_lines.append(f"- Cache dirs: {', '.join(tc['cache_directories'])}")
            if tc.get("artifact_paths"):
                config_lines.append(f"- Artifact paths: {', '.join(tc['artifact_paths'])}")
            if tc.get("auto_commit"):
                config_lines.append(f"- Auto-commit: YES (branch: {tc.get('commit_branch', 'main')})")
            if tc.get("tags"):
                config_lines.append(f"- Tags: {', '.join(tc['tags'])}")
            if tc.get("continue_on_failure"):
                config_lines.append("- Continue on failure: YES (other agents continue if one fails)")
            if tc.get("notification_channels"):
                channels = tc["notification_channels"]
                if isinstance(channels, list) and channels:
                    config_lines.append(f"- Notifications: {', '.join(channels)}")
            coord_goal += "\n".join(config_lines)

        # Set up the per-run budget tracker and KG context (the
        # subagents spawned by the coordinator read these).
        budget_tracker, budget_token = self._setup_budget_tracker(ctx, dt)
        kg_ctx_token = self._setup_kg_context(ctx)
        prev_board_env = self._set_board_env(ctx)

        # Execute pre-commands if specified in advanced config
        if ctx.test_config and ctx.test_config.get("pre_commands"):
            sandbox = ctx.sandbox or getattr(ctx.orchestrator, "_sandbox", None)
            if sandbox:
                for cmd in ctx.test_config["pre_commands"]:
                    try:
                        logger.info("Pre-command: %s", cmd)
                        await sandbox.run(cmd, timeout=120)
                    except Exception as exc:
                        logger.warning("Pre-command failed (continuing): %s: %s", cmd, exc)

        try:
            model = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")
            result = await dt.run(
                goal=coord_goal,
                toolsets=["coordinator"],
                role="orchestrator",
                model=model,
                max_tool_rounds=50,
            )
        finally:
            self._reset_budget(budget_token)
            self._reset_kg_context(kg_ctx_token)
            self._restore_board_env(prev_board_env)

        # Execute post-commands if specified in advanced config
        if ctx.test_config and ctx.test_config.get("post_commands"):
            sandbox = ctx.sandbox or getattr(ctx.orchestrator, "_sandbox", None)
            if sandbox:
                for cmd in ctx.test_config["post_commands"]:
                    try:
                        logger.info("Post-command: %s", cmd)
                        await sandbox.run(cmd, timeout=120)
                    except Exception as exc:
                        logger.warning("Post-command failed (continuing): %s: %s", cmd, exc)

        # Attach the raw result + budget snapshot to coordinator_result.
        coordinator_result = dict(ctx.coordinator_result or {})
        coordinator_result["raw_result"] = result
        if budget_tracker is not None and hasattr(budget_tracker, "snapshot"):
            try:
                snap = budget_tracker.snapshot()
                coordinator_result["budget_snapshot"] = {
                    "run_id": snap.run_id,
                    "session_id": snap.session_id,
                    "spent_usd": snap.spent_usd,
                    "soft_cap_usd": snap.soft_cap_usd,
                    "hard_cap_usd": snap.hard_cap_usd,
                    "throttle_step": snap.throttle_step,
                    "hitl_active": snap.hitl_active,
                    "sequential_active": snap.sequential_active,
                    "cheaper_model_active": snap.cheaper_model_active,
                    "pause_requested": snap.pause_requested,
                    "n_llm_calls": snap.n_llm_calls,
                    "n_tool_calls": snap.n_tool_calls,
                }
            except Exception as exc:
                logger.debug("budget snapshot in phase failed: %s", exc)
        return replace(ctx, coordinator_result=coordinator_result)

    def _setup_budget_tracker(self, ctx: RunContext, dt: Any) -> Any:
        try:
            from harness.budget_tracker import (
                BudgetTracker, set_current_tracker,
            )
            tracker = BudgetTracker(
                run_id=ctx.run_id, session_id=ctx.session_id,
                spec_id=ctx.spec_id,
            )
            token = set_current_tracker(tracker)
            setattr(dt, "_budget_tracker", tracker)
            return tracker, token
        except Exception as exc:
            logger.debug("budget tracker attach failed: %s", exc)
            return None, None

    def _reset_budget(self, token: Any) -> None:
        if token is None:
            return
        try:
            from harness.budget_tracker import reset_current_tracker
            reset_current_tracker(token)
        except Exception:
            pass

    def _setup_kg_context(self, ctx: RunContext) -> Any:
        if ctx.kg_ctx is None:
            return None
        try:
            from harness.services.knowledge_graph_syncer import (
                set_current_kg_context,
            )
            return set_current_kg_context(ctx.kg_ctx)
        except Exception as exc:
            logger.debug("kg context attach failed: %s", exc)
            return None

    def _reset_kg_context(self, token: Any) -> None:
        if token is None:
            return
        try:
            from harness.services.knowledge_graph_syncer import (
                reset_current_kg_context,
            )
            reset_current_kg_context(token)
        except Exception:
            pass

    def _set_board_env(self, ctx: RunContext) -> Any:
        if not ctx.board_id:
            return None
        try:
            prev = os.environ.get("TESTAI_KANBAN_BOARD")
            os.environ["TESTAI_KANBAN_BOARD"] = ctx.board_id
            return prev
        except Exception:
            return None

    def _restore_board_env(self, prev: Any) -> None:
        if prev is None and "TESTAI_KANBAN_BOARD" not in os.environ:
            return
        try:
            if prev is None:
                os.environ.pop("TESTAI_KANBAN_BOARD", None)
            else:
                os.environ["TESTAI_KANBAN_BOARD"] = prev
        except Exception:
            pass
