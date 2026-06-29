"""KnowledgeGraphSyncer &mdash; per-run KG index + restore + sync + provenance.

Wire of C03 (orchestrator decomposition), Phase 4. The original
``harness.orchestrator.OrchestratorEngine.run_single`` had two
blocks that shared the same ``(sandbox, repo_path, host_dir)``
tuple:

- **Pre-coordinator index** (lines 321-373): restore from
  host cache if the volume is fresh, build the KG, mirror
  the DB to host, write provenance.
- **Post-coordinator sync** (lines 599-624): run ``codegraph
  sync`` so the host cache reflects the agent's edits,
  re-read the status, re-mirror to host, rewrite provenance.

Both blocks share the same data &mdash; graph_id, host_dir,
prior_db_host, the same codegraph primitives &mdash; but
they're separated by ~200 lines of orchestrator code. The
:class:`KnowledgeGraphSyncer` is the named collaborator that
holds the shared context (graph_id, host_dir) and exposes
the two operations.

The class is stateless &mdash; all "state" is the
``SandboxKGContext`` dataclass that's built once at the
top of ``run_single`` and passed to each method.

Per :mod:`CONTEXT.md` glossary:
- **KnowledgeGraphSyncer** &mdash; this module
- **SandboxKGContext** &mdash; the per-run config bundle
- **index** &mdash; pre-coordinator: restore + build + mirror + provenance
- **sync** &mdash; post-coordinator: incremental sync + mirror + provenance
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# ContextVar so the orchestrator can attach a ``SandboxKGContext`` to
# the subagent it spawns via delegate_task. The orchestrator calls
# ``set_current_kg_context(ctx)`` in ``run_single`` after building
# the context; the ``kg_refresh`` tool (which runs in a subagent)
# reads ``get_current_kg_context()`` to call ``KnowledgeGraphSyncer.sync``.
# Mirrors the budget_tracker pattern at ``harness/budget_tracker.py``.
_CURRENT_KG_CONTEXT: ContextVar["SandboxKGContext | None"] = ContextVar(
    "_CURRENT_KG_CONTEXT", default=None
)


def get_current_kg_context() -> "SandboxKGContext | None":
    """Read the current orchestrator's SandboxKGContext, if any.

    Returns None if the tool is called outside an orchestrator run
    (e.g., a test, a chat-only flow).
    """
    return _CURRENT_KG_CONTEXT.get()


def set_current_kg_context(ctx: "SandboxKGContext | None"):
    """Set the current orchestrator's SandboxKGContext.

    Returns a contextvars Token; pair with ``reset_current_kg_context(token)``
    in a finally block. Mirrors ``set_current_tracker``.
    """
    return _CURRENT_KG_CONTEXT.set(ctx)


def reset_current_kg_context(token) -> None:
    """Reset the SandboxKGContext contextvar. Pair with set_current_kg_context."""
    _CURRENT_KG_CONTEXT.reset(token)


@dataclass(frozen=True)
class SandboxKGContext:
    """The per-run config bundle for the KG syncer.

    The original ``run_single`` computed these values inline
    and threaded them through both blocks. This dataclass
    makes the bundle explicit so ``index`` and ``sync`` can
    each take one argument.
    """
    repo_url: str
    branch: str
    session_id: str
    graph_id: str
    host_dir: str
    prior_db_host: str

    @staticmethod
    def build(
        repo_url: str,
        branch: str,
        session_id: str,
    ) -> "SandboxKGContext":
        """Build the context for a run. Mirrors the inline computation in ``run_single``.

        ``graph_id`` is the per-repo hash from
        :func:`harness.codegraph.repo_graph_id`. ``host_dir``
        is the per-graph host path the frontend reads from.
        ``prior_db_host`` is the absolute host path to the
        previous DB snapshot (the disaster-recovery fallback).
        """
        from harness.codegraph import repo_graph_id
        graph_id = repo_graph_id(repo_url, branch or "main")
        host_dir = f"agent_workspace/knowledge-graphs/{graph_id}"
        prior_db_host = f"/app/{host_dir}/codegraph.db"
        return SandboxKGContext(
            repo_url=repo_url,
            branch=branch or "main",
            session_id=session_id,
            graph_id=graph_id,
            host_dir=host_dir,
            prior_db_host=prior_db_host,
        )


class KnowledgeGraphSyncer:
    """Pre-coordinator index + post-coordinator sync for the per-run KG.

    Stateless; methods are static. The two operations
    (index, sync) are the only public surface; the helper
    methods are private because they encode the policy
    decisions that are easy to break if changed.
    """

    #: Default timeout for the initial index. Cold index of a
    #: 5,000-symbol repo takes 4-6 minutes; 600s gives
    #: headroom. The post-coordinator sync uses a shorter
    #: timeout because it's incremental.
    DEFAULT_INDEX_TIMEOUT_SECONDS: ClassVar[int] = 600

    #: Timeout for the post-coordinator sync. ``codegraph sync``
    #: is incremental so it should be fast; 60s is a safety
    #: margin (a 10,000-edit change is the worst case).
    DEFAULT_SYNC_TIMEOUT_SECONDS: ClassVar[int] = 60

    # ------------------------------------------------------------------
    # Pre-coordinator: build the KG so the agent starts with one.
    # ------------------------------------------------------------------

    @staticmethod
    async def index(
        sandbox: Any,
        repo_path: str,
        ctx: SandboxKGContext,
        timeout_seconds: int | None = None,
    ) -> dict:
        """Restore from host, build, mirror to host, write provenance.

        Returns the ``codegraph`` index result dict
        (``{success, nodeCount, edgeCount, symbols, files,
        ...}``). Failures in any of the 4 steps are
        downgraded to a log line; the function still returns
        the partial result so the orchestrator can proceed.
        The agent can still run on a repo without a KG
        &mdash; it just won't have the cross-file context.

        Steps (matches the original ``run_single`` lines 321-373):
        1. Check whether the sandbox volume already has a
           non-empty KG. If not and the host cache exists,
           restore the host DB into the sandbox.
        2. Run ``codegraph init --index`` (the underlying
           primitive handles stale-DB detection).
        3. Mirror the freshly-built DB to the host cache.
        4. Write provenance so the frontend can show the
           graph in the UI.
        """
        from harness.codegraph import (
            index_project,
            copy_db_to_host,
            restore_db_from_host,
            write_provenance,
            get_status as _cg_status,
        )

        timeout = timeout_seconds or KnowledgeGraphSyncer.DEFAULT_INDEX_TIMEOUT_SECONDS

        # 1. Check staleness against host cache. If the repo has
        #    newer commits than the last index, skip the host restore
        #    and rebuild from scratch.
        skip_restore = False
        try:
            provenance_path = os.path.join(ctx.host_dir, "provenance.json")
            if os.path.exists(provenance_path):
                import json
                with open(provenance_path) as f:
                    prov = json.load(f)
                last_indexed = prov.get("last_indexed_at")
                if last_indexed and os.path.exists(ctx.prior_db_host):
                    git_date = await sandbox.run(
                        "cd %s && git log -1 --format=%%cI HEAD 2>/dev/null || echo ''" % repo_path,
                        timeout=15,
                    )
                    git_ts = (git_date.stdout or "").strip() if git_date.returncode == 0 else ""
                    if git_ts and git_ts <= str(last_indexed):
                        skip_restore = True  # host cache is fresh enough
        except Exception as exc:
            logger.debug("KG staleness check failed (non-fatal): %s", exc)

        # 2. Restore from host if the volume is fresh and host cache is not stale.
        try:
            existing = await _cg_status(sandbox, repo_path)
            has_nodes = (
                existing.get("nodeCount") or existing.get("symbols") or 0
            ) > 0
            if not has_nodes and os.path.exists(ctx.prior_db_host) and not skip_restore:
                await restore_db_from_host(sandbox, ctx.prior_db_host, repo_path)
        except Exception as exc:
            logger.debug("KG restore-from-host failed (non-fatal): %s", exc)

        # 2. Build (or rebuild) the KG.
        kg = await index_project(sandbox, repo_path, timeout=timeout)

        # 3. Mirror to host + 4. provenance.
        if kg.get("success"):
            await copy_db_to_host(sandbox, repo_path, ctx.host_dir)
            try:
                write_provenance(
                    ctx.host_dir,
                    repo_url=ctx.repo_url or "",
                    branch=ctx.branch,
                    graph_id=ctx.graph_id,
                    source_session_id=ctx.session_id,
                    node_count=kg.get("nodeCount") or kg.get("symbols"),
                    edge_count=kg.get("edgeCount"),
                )
            except Exception as exc:
                logger.debug("KG provenance write failed (non-fatal): %s", exc)

        return kg

    # ------------------------------------------------------------------
    # Post-coordinator: incremental sync after the agent edited files.
    # ------------------------------------------------------------------

    @staticmethod
    async def sync(
        sandbox: Any,
        repo_path: str,
        ctx: SandboxKGContext,
        timeout_seconds: int | None = None,
    ) -> dict:
        """Run ``codegraph sync`` so the host cache reflects the agent's edits.

        Returns the fresh status dict (``{nodeCount, edgeCount,
        ...}``) or ``{}`` if the sync failed. The function
        never raises; sync failures are non-fatal because the
        next run's restore-from-host step will rebuild from
        the prior snapshot.

        Matches the original ``run_single`` lines 599-624.
        """
        from harness.codegraph import (
            _run_in_sandbox as _cg_run,
            copy_db_to_host,
            get_status as _cg_status,
            write_provenance,
        )

        timeout = timeout_seconds or KnowledgeGraphSyncer.DEFAULT_SYNC_TIMEOUT_SECONDS
        try:
            sync_result = await _cg_run(sandbox, ["sync", repo_path], timeout=timeout)
            if not sync_result or sync_result.returncode != 0:
                return {}
            fresh = await _cg_status(sandbox, repo_path)
            await copy_db_to_host(sandbox, repo_path, ctx.host_dir)
            write_provenance(
                ctx.host_dir,
                repo_url=ctx.repo_url or "",
                branch=ctx.branch,
                graph_id=ctx.graph_id,
                source_session_id=ctx.session_id,
                node_count=fresh.get("nodeCount") or fresh.get("symbols"),
                edge_count=fresh.get("edgeCount"),
            )
            logger.info(
                "KG synced after coordinator: %s nodes, %s edges",
                fresh.get("nodeCount", "?"), fresh.get("edgeCount", "?"),
            )
            return fresh
        except Exception as exc:
            logger.debug("post-coordinator KG sync failed (non-fatal): %s", exc)
            return {}
