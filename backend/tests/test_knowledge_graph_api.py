from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from api.routers import knowledge_graph_api


def _create_graph_snapshot(root: Path, graph_id: str, *, include_repo: bool = True, branch: str | None = None) -> None:
    graph_dir = root / graph_id
    graph_dir.mkdir(parents=True, exist_ok=True)

    db_path = graph_dir / "codegraph.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE nodes (id TEXT, kind TEXT, name TEXT, file_path TEXT, language TEXT, docstring TEXT)")
    conn.execute("CREATE TABLE edges (source TEXT, target TEXT, kind TEXT)")
    conn.execute(
        "CREATE TABLE files (path TEXT, content_hash TEXT, language TEXT, size INTEGER, modified_at REAL, indexed_at REAL, node_count INTEGER, errors TEXT)"
    )
    conn.execute("CREATE TABLE project_metadata (key TEXT, value TEXT, updated_at INTEGER)")
    conn.execute("CREATE TABLE schema_versions (version INTEGER, applied_at INTEGER, description TEXT)")

    conn.execute(
        "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?)",
        ("file-1", "file", "app.py", "src/app.py", "python", "Application entrypoint"),
    )
    conn.execute(
        "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?)",
        ("fn-1", "function", "main", "src/app.py", "python", "Main function"),
    )
    conn.execute("INSERT INTO edges VALUES (?, ?, ?)", ("file-1", "fn-1", "contains"))
    conn.execute(
        "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("src/app.py", "hash", "python", 128, 1780899024201.0, 1780899060846.0, 2, None),
    )
    conn.execute(
        "INSERT INTO schema_versions VALUES (?, ?, ?)",
        (4, 1780899060229, "Initial schema includes all migrations"),
    )
    if branch is not None:
        conn.execute(
            "INSERT INTO project_metadata VALUES (?, ?, ?)",
            ("branch", branch, 1780899060229),
        )
    conn.commit()
    conn.close()

    payload = {
        "metadata": {
            "generator": "testai-kg-generator",
            "totalFiles": 12,
        }
    }
    if include_repo:
        payload["metadata"]["repoUrl"] = "https://github.com/example-org/example-repo"
    (graph_dir / "knowledge-graph.json").write_text(json.dumps(payload), encoding="utf-8")


def test_list_recent_graphs_exposes_contract_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _create_graph_snapshot(tmp_path, "snapshot-123", include_repo=True, branch="feature/wireframe")
    monkeypatch.setattr(knowledge_graph_api, "KG_ROOT", tmp_path)

    graphs = knowledge_graph_api._list_cg_graphs()

    assert len(graphs) == 1
    graph = graphs[0]
    assert graph["id"] == "snapshot-123"
    assert graph["repo_url"] == "https://github.com/example-org/example-repo"
    assert graph["repository_display_name"] == "example-org/example-repo"
    assert graph["branch"] == "feature/wireframe"
    assert graph["version_label"] == "schema v4"
    assert graph["snapshot_id"] == "snapshot-123"
    assert graph["snapshot_label"] == "example-org/example-repo"
    assert graph["indexed_at"] == "2026-06-08T06:11:00.846000Z"


@pytest.mark.asyncio
async def test_get_graph_returns_nullable_contract_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _create_graph_snapshot(tmp_path, "snapshot-no-repo", include_repo=False, branch=None)
    monkeypatch.setattr(knowledge_graph_api, "KG_ROOT", tmp_path)

    response = await knowledge_graph_api.get_graph("snapshot-no-repo")

    graph = response["graph"]
    metadata = graph["metadata"]
    assert graph["version"] == "schema v4"
    assert metadata["repoUrl"] is None
    assert metadata["repo_url"] is None
    assert metadata["repositoryDisplayName"] is None
    assert metadata["branch"] is None
    assert metadata["snapshotId"] == "snapshot-no-repo"
    assert metadata["snapshotLabel"] == "snapshot-no-repo"
    assert metadata["indexedAt"] == "2026-06-08T06:11:00.846000Z"
    assert metadata["analyzedAt"] == "2026-06-08T06:11:00.846000Z"
    assert metadata["nodeCount"] == 2
    assert metadata["edgeCount"] == 1
