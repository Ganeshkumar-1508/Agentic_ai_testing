"""L0 raw artifact storage + L1 knowledge graph indexer.

Q7-B/C from the autonomy roadmap. Three layers:

  - L0 (``agent_artifacts`` table) — the raw "what happened" stream.
    One row per (round, tool_call, result), written at run end via
    ``Agent._save_reflections()``. Cheap to write; no LLM calls.

  - L1 (``kg_nodes`` / ``kg_edges`` tables) — queryable facts extracted
    from L0 by ``L1Indexer.promote()``. Scans recent L0 rows and promotes
    file-write, test-run, and delegation patterns into knowledge graph
    entries so subsequent agents can discover what was done.

  - L2 reflection (the "lesson learned" the agent writes at run end
    for the *next* run on the same repo to read) is a separate surface
    — see ``memory_tool.py`` (the existing per-repo memory tool).

Usage:
    from harness.services.artifact_store import L1Indexer
    await L1Indexer(db).promote(session_id)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class ArtifactStore:
    """L0 raw artifact storage.

    Lightweight wrapper around the ``agent_artifacts`` table. The
    Agent calls ``write_batch(session_id, messages)`` once at the
    end of a run (in ``_save_reflections``). The indexer reads
    back via ``recent(limit=N)``.

    The store is intentionally simple: no transactions, no upsert,
    no deduplication. Each call appends rows. Disk space is bounded
    by the configured retention (separate concern — see
    ``ArtifactStore.purge_older_than``).
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    async def write_batch(
        self,
        session_id: str,
        items: Iterable[dict[str, Any]],
    ) -> int:
        """Write multiple artifact rows for one session in one go.

        Each item is a dict with:
          - ``kind`` (str): "tool_call" | "tool_result" | "reflection" | ...
          - ``round_num`` (int, optional)
          - ``tool_name`` (str, optional)
          - ``payload`` (dict, optional)

        Returns the number of rows written (0 if items is empty).
        """
        rows = list(items)
        if not rows:
            return 0
        count = 0
        for item in rows:
            try:
                await self.db.execute(
                    """INSERT INTO agent_artifacts
                       (session_id, round_num, kind, tool_name, payload)
                       VALUES ($1, $2, $3, $4, $5::jsonb)""",
                    session_id,
                    int(item.get("round_num", 0)),
                    str(item.get("kind", "tool_call")),
                    item.get("tool_name") or "",
                    json.dumps(item.get("payload", {}), ensure_ascii=False, default=str),
                )
                count += 1
            except Exception as exc:
                logger.warning(
                    "ArtifactStore.write_batch row failed session=%s kind=%s: %s",
                    session_id, item.get("kind"), exc,
                )
        return count

    async def recent(
        self,
        session_id: str | None = None,
        *,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read recent artifacts, optionally filtered by session or kind.

        Used by the L1 indexer (follow-up) and by the dashboard's
        per-run timeline view (Phase 3 PR-3.7).
        """
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            params.append(session_id)
            clauses.append(f"session_id = ${len(params)}")
        if kind is not None:
            params.append(kind)
            clauses.append(f"kind = ${len(params)}")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        sql = (
            f"SELECT id, session_id, round_num, kind, tool_name, payload, created_at "
            f"FROM agent_artifacts {where} "
            f"ORDER BY created_at DESC LIMIT ${len(params)}"
        )
        try:
            rows = await self.db.fetch(sql, *params)
        except Exception as exc:
            logger.warning("ArtifactStore.recent failed: %s", exc)
            return []
        out: list[dict[str, Any]] = []
        for r in rows:
            payload = r["payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    payload = {}
            out.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "round_num": r["round_num"],
                "kind": r["kind"],
                "tool_name": r["tool_name"],
                "payload": payload or {},
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
        return out


class L1Indexer:
    """Promote L0 artifacts to the Postgres knowledge graph tables.

    After an agent run completes, scans the L0 ``agent_artifacts``
    for file-write and test-run patterns and writes summary nodes to
    ``kg_nodes``/``kg_edges`` for the dashboard.

    CodeGraph auto-sync requires the MCP server daemon running in
    the background. In the sandbox we call the CLI directly — no
    daemon — so we explicitly run ``codegraph sync`` after changes
    to keep the index fresh.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    async def promote(self, session_id: str) -> dict[str, Any]:
        """Promote L0 artifacts for a session to the knowledge graph.

        1. Read recent L0 artifacts for this session
        2. Extract file-write and test-run facts
        3. Write summary nodes + edges to Postgres KG tables

        CodeGraph's auto-sync handles the sandbox-side re-index.
        """
        import json as _json
        import hashlib as _hl
        store = ArtifactStore(self.db)
        artifacts = await store.recent(session_id=session_id, limit=500)
        if not artifacts:
            return {"promoted": 0, "files": [], "tests": []}

        promoted_files: set[str] = set()
        promoted_tests: set[str] = set()
        tool_names: dict[str, int] = {}

        for art in artifacts:
            name = str(art.get("tool_name", "") or "")
            if name:
                tool_names[name] = tool_names.get(name, 0) + 1
            payload = art.get("payload", {}) or {}
            if art["kind"] == "tool_call":
                args_str = str(payload.get("arguments", "") or "")
                if name in ("write_file", "edit_file", "apply_patch"):
                    for line in args_str.split(","):
                        line = line.strip().strip('"').strip("'")
                        for prefix in ("path=", '"path":', "'path':", '\\"path\\":'):
                            if prefix in line:
                                val = line.split(prefix, 1)[-1].split(",")[0].strip()
                                val = val.strip('"').strip("'").strip("\\")
                                if val and val.startswith("/"):
                                    promoted_files.add(val)
                if name == "bash":
                    cmd = str(payload.get("arguments", "") or args_str)
                    if "test" in cmd.lower() and any(x in cmd for x in ("pytest", "rspec", "jest", "go test", "npm test")):
                        promoted_tests.add(cmd[:120])

        total_promoted = len(promoted_files) + len(promoted_tests)
        if total_promoted == 0:
            return {"promoted": 0, "files": [], "tests": []}

        run_id = session_id[:12]
        node_ids: list[str] = []
        for fp in sorted(promoted_files):
            nid = f"l1-{_hl.md5(fp.encode()).hexdigest()[:8]}"
            node_ids.append(nid)
            try:
                await self.db.execute(
                    "INSERT INTO kg_nodes (id, label, file_type, source_file, properties, run_id) "
                    "VALUES ($1, $2, $3, $4, $5::jsonb, $6) ON CONFLICT (id) DO NOTHING",
                    nid, fp.split("/")[-1],
                    "code" if fp.endswith((".py", ".js", ".ts", ".rb", ".go", ".rs", ".java")) else "artifact",
                    fp, _json.dumps({"promoted_from": session_id[:8], "tool_calls": dict(tool_names)}), run_id,
                )
            except Exception as exc:
                logger.debug("L1Indexer kg_nodes insert failed: %s", exc)

        # Write kg_edges: pairwise "imports" / "touches" / "tests"
        # between promoted files. Co-occurrence in the same
        # agent run is a meaningful signal for the dashboard.
        for i, a in enumerate(node_ids):
            for b in node_ids[i + 1: i + 4]:  # cap at 3 edges per node to avoid fan-out blow-up
                try:
                    await self.db.execute(
                        "INSERT INTO kg_edges (source_id, target_id, relation, confidence, source_file, run_id) "
                        "VALUES ($1, $2, $3, $4, $5, $6) "
                        "ON CONFLICT (source_id, target_id, relation) DO NOTHING",
                        a, b, "co_occurs_in_run", "EXTRACTED", "", run_id,
                    )
                except Exception as exc:
                    logger.debug("L1Indexer kg_edges insert failed: %s", exc)

        # Sync CodeGraph in sandbox so codegraph_explore/search see changes
        await self._sync_codegraph()

        return {"promoted": total_promoted, "files": list(promoted_files), "tests": list(promoted_tests)}

    async def _sync_codegraph(self) -> bool:
        """Run ``codegraph sync`` in the sandbox for incremental KG update."""
        try:
            from harness.codegraph import get_sandbox_env, _run_in_sandbox
            env = await get_sandbox_env()
            if env is None:
                logger.debug("L1Indexer: no sandbox env for sync")
                return False
            proc = await _run_in_sandbox(env, ["sync", "/workspace/repo"], timeout=60)
            if proc and proc.returncode == 0:
                logger.info("L1Indexer: CodeGraph synced after file changes")
                return True
            logger.debug("L1Indexer: CodeGraph sync returned %s", proc.returncode if proc else "None")
            return False
        except Exception as exc:
            logger.debug("L1Indexer sync failed: %s", exc)
            return False


def derive_l0_items_from_messages(
    messages: list[Any],
    *,
    last_reflection: str | None = None,
) -> list[dict[str, Any]]:
    """Extract L0 artifact rows from an agent's message history.

    Iterates ``messages`` looking for assistant tool_calls and the
    tool results that follow. Each pair becomes one ``tool_call``
    and one ``tool_result`` artifact row, with ``round_num`` derived
    from the position in the list.

    If ``last_reflection`` is provided (the reflexion text the
    agent injected after a failed tool), it's written as a
    ``reflection`` artifact.

    This is a pure function over the message list — no DB access.
    The caller (``Agent._save_reflections``) hands the result to
    ``ArtifactStore.write_batch``.
    """
    items: list[dict[str, Any]] = []
    round_num = 0
    pending_calls: dict[str, dict[str, Any]] = {}
    for m in messages:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
        if role == "assistant":
            tool_calls = getattr(m, "tool_calls", None) or (
                m.get("tool_calls") if isinstance(m, dict) else None
            ) or []
            for tc in tool_calls:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", {})
                if not fn:
                    continue
                name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                args = fn.get("arguments", "") if isinstance(fn, dict) else getattr(fn, "arguments", "")
                call_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                items.append({
                    "kind": "tool_call",
                    "round_num": round_num,
                    "tool_name": name or "",
                    "payload": {
                        "call_id": call_id or "",
                        "arguments": (args or "")[:1000],  # cap huge args
                    },
                })
                if call_id:
                    pending_calls[call_id] = {
                        "round_num": round_num,
                        "tool_name": name or "",
                    }
            if tool_calls:
                round_num += 1
        elif role == "tool":
            call_id = getattr(m, "tool_call_id", None) or (
                m.get("tool_call_id") if isinstance(m, dict) else None
            ) or ""
            if call_id and call_id in pending_calls:
                info = pending_calls.pop(call_id)
                output = (content or "")
                items.append({
                    "kind": "tool_result",
                    "round_num": info["round_num"],
                    "tool_name": info["tool_name"],
                    "payload": {
                        "call_id": call_id,
                        "output": output[:2000],  # cap huge outputs
                    },
                })
    if last_reflection:
        items.append({
            "kind": "reflection",
            "round_num": round_num,
            "tool_name": "",
            "payload": {"text": last_reflection[:2000]},
        })
    return items
