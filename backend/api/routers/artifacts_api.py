"""Artifacts API — browse the per-session container filesystem at /workspace.

The previous implementation queried a Postgres `artifacts` table that the
orchestrator never wrote to, so the page was always empty. The page now
talks to the per-session sandbox container that already holds the cloned
repo, generated test reports, and any other write the agent produced.

Endpoints:
    GET  /api/artifacts/sessions                            list sessions with running sandboxes
    GET  /api/artifacts/{session_id}/tree?path=&depth=      recursive file tree
    GET  /api/artifacts/{session_id}/file-content?path=     read text file (capped, for preview)
    GET  /api/artifacts/{session_id}/download?path=         download a single file
    DELETE /api/artifacts/{session_id}/file?path=          delete a file (or empty dir)

The DB-backed download endpoint kept for backward-compat:
    GET  /api/artifacts/{session_id}                        list artifacts in `artifacts` table
    GET  /api/artifacts/{session_id}/download/{artifact_id} download by row id
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _docker_path() -> str:
    """Return path to the docker CLI.

    Honors the TESTAI_DOCKER_HOST env var so tests can stub it.
    """
    return os.environ.get("TESTAI_DOCKER_HOST", "docker")


def _manager(request: Request):
    mgr = getattr(request.app.state, "backend_factory", None)
    if not mgr:
        raise HTTPException(status_code=503, detail="sandbox manager not initialized")
    return mgr


async def _resolve_container_id(request: Request, session_id: str) -> str:
    """Find the running container for a session, or raise 404.

    The container may be tracked in the in-memory SandboxManager (recovered
    on startup via `docker ps --filter name=testai-sandbox-`) or discovered
    lazily via `docker ps` so that this endpoint also works for containers
    that the manager doesn't know about.
    """
    mgr = _manager(request)
    try:
        for sb in mgr.list_sandboxes():
            if sb.get("session_id") == session_id and sb.get("container_id"):
                return sb["container_id"]
    except Exception:
        pass

    # fallback: docker ps
    docker = _docker_path()
    prefix = f"tsb-{session_id[:48]}"
    try:
        proc = subprocess.run(
            [docker, "ps", "-a", "--filter", f"name={prefix}",
             "--format", "{{.ID}}\t{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"docker unavailable: {exc}") from exc

    if proc.returncode != 0 or not proc.stdout.strip():
        raise HTTPException(status_code=404, detail=f"no sandbox for session {session_id}")
    for line in proc.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].startswith(prefix):
            return parts[0]
    raise HTTPException(status_code=404, detail=f"no sandbox for session {session_id}")


async def _docker_exec(container_id: str, cmd: str, timeout: int = 30) -> str:
    """Run `docker exec <id> bash -lc <cmd>` and return stdout."""
    docker = _docker_path()
    proc = subprocess.run(
        [docker, "exec", container_id, "bash", "-lc", cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0 and not proc.stdout:
        raise HTTPException(status_code=500, detail=proc.stderr.strip() or "exec failed")
    return proc.stdout


def _safe_join(root: str, rel: str) -> str:
    """Join + assert `rel` does not escape `root`."""
    if not rel or rel == ".":
        return root
    rel = rel.lstrip("/")
    candidate = os.path.normpath(os.path.join(root, rel))
    root_norm = os.path.normpath(root)
    if not (candidate == root_norm or candidate.startswith(root_norm + os.sep)):
        raise HTTPException(status_code=400, detail="path escapes workspace root")
    return candidate


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions_with_sandboxes(request: Request):
    """List every session with a running sandbox container.

    The page uses this as the session dropdown source — it returns the
    sessions the user can actually browse, not the subagent sessions
    that have no workspace of their own.
    """
    try:
        mgr = _manager(request)
        sandboxes = mgr.list_sandboxes() or []
    except HTTPException:
        sandboxes = []
    except Exception:
        sandboxes = []

    db = getattr(request.app.state, "db", None)
    out: list[dict[str, Any]] = []
    for sb in sandboxes:
        sid = sb.get("session_id", "")
        if not sid:
            continue
        rec: dict[str, Any] = {
            "session_id": sid,
            "container_id": sb.get("container_id", ""),
            "container_name": sb.get("name", f"testai-sandbox-{sid[:12]}"),
            "created_at": sb.get("created_at"),
            "is_running": bool(sb.get("is_running", True)),
            "repo_url": "",
            "goal": "",
        }
        if db:
            try:
                row = await db.fetchrow(
                    "SELECT prompt, repo_url, goal, created_at, status "
                    "FROM sessions WHERE id = $1",
                    sid,
                )
                if row:
                    rec["repo_url"] = row.get("repo_url") or ""
                    rec["goal"] = row.get("goal") or row.get("prompt") or ""
                    if rec["created_at"] is None and row.get("created_at"):
                        rec["created_at"] = row["created_at"].timestamp()
                    rec["status"] = row.get("status", "")
            except Exception:
                pass
        out.append(rec)

    out.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return {"sessions": out, "count": len(out)}


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


@router.get("/{session_id}/tree")
async def get_tree(
    request: Request,
    session_id: str,
    path: str = Query("/", description="workspace-relative path"),
    depth: int = Query(4, ge=1, le=8),
    show_hidden: bool = Query(False),
    limit: int = Query(2000, ge=1, le=10000),
):
    """Recursive file tree under `path` (workspace-relative)."""
    container_id = await _resolve_container_id(request, session_id)
    rel = path.strip() or "/"
    if rel == ".":
        rel = "/"

    # Cap to /workspace
    if rel.startswith("/workspace"):
        rel_in = rel[len("/workspace"):]
    else:
        rel_in = rel.lstrip("/")

    safe_path = shlex.quote(rel_in or ".")

    hidden_filter = "" if show_hidden else r"-not -path '*/\.*'"
    script = f"""
set -e
ROOT=/workspace
cd "$ROOT" || exit 1
find {safe_path} -mindepth 0 -maxdepth {int(depth)} \
  \( -path '*/node_modules' -o -path '*/.git' \) -prune -o \
  {hidden_filter} -print 2>/dev/null \
  | head -n {int(limit)}
"""
    raw = await _docker_exec(container_id, script, timeout=60)

    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        line = line.rstrip("/").strip()
        if not line or line in seen:
            continue
        seen.add(line)
        relpath = line.lstrip("./")
        is_dir = False
        # `find` only tells us the type via -type — re-check per node.
        try:
            t = await _docker_exec(container_id, f"test -d {shlex.quote(line)} && echo DIR || echo FILE", timeout=5)
            is_dir = t.strip() == "DIR"
        except Exception:
            is_dir = False
        nodes.append({"path": relpath, "name": os.path.basename(relpath) or "/", "is_dir": is_dir})

    # Root pseudo-node so the UI can render the workspace header even when empty.
    if not any(n["path"] == "" for n in nodes):
        nodes.insert(0, {"path": "", "name": "/workspace", "is_dir": True})

    return {
        "session_id": session_id,
        "path": rel,
        "depth": depth,
        "nodes": nodes,
        "count": len(nodes),
    }


# ---------------------------------------------------------------------------
# preview / download
# ---------------------------------------------------------------------------


_TEXT_EXT = {
    "txt", "md", "rst", "log", "json", "yaml", "yml", "toml", "ini", "cfg",
    "py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "rb", "go", "rs", "java",
    "kt", "swift", "c", "h", "hpp", "cpp", "cc", "cs", "php", "sh", "bash",
    "zsh", "html", "htm", "xml", "css", "scss", "sass", "less", "sql",
    "dockerfile", "gitignore", "gitattributes", "env", "csv", "tsv", "erb",
    "haml", "slim", "vue", "svelte", "lua", "pl", "r", "dart",
}


@router.get("/{session_id}/file-content")
async def get_file_content(
    request: Request,
    session_id: str,
    path: str = Query(..., description="workspace-relative path"),
    max_bytes: int = Query(256_000, ge=1, le=4_000_000),
):
    """Read a text file from the workspace. Binary returns 415 with base64."""
    container_id = await _resolve_container_id(request, session_id)
    rel = path.lstrip("/")
    if rel.startswith("workspace/"):
        rel = rel[len("workspace/"):]
    quoted = shlex.quote(rel)
    # Type + size first
    meta = await _docker_exec(
        container_id,
        f"stat -c '%s|%F' -- {quoted} 2>/dev/null || echo -",
        timeout=5,
    )
    if meta.strip() == "-" or not meta.strip():
        raise HTTPException(status_code=404, detail="file not found")
    size_str, ftype = (meta.strip() + "|").split("|", 1)
    try:
        size = int(size_str)
    except ValueError:
        size = 0
    if "directory" in ftype.lower():
        raise HTTPException(status_code=400, detail="path is a directory")

    ext = os.path.splitext(rel)[1].lstrip(".").lower()
    name = os.path.basename(rel).lower()
    is_text = ext in _TEXT_EXT or name in {"dockerfile", "makefile", "gemfile", "rakefile"}

    truncated = size > max_bytes
    if is_text:
        head = await _docker_exec(
            container_id,
            f"head -c {int(max_bytes)} -- {quoted} 2>/dev/null || echo ''",
            timeout=15,
        )
        text = head if not truncated else head + f"\n\n…[truncated, {size - max_bytes} more bytes]"
        return {
            "session_id": session_id,
            "path": rel,
            "size_bytes": size,
            "truncated": truncated,
            "is_text": True,
            "content": text,
        }

    # binary -> base64
    head = await _docker_exec(
        container_id,
        f"head -c {int(max_bytes)} -- {quoted} 2>/dev/null | base64 -w0 || echo ''",
        timeout=15,
    )
    return {
        "session_id": session_id,
        "path": rel,
        "size_bytes": size,
        "truncated": truncated,
        "is_text": False,
        "encoding": "base64",
        "content": head.strip(),
    }


@router.get("/{session_id}/download")
async def download_file(
    request: Request,
    session_id: str,
    path: str = Query(..., description="workspace-relative path"),
):
    """Stream a single file out of the container via docker cp + Response."""
    container_id = await _resolve_container_id(request, session_id)
    rel = path.lstrip("/")
    if rel.startswith("workspace/"):
        rel = rel[len("workspace/"):]
    quoted = shlex.quote(rel)
    meta = await _docker_exec(
        container_id,
        f"stat -c '%s|%F' -- {quoted} 2>/dev/null || echo -",
        timeout=5,
    )
    if meta.strip() == "-" or not meta.strip():
        raise HTTPException(status_code=404, detail="file not found")
    size_str, ftype = (meta.strip() + "|").split("|", 1)
    try:
        size = int(size_str)
    except ValueError:
        size = 0
    if "directory" in ftype.lower():
        raise HTTPException(status_code=400, detail="path is a directory")

    # Use docker cp to host then stream the file
    docker = _docker_path()
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [docker, "cp", f"{container_id}:/workspace/{rel}", tmp_path],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=proc.stderr.strip() or "docker cp failed")
        with open(tmp_path, "rb") as fh:
            data = fh.read()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    ext = os.path.splitext(rel)[1].lstrip(".").lower()
    name = os.path.basename(rel)
    is_text = ext in _TEXT_EXT or os.path.basename(rel).lower() in {"dockerfile", "makefile", "gemfile", "rakefile"}
    media = "text/plain; charset=utf-8" if is_text else "application/octet-stream"
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Content-Length": str(len(data)),
        },
    )


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@router.delete("/{session_id}/file")
async def delete_file(
    request: Request,
    session_id: str,
    path: str = Query(..., description="workspace-relative path"),
    recursive: bool = Query(False, description="allow removing non-empty directories"),
):
    """Delete a file (or directory if recursive=true) from the workspace."""
    container_id = await _resolve_container_id(request, session_id)
    rel = path.lstrip("/")
    if rel.startswith("workspace/"):
        rel = rel[len("workspace/"):]
    if not rel or rel in {".", "/"}:
        raise HTTPException(status_code=400, detail="refusing to delete workspace root")

    quoted = shlex.quote(rel)
    flags = "-rf" if recursive else "-f"
    out = await _docker_exec(
        container_id,
        f"rm {flags} -- {quoted} && echo OK || echo FAIL",
        timeout=15,
    )
    if "OK" not in out:
        raise HTTPException(status_code=400, detail="delete failed (file missing or non-empty directory)")
    return {"status": "deleted", "session_id": session_id, "path": rel, "recursive": recursive}


# ---------------------------------------------------------------------------
# legacy DB-backed listing (kept so /api/artifacts/{id} still returns 200)
# ---------------------------------------------------------------------------


@router.get("/{session_id}")
async def list_artifacts_legacy(request: Request, session_id: str):
    """Legacy: list artifacts registered in the `artifacts` table.

    The orchestrator does not currently write to this table, so the
    result is usually empty. The page now uses /tree instead; this
    endpoint exists only for backward compatibility with /api/sandbox
    panels and external integrations.
    """
    db = getattr(request.app.state, "db", None)
    if not db:
        return {"artifacts": [], "session_id": session_id, "source": "memory"}
    try:
        rows = await db.fetch(
            "SELECT id, subagent_id, path, size_bytes, mime_type, description, created_at "
            "FROM artifacts WHERE session_id = $1 ORDER BY created_at DESC",
            session_id,
        )
        return {
            "artifacts": [dict(r) for r in rows],
            "session_id": session_id,
            "source": "db",
        }
    except Exception as exc:  # noqa: BLE001
        return {"artifacts": [], "session_id": session_id, "source": "db", "error": str(exc)}


@router.get("/{session_id}/download/{artifact_id}")
async def download_artifact_legacy(
    request: Request, session_id: str, artifact_id: str,
):
    """Legacy: download an artifact by row id from the `artifacts` table."""
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=503, detail="db not initialized")
    try:
        row = await db.fetchrow(
            "SELECT path, mime_type FROM artifacts WHERE id = $1 AND session_id = $2",
            artifact_id, session_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="artifact not found")
    file_path = row["path"]
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"file missing: {file_path}")
    return FileResponse(
        file_path,
        media_type=row["mime_type"] or "application/octet-stream",
        filename=Path(file_path).name,
    )
