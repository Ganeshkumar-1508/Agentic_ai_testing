"""Knowledge graph API — serves CodeGraph SQLite data to the frontend.

CodeGraph (https://github.com/colbymchenry/codegraph) builds a symbol-level
knowledge graph using tree-sitter AST parsing, stored in a SQLite DB at
``.codegraph/codegraph.db``. This API reads that DB (either live from the
sandbox or from a host-cached copy) and returns a JSON shape the frontend
KnowledgeGraph component expects.

Resolution chain:
  1. Host-cached ``agent_workspace/knowledge-graphs/<hash>/codegraph.db``
     (hash = SHA256(repo_url|branch)[:16] for per-repo persistence)
  2. Live sandbox ``/workspace/<session>/.codegraph/codegraph.db`` (via docker exec)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge-graph"])

KG_ROOT = Path(os.environ.get("AGENT_WORKSPACE_MOUNT", "/app/agent_workspace")) / "knowledge-graphs"

MAX_FILE_BYTES = 512 * 1024

# Map CodeGraph node_kind → frontend NodeType
CODEGRAPH_KIND_MAP: dict[str, str] = {
    "file": "file",
    "module": "module",
    "class": "class",
    "struct": "class",
    "interface": "class",
    "trait": "class",
    "protocol": "class",
    "function": "function",
    "method": "function",
    "route": "endpoint",
    "component": "class",
}

# Map CodeGraph edge_kind → frontend EdgeType
# All values must exist in the frontend's EDGE_CATEGORY map
CODEGRAPH_EDGE_MAP: dict[str, str] = {
    "contains": "contains",
    "calls": "calls",
    "imports": "imports",
    "exports": "exports",
    "extends": "inherits",
    "implements": "implements",
    "references": "depends_on",
    "type_of": "depends_on",
    "returns": "calls",
    "instantiates": "calls",
    "overrides": "depends_on",
    "decorates": "depends_on",
}


def _read_snapshot_json(graph_id: str) -> dict[str, Any]:
    snapshot_path = KG_ROOT / graph_id / "knowledge-graph.json"
    if not snapshot_path.exists():
        return {}
    try:
        with snapshot_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.debug("Failed to read knowledge-graph.json for %s: %s", graph_id, e)
    return {}


def _read_db_metadata(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = conn.execute("SELECT key, value FROM project_metadata").fetchall()
    except Exception:
        return {}

    metadata: dict[str, Any] = {}
    for row in rows:
        key = row["key"]
        value = row["value"]
        if not key:
            continue
        metadata[str(key)] = value
    return metadata


def _coerce_non_empty_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _extract_repo_url(*sources: dict[str, Any]) -> str | None:
    for source in sources:
        for key in ("repoUrl", "repo_url", "repositoryUrl", "repository_url"):
            value = _coerce_non_empty_string(source.get(key))
            if value:
                return value
    return None


def _extract_branch(*sources: dict[str, Any]) -> str | None:
    for source in sources:
        for key in ("branch", "gitBranch", "source_branch", "default_branch", "branch_name"):
            value = _coerce_non_empty_string(source.get(key))
            if value:
                return value
    return None


def _repo_display_name(repo_url: str | None) -> str | None:
    if not repo_url:
        return None
    cleaned = repo_url.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return cleaned or None


def _millis_to_iso8601(value: Any) -> str | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _coerce_non_empty_string(value)
    if numeric <= 0:
        return None
    return datetime.fromtimestamp(numeric / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def _schema_version_label(conn: sqlite3.Connection) -> tuple[int | None, str | None]:
    try:
        row = conn.execute("SELECT MAX(version) AS version FROM schema_versions").fetchone()
    except Exception:
        return None, None
    if not row:
        return None, None
    version = row["version"]
    if version is None:
        return None, None
    return int(version), f"codegraph v{int(version)}"


def _indexed_at_iso(conn: sqlite3.Connection) -> str | None:
    try:
        row = conn.execute("SELECT MAX(indexed_at) AS indexed_at FROM files").fetchone()
    except Exception:
        return None
    if not row:
        return None
    return _millis_to_iso8601(row["indexed_at"])


def _build_graph_contract_metadata(
    graph_id: str,
    conn: sqlite3.Connection,
    *,
    node_count: int,
    edge_count: int,
) -> dict[str, Any]:
    snapshot = _read_snapshot_json(graph_id)
    snapshot_meta = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
    db_meta = _read_db_metadata(conn)

    repo_url = _extract_repo_url(snapshot_meta, snapshot, db_meta)
    # Fallback: read from provenance.json written by the syncer.
    # This is the canonical source for "which repo is this graph for"
    # when the snapshot/db metadata is missing the URL.
    if not repo_url:
        prov_path = KG_ROOT / graph_id / "provenance.json"
        if prov_path.exists():
            try:
                with open(prov_path) as f:
                    prov = json.load(f)
                if isinstance(prov, dict):
                    repo_url = _coerce_non_empty_string(prov.get("repo_url")) or ""
            except Exception:
                pass
    repository_display_name = _repo_display_name(repo_url)
    branch = _extract_branch(snapshot_meta, snapshot, db_meta)
    schema_version, version_label = _schema_version_label(conn)
    indexed_at = _indexed_at_iso(conn)
    generated_at = (
        _coerce_non_empty_string(snapshot_meta.get("generatedAt"))
        or _coerce_non_empty_string(snapshot_meta.get("generated_at"))
        or _coerce_non_empty_string(snapshot_meta.get("indexedAt"))
        or _coerce_non_empty_string(snapshot_meta.get("indexed_at"))
    )
    snapshot_label = repository_display_name or graph_id

    metadata: dict[str, Any] = {
        "generator": _coerce_non_empty_string(snapshot_meta.get("generator")) or "codegraph",
        "totalFiles": snapshot_meta.get("totalFiles") or node_count,
        "repoUrl": repo_url,
        "repo_url": repo_url,
        "name": repository_display_name or graph_id,
        "repositoryDisplayName": repository_display_name,
        "branch": branch,
        "graphId": graph_id,
        "snapshotId": graph_id,
        "snapshotLabel": snapshot_label,
        "versionLabel": version_label,
        "schemaVersion": schema_version,
        "generatedAt": generated_at,
        "indexedAt": indexed_at,
        "analyzedAt": indexed_at,
        "nodeCount": node_count,
        "edgeCount": edge_count,
    }
    return metadata


def _find_host_db(graph_id: str) -> Path | None:
    """Check host-cached CodeGraph DB at ``agent_workspace/knowledge-graphs/<id>/codegraph.db``."""
    candidate = KG_ROOT / graph_id / "codegraph.db"
    if candidate.exists():
        return candidate
    return None


def _open_cg_db(graph_id: str) -> sqlite3.Connection | None:
    """Open a CodeGraph SQLite DB. Returns connection or None."""
    db_path = _find_host_db(graph_id)
    if not db_path:
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.warning("Failed to open CodeGraph DB at %s: %s", db_path, e)
        return None


def _list_cg_graphs() -> list[dict[str, Any]]:
    """Scan host-cached CodeGraph DBs at ``agent_workspace/knowledge-graphs/``."""
    if not KG_ROOT.exists():
        return []
    graphs = []
    for entry in sorted(KG_ROOT.iterdir(), reverse=True):
        if entry.is_dir():
            db_file = entry / "codegraph.db"
            if db_file.exists():
                try:
                    conn = _open_cg_db(entry.name)
                    if conn:
                        cur = conn.execute("SELECT COUNT(*) as count FROM nodes")
                        node_count = cur.fetchone()["count"]
                        cur = conn.execute("SELECT COUNT(*) as count FROM edges")
                        edge_count = cur.fetchone()["count"]
                        metadata = _build_graph_contract_metadata(
                            entry.name,
                            conn,
                            node_count=node_count,
                            edge_count=edge_count,
                        )
                        conn.close()
                        graphs.append({
                            "id": entry.name,
                            "volume": entry.name,
                            "node_count": node_count,
                            "edge_count": edge_count,
                            "repo_url": metadata.get("repoUrl") or "",
                            "repository_display_name": metadata.get("repositoryDisplayName"),
                            "branch": metadata.get("branch"),
                            "version_label": metadata.get("versionLabel"),
                            "indexed_at": metadata.get("indexedAt"),
                            "snapshot_id": metadata.get("snapshotId"),
                            "snapshot_label": metadata.get("snapshotLabel"),
                            "language": "codegraph",  # CodeGraph detects languages internally
                        })
                except Exception as e:
                    logger.debug("Failed to read CodeGraph DB %s: %s", entry.name, e)
    return graphs


def _build_frontend_graph(conn: sqlite3.Connection) -> dict[str, Any]:
    """Convert CodeGraph SQLite schema to the frontend KnowledgeGraph JSON shape.

    Per CodeGraph docs, the nodes table has columns:
      id, kind, name, qualified_name, file_path, language, docstring, signature, ...

    The edges table has columns:
      id, source, target, kind, metadata, line, col, provenance

    See: https://deepwiki.com/colbymchenry/codegraph/6-architecture
    """
    nodes: list[dict[str, Any]] = []
    try:
        cur = conn.execute("SELECT id, kind, name, file_path, language, docstring FROM nodes")
        for row in cur.fetchall():
            kind = row["kind"] or "file"
            node_type = CODEGRAPH_KIND_MAP.get(kind, "file")
            name = row["name"] or Path(row["file_path"] or "").name or row["id"]
            nodes.append({
                "id": row["id"],
                "type": node_type,
                "name": name,
                "file": row["file_path"] or "",
                "filePath": row["file_path"] or "",
                "summary": (row["docstring"] or "")[:200],
                "tags": [kind],
                "language": row["language"] or "",
            })
    except Exception as e:
        logger.warning("Failed to read nodes: %s", e)

    edges: list[dict[str, Any]] = []
    try:
        cur = conn.execute("SELECT source, target, kind FROM edges")
        for row in cur.fetchall():
            edge_type = CODEGRAPH_EDGE_MAP.get(row["kind"], "references")
            edges.append({
                "source": row["source"],
                "target": row["target"],
                "type": edge_type,
                "direction": "forward" if edge_type != "imports" else "backward",
                "weight": 1,
            })
    except Exception as e:
        logger.warning("Failed to read edges: %s", e)

    return {
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/recent")
async def list_recent_graphs(limit: int = 10):
    """List the most recent knowledge graphs from host-cached CodeGraph DBs."""
    return {"graphs": _list_cg_graphs()[:limit]}


@router.get("/by-repo")
async def get_graph_by_repo(repo_url: str, branch: str = "main"):
    """Resolve the per-repo graph_id from `repo_url`+`branch` and return it.

    Returns 404 if no graph has been built for this repo yet. The frontend
    can then call `GET /api/knowledge-graph/{graph_id}` to fetch the full graph.
    """
    import hashlib
    key = f"{(repo_url or '').strip()}|{branch.strip()}"
    graph_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    provenance_path = KG_ROOT / graph_id / "provenance.json"
    db_path = KG_ROOT / graph_id / "codegraph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"No knowledge graph yet for {repo_url}@{branch}")
    prov: dict[str, Any] = {}
    if provenance_path.exists():
        try:
            with provenance_path.open("r", encoding="utf-8") as fh:
                prov = json.load(fh) or {}
        except Exception:
            prov = {}
    return {
        "graph_id": graph_id,
        "repo_url": repo_url,
        "branch": branch,
        "provenance": prov,
    }


@router.get("/{graph_id}")
async def get_graph(graph_id: str):
    """Get a specific knowledge graph by reading its CodeGraph SQLite DB."""
    conn = _open_cg_db(graph_id)
    if not conn:
        raise HTTPException(status_code=404, detail="CodeGraph database not found")
    try:
        graph = _build_frontend_graph(conn)
        metadata = _build_graph_contract_metadata(
            graph_id,
            conn,
            node_count=len(graph.get("nodes", [])),
            edge_count=len(graph.get("edges", [])),
        )
        if metadata.get("versionLabel"):
            graph["version"] = metadata["versionLabel"]
        graph["metadata"] = metadata
        return {"graph": graph}
    finally:
        conn.close()


@router.get("/{graph_id}/metadata")
async def get_graph_metadata(graph_id: str):
    """Get graph metadata (counts, file list, version). Small payload.

    Use this to display graph info before loading nodes/edges. For
    graphs with 60K+ nodes, the full graph response is 40+ MB;
    use /neighborhood or /node to load nodes on demand.
    """
    conn = _open_cg_db(graph_id)
    if not conn:
        raise HTTPException(status_code=404, detail="CodeGraph database not found")
    try:
        metadata = _build_graph_contract_metadata(
            graph_id, conn,
            node_count=conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
            edge_count=conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        )
        files = conn.execute(
            "SELECT path, language, size FROM files ORDER BY size DESC LIMIT 50"
        ).fetchall()
        node_kinds = conn.execute(
            "SELECT kind, COUNT(*) AS n FROM nodes GROUP BY kind ORDER BY n DESC"
        ).fetchall()
        return {
            "graph_id": graph_id,
            "metadata": metadata,
            "files": [dict(f) for f in files],
            "node_kinds": [dict(k) for k in node_kinds],
        }
    finally:
        conn.close()


@router.get("/{graph_id}/neighborhood")
async def get_graph_neighborhood(
    graph_id: str,
    node_id: str,
    depth: int = 1,
    max_nodes: int = 200,
):
    """Get a node + its neighbors (BFS up to `depth` hops, capped at `max_nodes`).

    This is the lazy-load endpoint: when the user clicks a node in the
    graph UI, the frontend calls this to fetch that node and its
    immediate surroundings. Keeps responses small (~1-5KB) even for
    60K+ node graphs.
    """
    if depth < 0 or depth > 3:
        depth = min(max(depth, 0), 3)  # cap at 3 hops
    if max_nodes > 1000:
        max_nodes = 1000
    conn = _open_cg_db(graph_id)
    if not conn:
        raise HTTPException(status_code=404, detail="CodeGraph database not found")
    try:
        # Verify the root node exists
        root_row = conn.execute(
            "SELECT id, kind, name, file_path, language, docstring "
            "FROM nodes WHERE id = ?", (node_id,),
        ).fetchone()
        if not root_row:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

        def _node_to_dict(row):
            kind = row["kind"] or "file"
            return {
                "id": row["id"],
                "type": CODEGRAPH_KIND_MAP.get(kind, "file"),
                "name": row["name"] or Path(row["file_path"] or "").name or row["id"],
                "file": row["file_path"] or "",
                "filePath": row["file_path"] or "",
                "summary": (row["docstring"] or "")[:200],
                "tags": [kind],
                "language": row["language"] or "",
            }

        visited: set[str] = {node_id}
        current_layer: set[str] = {node_id}
        nodes_out: list[dict] = [_node_to_dict(root_row)]
        edges_out: list[dict] = []

        for _ in range(depth):
            if not current_layer or len(nodes_out) >= max_nodes:
                break
            placeholders = ",".join("?" * len(current_layer))
            # Find all edges connecting to the current layer
            edge_rows = conn.execute(
                f"SELECT source, target, kind FROM edges "
                f"WHERE source IN ({placeholders}) OR target IN ({placeholders})",
                (*current_layer, *current_layer),
            ).fetchall()
            next_layer: set[str] = set()
            for er in edge_rows:
                edges_out.append({
                    "source": er["source"],
                    "target": er["target"],
                    "type": CODEGRAPH_EDGE_MAP.get(er["kind"], "references"),
                    "direction": "forward",
                    "weight": 1,
                })
                for endpoint in (er["source"], er["target"]):
                    if endpoint not in visited and len(nodes_out) < max_nodes:
                        next_layer.add(endpoint)
                        visited.add(endpoint)
            if not next_layer:
                break
            # Fetch the new nodes
            np = ",".join("?" * len(next_layer))
            node_rows = conn.execute(
                f"SELECT id, kind, name, file_path, language, docstring "
                f"FROM nodes WHERE id IN ({np})",
                (*next_layer,),
            ).fetchall()
            for nr in node_rows:
                nodes_out.append(_node_to_dict(nr))
            current_layer = next_layer

        return {
            "root": node_id,
            "depth": depth,
            "nodes": nodes_out,
            "edges": edges_out,
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
            "truncated": len(nodes_out) >= max_nodes,
        }
    finally:
        conn.close()


@router.get("/{graph_id}/file")
async def get_graph_file(graph_id: str, path: str = ""):
    """Get all nodes + edges in a single file.

    Used by the file panel in the KG UI: when the user opens a file,
    the frontend calls this to render all symbols defined in it
    (and the edges between them).
    """
    if not path:
        raise HTTPException(status_code=400, detail="path query param required")
    conn = _open_cg_db(graph_id)
    if not conn:
        raise HTTPException(status_code=404, detail="CodeGraph database not found")
    try:
        node_rows = conn.execute(
            "SELECT id, kind, name, file_path, language, docstring "
            "FROM nodes WHERE file_path = ? ORDER BY id",
            (path,),
        ).fetchall()
        nodes: list[dict] = []
        node_ids: set[str] = set()
        for row in node_rows:
            kind = row["kind"] or "file"
            nodes.append({
                "id": row["id"],
                "type": CODEGRAPH_KIND_MAP.get(kind, "file"),
                "name": row["name"] or Path(row["file_path"] or "").name or row["id"],
                "file": row["file_path"] or "",
                "filePath": row["file_path"] or "",
                "summary": (row["docstring"] or "")[:200],
                "tags": [kind],
                "language": row["language"] or "",
            })
            node_ids.add(row["id"])
        edges: list[dict] = []
        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            edge_rows = conn.execute(
                f"SELECT source, target, kind FROM edges "
                f"WHERE source IN ({placeholders}) OR target IN ({placeholders})",
                (*node_ids, *node_ids),
            ).fetchall()
            for er in edge_rows:
                if er["source"] in node_ids and er["target"] in node_ids:
                    edges.append({
                        "source": er["source"],
                        "target": er["target"],
                        "type": CODEGRAPH_EDGE_MAP.get(er["kind"], "references"),
                        "direction": "forward",
                        "weight": 1,
                    })
        return {
            "path": path,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
    finally:
        conn.close()


@router.post("/{graph_id}/search")
async def search_graph(graph_id: str, body: dict):
    """Search nodes in a knowledge graph by name or file path."""
    query = (body.get("query") or "").strip()
    max_results = int(body.get("max_results", 10))
    if not query:
        return {"results": []}
    conn = _open_cg_db(graph_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Graph not found")
    try:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT id, name, kind, file_path, language FROM nodes WHERE name LIKE ? OR file_path LIKE ? LIMIT ?",
            (like, like, max_results),
        ).fetchall()
        return {"results": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/{graph_id}/file-content")
async def get_file_content(
    graph_id: str,
    path: str = Query(..., description="File path relative to repo root"),
):
    """Fetch source code for a file referenced by a CodeGraph node.

    Resolution order:
      1. Sandbox: ``/workspace/<session_id>/<path>``
      2. Host: ``agent_workspace/knowledge-graphs/{id}/source/<path>``
      3. Host: ``agent_workspace/<path>``

    Falls back to a GitHub blob URL when the file is not local.
    """
    if not path or "\x00" in path:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if ".." in path.split("/"):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    conn = _open_cg_db(graph_id)
    repo_url = ""
    if conn:
        try:
            cur = conn.execute("SELECT file_path FROM nodes WHERE kind = 'file' LIMIT 1")
            row = cur.fetchone()
            if row and row["file_path"]:
                repo_url = "/".join(row["file_path"].split("/")[:3])  # extract github.com/owner/repo
        except Exception:
            pass
        finally:
            conn.close()

    candidates: list[Path] = [
        Path("/workspace") / path,
        KG_ROOT / graph_id / "source" / path,
        KG_ROOT / graph_id / path,
        Path(os.environ.get("AGENT_WORKSPACE_MOUNT", "/app/agent_workspace")) / path,
    ]

    resolved: Path | None = None
    for cand in candidates:
        try:
            cand_resolved = cand.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        for allowed_root in (KG_ROOT / graph_id if (KG_ROOT / graph_id).exists() else KG_ROOT,
                            Path("/workspace") if Path("/workspace").exists() else KG_ROOT):
            try:
                cand_resolved.relative_to(allowed_root.resolve())
                resolved = cand_resolved
                break
            except (ValueError, OSError):
                continue
        if resolved is not None:
            break

    ext = Path(path).suffix.lower()
    language = {
        ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
        ".jsx": "jsx", ".go": "go", ".rs": "rust", ".java": "java",
    }.get(ext, "text")

    response: dict[str, Any] = {
        "graph_id": graph_id,
        "path": path,
        "language": language,
        "content": None,
        "lines": 0,
        "size_bytes": 0,
        "truncated": False,
        "source": "missing",
        "source_url": None,
    }

    if resolved is not None and resolved.is_file():
        try:
            data_bytes = resolved.read_bytes()
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
        truncated = len(data_bytes) > MAX_FILE_BYTES
        if truncated:
            data_bytes = data_bytes[:MAX_FILE_BYTES]
        text = data_bytes.decode("utf-8", errors="replace")
        response.update({
            "content": text,
            "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
            "size_bytes": resolved.stat().st_size,
            "truncated": truncated,
            "source": "local",
        })
    else:
        logger.info("[knowledge-graph] file-content not found: graph=%s path=%s", graph_id, path)

    return response
