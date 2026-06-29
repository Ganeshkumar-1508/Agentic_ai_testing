"""kg_refresh tool — coordinator-callable KG re-index trigger.

Replaces the simpler ``KGRefreshTool`` previously defined in
``knowledge_graph_tool.py``. That tool ran ``codegraph sync`` directly,
returned only the new symbol/file count, and had no debounce, no delta
computation, no event emission, and no failure categorization. Per the
C04 design (see ``docs/2026-06-21-architecture-decision-tree.md``), this
new tool:

  - Always calls ``KnowledgeGraphSyncer.sync`` (which runs
    ``codegraph sync``, copies the DB to the host, and writes
    ``provenance.json``). The previous tool skipped the copy and the
    provenance write — both are needed for the dashboard.
  - Returns a status + delta dict: ``{nodeCount, edgeCount, delta:
    {added, removed, modified}, duration_ms, last_refresh_at}`` (or a
    debounce-skipped response, or a categorized error).
  - Hard-debounces 60 s by default; ``force=true`` bypasses the
    debounce. Configurable via ``KG_REFRESH_DEBOUNCE_SECONDS`` env.
  - Emits a ``kg.refreshed`` event on the EventBus / ``stream_events``
    table so the dashboard can show the header pill + the panel.
  - Categorizes failures (sync_failed, timeout, copy_failed,
    sandbox_unreachable) and reports ``recoverable: true|false``.

Coordinator-only: the leaf-worker allowed-tools set in
``harness/tools/delegate_task.py`` does NOT include ``kg_refresh`` —
so bug-fixer / test-writer subagents cannot thrash the syncer. The
tool is registered for the ``coordinator`` and ``bug-fixer`` toolsets
(matching the pre-C04 wiring at ``toolsets.py:134`` and ``toolsets.py:159``).

In-process state is per-tool-instance (the registry holds one
``KgRefreshTool`` singleton). The orchestrator's
``OrchestratorEngine.run_single`` calls ``_seed_baseline()`` after the
post-coordinator sync so the first in-run ``kg_refresh`` call computes
a delta against the just-finished state, not against the (potentially
stale) initial index. See ``orchestrator.py:_seed_baseline`` call
site.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_SECONDS = 60.0
_DEBOUNCE_ENV_VAR = "KG_REFRESH_DEBOUNCE_SECONDS"


class KgRefreshError(RuntimeError):
    """Categorized error raised by ``kg_refresh``.

    The tool catches this in its ``run`` and converts to a
    ``ToolResult(success=False, data={...})`` with the category,
    duration, and ``recoverable`` flag the LLM needs to decide
    next steps.
    """

    def __init__(
        self,
        category: str,
        message: str,
        *,
        recoverable: bool = True,
        duration_ms: int = 0,
        last_known_good: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.recoverable = recoverable
        self.duration_ms = duration_ms
        self.last_known_good = last_known_good

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "error": str(self),
            "category": self.category,
            "recoverable": self.recoverable,
            "duration_ms": self.duration_ms,
            "last_known_good": self.last_known_good,
        }


class KgRefreshTool(BaseTool):
    """Coordinator-callable: re-index the KG so subsequent codegraph_*
    queries see the latest state.

    The default debounce is 60 s. Pass ``force=true`` to bypass.
    The tool is non-side-effecting at the source-code level: it only
    refreshes an index, not edits a file. So it is ``default_level =
    "allow"`` (no HITL prompt).
    """

    name = "kg_refresh"
    description = (
        "Re-index the knowledge graph so subsequent `codegraph_*` "
        "queries see the latest state. Runs `codegraph sync` "
        "incrementally (mtime-based, fast — usually 1-10 seconds). "
        "Returns the new node/edge counts and a delta vs the last "
        "successful refresh in this run. The tool debounces: a "
        "second call within 60 seconds of the previous one returns "
        "`{skipped: true, last_refresh_age_seconds: N}` without "
        "running sync. Pass `force=true` to bypass the debounce "
        "(e.g. when you need to verify that an edit took effect "
        "before running a codegraph_search). The tool is "
        "coordinator-only — leaf workers (bug-fixer, test-writer) "
        "do not inherit it."
    )
    default_level = "allow"
    capabilities = ["can_write_kg"]

    def __init__(self) -> None:
        super().__init__()
        # In-process state. The tool is a singleton (registered once
        # in the registry), so this state is process-wide. The
        # orchestrator's run_single resets it via _seed_baseline.
        self._last_refresh_at: float = 0.0
        self._last_status: dict[str, Any] | None = None
        self._last_baseline_source: str = "uninitialized"
        self._lock = asyncio.Lock()
        self._debounce_seconds: float = self._read_debounce_seconds()

    @staticmethod
    def _read_debounce_seconds() -> float:
        try:
            raw = os.environ.get(_DEBOUNCE_ENV_VAR, "").strip()
            if raw:
                return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
        return _DEFAULT_DEBOUNCE_SECONDS

    # ------------------------------------------------------------------
    # Public surface for the orchestrator
    # ------------------------------------------------------------------

    def _seed_baseline(self, status: dict[str, Any]) -> None:
        """Seed the tool's "last known" state after the orchestrator's
        post-coordinator sync. Idempotent: safe to call multiple times
        in a run; the most recent status wins.

        The orchestrator's run_single calls this in the post-coordinator
        sync block (``orchestrator.py:run_single``), so the first
        in-run ``kg_refresh`` call computes a delta against the
        just-finished state, not against the (potentially stale)
        initial index.
        """
        if not status:
            return
        self._last_status = {
            "nodeCount": status.get("nodeCount") or status.get("symbols") or 0,
            "edgeCount": status.get("edgeCount") or 0,
            "fileCount": status.get("fileCount") or status.get("files") or 0,
        }
        # Use the post-sync status as the time anchor so a subsequent
        # kg_refresh call within the debounce window is skipped
        # against this same baseline — the LLM can read
        # last_refresh_age_seconds and know the baseline is the
        # post-coordinator state.
        self._last_refresh_at = time.monotonic()
        self._last_baseline_source = "orchestrator_post_sync"

    # ------------------------------------------------------------------
    # Tool spec + run
    # ------------------------------------------------------------------

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Bypass the 60s debounce. Use when you need "
                            "to verify that a recent edit was picked up "
                            "by the KG before running a codegraph_search."
                        ),
                    },
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        force = bool(kwargs.get("force", False))
        start = time.monotonic()
        async with self._lock:
            last_refresh_at = self._last_refresh_at
        elapsed = start - last_refresh_at if last_refresh_at > 0 else float("inf")

        # ------------------------------------------------------------------
        # 1. Debounce gate
        # ------------------------------------------------------------------
        if not force and last_refresh_at > 0 and elapsed < self._debounce_seconds:
            return ToolResult(
                success=True,
                output=json.dumps(
                    {
                        "skipped": True,
                        "last_refresh_age_seconds": int(elapsed),
                        "force_available": True,
                        "message": (
                            f"Refusing to refresh; last refresh was "
                            f"{int(elapsed)}s ago "
                            f"(< debounce {int(self._debounce_seconds)}s). "
                            f"Pass force=true to override."
                        ),
                    }
                ),
                data={
                    "skipped": True,
                    "last_refresh_age_seconds": int(elapsed),
                    "force_available": True,
                },
            )

        # ------------------------------------------------------------------
        # 2. Resolve sandbox + KG context
        # ------------------------------------------------------------------
        from harness.codegraph import get_sandbox_env

        env = await get_sandbox_env()
        if env is None:
            err = KgRefreshError(
                category="sandbox_unreachable",
                message="No active sandbox environment for this session.",
                recoverable=False,
                duration_ms=int((time.monotonic() - start) * 1000),
                last_known_good=self._last_status,
            )
            return self._failure_result(err)

        from harness.services.knowledge_graph_syncer import (
            KnowledgeGraphSyncer,
            get_current_kg_context,
        )

        kg_ctx = get_current_kg_context()
        if kg_ctx is None:
            err = KgRefreshError(
                category="sandbox_unreachable",
                message=(
                    "No KG context attached to this run. kg_refresh must "
                    "be called from inside an orchestrator run. If you "
                    "are the coordinator of a Run, this is a bug."
                ),
                recoverable=False,
                duration_ms=int((time.monotonic() - start) * 1000),
                last_known_good=self._last_status,
            )
            return self._failure_result(err)

        # ------------------------------------------------------------------
        # 3. Run sync (handles DB copy + provenance)
        # ------------------------------------------------------------------
        try:
            fresh = await KnowledgeGraphSyncer.sync(
                env, "/workspace/repo", kg_ctx
            )
        except asyncio.TimeoutError as exc:
            err = KgRefreshError(
                category="timeout",
                message=f"codegraph sync timed out: {exc}",
                recoverable=True,
                duration_ms=int((time.monotonic() - start) * 1000),
                last_known_good=self._last_status,
            )
            return self._failure_result(err)
        except Exception as exc:
            # ``KnowledgeGraphSyncer.sync`` is designed not to raise
            # (it returns {} on failure). If it does raise, the
            # orchestrator's connection is likely severed —
            # categorize as sandbox_unreachable.
            err = KgRefreshError(
                category="sandbox_unreachable",
                message=f"sync raised unexpectedly: {exc}",
                recoverable=False,
                duration_ms=int((time.monotonic() - start) * 1000),
                last_known_good=self._last_status,
            )
            return self._failure_result(err)

        if not fresh:
            # ``KnowledgeGraphSyncer.sync`` returns {} on failure but
            # never raises; surface a categorized error here so the
            # LLM can react.
            err = KgRefreshError(
                category="sync_failed",
                message=(
                    "codegraph sync returned no status. Likely an "
                    "mtime glitch or a codegraph CLI error; "
                    "retry is usually safe."
                ),
                recoverable=True,
                duration_ms=int((time.monotonic() - start) * 1000),
                last_known_good=self._last_status,
            )
            return self._failure_result(err)

        # ------------------------------------------------------------------
        # 4. Compute delta vs the last refresh in this run
        # ------------------------------------------------------------------
        async with self._lock:
            prev = self._last_status
            delta = self._compute_delta(fresh, prev)
            duration_ms = int((time.monotonic() - start) * 1000)
            new_status = {
                "nodeCount": fresh.get("nodeCount") or fresh.get("symbols") or 0,
                "edgeCount": fresh.get("edgeCount") or 0,
                "fileCount": fresh.get("fileCount") or fresh.get("files") or 0,
            }
            self._last_status = new_status
            self._last_refresh_at = time.monotonic()
            self._last_baseline_source = "kg_refresh"

        # ------------------------------------------------------------------
        # 5. Emit kg.refreshed event on the stream
        # ------------------------------------------------------------------
        try:
            from harness.api.state import emit_stream_event

            await emit_stream_event(
                session_id=kg_ctx.session_id,
                event_type="kg.refreshed",
                payload={
                    "nodeCount": new_status["nodeCount"],
                    "edgeCount": new_status["edgeCount"],
                    "delta": delta,
                    "duration_ms": duration_ms,
                    "skipped": False,
                    "force": force,
                },
            )
        except Exception as exc:
            # Event emission is non-fatal; the sync itself succeeded.
            logger.debug("kg.refreshed event emit failed (non-fatal): %s", exc)

        # ------------------------------------------------------------------
        # 6. Return the result
        # ------------------------------------------------------------------
        return ToolResult(
            success=True,
            output=json.dumps(
                {
                    "nodeCount": new_status["nodeCount"],
                    "edgeCount": new_status["edgeCount"],
                    "delta": delta,
                    "duration_ms": duration_ms,
                    "last_refresh_at": time.time(),
                    "baseline_source": "kg_refresh",
                }
            ),
            data={
                "nodeCount": new_status["nodeCount"],
                "edgeCount": new_status["edgeCount"],
                "delta": delta,
                "duration_ms": duration_ms,
                "skipped": False,
                "force": force,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_delta(
        fresh: dict[str, Any], prev: dict[str, Any] | None
    ) -> dict[str, int]:
        """Compute a count-based delta between the current and previous
        status dicts.

        Limitation: codegraph's status -j only emits total counts, not
        per-file / per-symbol diff. We expose the absolute change as
        nodes_added / nodes_removed (one of which is always 0 for a
        monotonic add/remove cycle); modified is set to 0 because we
        cannot cheaply compute file-level deltas without an extra
        `codegraph affected` call. A future version can call
        `codegraph affected <changed_files>` to populate ``modified``.

        The first call after the orchestrator's post-coordinator sync
        baseline (which seeded prev) will typically see delta=0 unless
        additional file edits happened between the baseline and this
        call — which is the desired behavior (no spurious "X changed"
        reports).
        """
        if prev is None:
            return {
                "nodes_added": 0,
                "nodes_removed": 0,
                "edges_added": 0,
                "edges_removed": 0,
                "modified": 0,
                "note": "no prior status; delta unavailable",
            }
        new_nodes = fresh.get("nodeCount") or fresh.get("symbols") or 0
        old_nodes = prev.get("nodeCount") or 0
        new_edges = fresh.get("edgeCount") or 0
        old_edges = prev.get("edgeCount") or 0
        nodes_delta = new_nodes - old_nodes
        edges_delta = new_edges - old_edges
        return {
            "nodes_added": max(0, nodes_delta),
            "nodes_removed": max(0, -nodes_delta),
            "edges_added": max(0, edges_delta),
            "edges_removed": max(0, -edges_delta),
            "modified": 0,
        }

    @staticmethod
    def _failure_result(err: "KgRefreshError") -> ToolResult:
        return ToolResult(
            success=False,
            output=json.dumps(err.to_dict(), indent=2),
            error=err.category,
            data=err.to_dict(),
        )


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------
# Single registration. The registry keys by tool name; the toolset
# field is informational metadata. The actual access control is at
# the role boundary in harness/tools/delegate_task.py:312-317 — the
# leaf-worker ``allowed_leaf`` set does NOT include ``kg_refresh``,
# so the tool is effectively coordinator-only. (The pre-C04 wiring
# listed ``kg_refresh`` in both the ``coordinator`` and ``bug-fixer``
# toolsets in toolsets.py; that listing is preserved so existing
# Role YAML frontmatter referencing the name keeps working, but
# the leaf role filter removes the tool from bug-fixer's resolved
# toolset at delegate time.)
from harness.tools.registry import registry

registry.register(KgRefreshTool(), toolset="coordinator")
__all__ = ["KgRefreshTool", "KgRefreshError"]
