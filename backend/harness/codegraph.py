"""CodeGraph integration — sandbox-aware indexing and querying.

Official CodeGraph docs: https://colbymchenry.github.io/codegraph
Commands run inside the sandbox container via docker exec because
the source code lives on a Docker volume accessible only from the sandbox.

Per the CodeGraph docs, the CLI supports:
  codegraph init    — build per-project knowledge graph index
  codegraph status  — index statistics (symbols, files)
  codegraph query   — search symbols by name
  codegraph callers — find callers of a symbol
  codegraph callees — find callees of a symbol
  codegraph affected — find tests affected by file changes
  codegraph explore — free-form codebase exploration (primary tool)

npx needs a writable HOME directory. Sandbox user (pn) may lack one,
so we set HOME=/workspace (writable volume) before every npx call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


async def store_test_results_in_codegraph(
    db: Any,
    env: Any,
    workspace_path: str,
    run_id: str,
) -> int:
    """Store test results as codegraph node annotations for a given run.

    Queries test_results for the run, then uses ``codegraph annotate`` to
    attach pass/fail metadata to the corresponding codegraph nodes. This
    lets future coordinator rounds see which files had failing tests.

    Returns the number of annotations written.
    """
    try:
        rows = await db.fetch(
            "SELECT test_name, status, error, duration_ms, file_path "
            "FROM test_results WHERE run_id = $1 ORDER BY test_name",
            run_id,
        )
    except Exception as e:
        logger.warning("store_test_results_in_codegraph: query failed: %s", e)
        return 0

    if not rows:
        return 0

    annotations = []
    for r in rows:
        node_path = r.get("file_path") or r.get("test_name", "").split("::")[0]
        status = r["status"] or "unknown"
        duration = int(r["duration_ms"] or 0)
        annotations.append(json.dumps({
            "path": node_path,
            "test": r["test_name"],
            "status": status,
            "duration_ms": duration,
            "error": (r["error"] or "")[:200],
        }))

    for ann in annotations:
        try:
            proc = await _run_in_sandbox(
                env, ["annotate", "--json", ann], timeout=30,
            )
            if proc and proc.returncode != 0:
                logger.debug("codegraph annotate warning for %s: %s", run_id, (proc.stderr or "")[:100])
        except Exception as e:
            logger.debug("codegraph annotate failed for %s: %s", run_id, e)

    stored = len(annotations)
    logger.info("Stored %d test-result annotations in codegraph for run %s", stored, run_id)
    return stored


async def get_test_failures_for_run(
    db: Any,
    run_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get failed test details for a run — useful for coordinator context.

    Returns a list of {test_name, file_path, error} dicts for the most
    recent failed tests in the run. This lets the coordinator understand
    what broke before delegating the next round of fix attempts.
    """
    try:
        rows = await db.fetch(
            "SELECT test_name, file_path, error, duration_ms "
            "FROM test_results WHERE run_id = $1 AND status = 'failed' "
            "ORDER BY duration_ms DESC LIMIT $2",
            run_id, limit,
        )
    except Exception as e:
        logger.warning("get_test_failures_for_run: query failed: %s", e)
        return []

    return [
        {
            "test_name": r["test_name"],
            "file_path": r.get("file_path") or r["test_name"].split("::")[0],
            "error": (r["error"] or "")[:300],
            "duration_ms": int(r["duration_ms"] or 0),
        }
        for r in rows
    ]


def is_available() -> bool:
    """Check if npx is available on the backend host."""
    return shutil.which("npx") is not None


async def _run_in_sandbox(env: Any, args: list[str], timeout: int = 120, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a codegraph command inside the sandbox container.

    Sets HOME=/workspace so npm can write its cache (sandbox user pn
    may not have a writable home dir). Uses npx to download and cache
    codegraph; subsequent calls reuse the cached version.
    """
    cmd = "HOME=/workspace npx --yes @colbymchenry/codegraph " + " ".join(shlex_quote(a) for a in args)
    if cwd:
        cmd = "cd {} && {}".format(shlex_quote(cwd), cmd)
    return await env.run(cmd, timeout=timeout)


def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


async def get_sandbox_env() -> Any | None:
    """Resolve the current sandbox environment from the active scope."""
    try:
        from harness.context import manager as scope_manager
        scope = scope_manager.current
        if scope is None:
            return None
        session_id = scope.session_id
        if not session_id:
            return None
        from harness.backends.factory import get_backend
        from harness.memory.db_context import get_db
        _db = get_db()
        if _db is None:
            return None
        return get_backend(_db, session_id)
    except Exception:
        return None


async def index_project(env: Any, workspace_path: str, force: bool = False, timeout: int = 600) -> dict[str, Any]:
    """Build the per-project knowledge graph index via ``codegraph init --index``.

    ``codegraph init`` without ``--index`` only creates the project directory
    and an empty DB — it does NOT parse source files or build the symbol
    graph.  The ``--index`` flag (or the ``codegraph index`` command) is
    required to actually extract nodes and edges.

    If ``force`` is True, or the existing DB is empty (smaller than 16 KB
    — just the SQLite header), we delete ``.codegraph/`` before starting so
    ``init --index`` does a full rebuild.  This handles the case where a
    prior run left a stale empty DB that blocks re-indexing (CodeGraph
    treats ``Already initialized`` as a no-op).
    """
    try:
        # Stale DB detection: wipe .codegraph/ if the DB is empty so
        # init --index actually indexes instead of silently skipping.
        if force:
            await _wipe_codegraph_dir(env, workspace_path)
        else:
            try:
                db_size = await _db_file_size(env, workspace_path)
                if db_size is not None and db_size < 16 * 1024:
                    logger.info(
                        "CodeGraph DB is empty (%d bytes), wiping for fresh index",
                        db_size,
                    )
                    await _wipe_codegraph_dir(env, workspace_path)
            except Exception:
                pass

        proc = await _run_in_sandbox(env, ["init"], timeout=timeout, cwd=workspace_path)
        if proc.returncode != 0:
            stderr = (proc.stderr or "")[:300]
            logger.warning("CodeGraph index failed: %s", stderr)
            return {"success": False, "error": stderr}
        status = await get_status(env, workspace_path)
        return {"success": True, **status}
    except Exception as e:
        logger.warning("CodeGraph index error: %s", e)
        return {"success": False, "error": str(e)}


async def _db_file_size(env: Any, workspace_path: str) -> int | None:
    """Return the size in bytes of the CodeGraph DB, or None if it doesn't exist."""
    try:
        path = f"{workspace_path}/.codegraph/codegraph.db"
        result = await env.run(f"stat -c %s {path} 2>/dev/null || echo 0", timeout=10)
        return int(result.stdout.strip())
    except Exception:
        return None


async def _wipe_codegraph_dir(env: Any, workspace_path: str) -> None:
    """Delete the .codegraph/ directory inside the sandbox."""
    try:
        path = f"{workspace_path}/.codegraph"
        await env.run(f"rm -rf {shlex_quote(path)}", timeout=15)
        logger.info("Wiped stale .codegraph/ at %s", path)
    except Exception as exc:
        logger.debug("_wipe_codegraph_dir failed (non-fatal): %s", exc)


async def get_status(env: Any, workspace_path: str) -> dict[str, Any]:
    """Show index statistics.

    Returns:
        dict with ``nodeCount``, ``edgeCount``, ``fileCount``
        (CodeGraph's ``status -j`` canonical field names). The
        orchestrator maps these to ``symbols``/``files`` for
        backward compatibility in the coordinator goal text.
    """
    try:
        proc = await _run_in_sandbox(env, ["status", "-j"], timeout=30, cwd=workspace_path)
        if proc.returncode == 0 and proc.stdout and proc.stdout.strip():
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
        return {"nodeCount": 0, "edgeCount": 0, "fileCount": 0}
    except Exception:
        return {"nodeCount": 0, "edgeCount": 0, "fileCount": 0}


async def query_symbols(env: Any, workspace_path: str, query: str, kind: str = "", limit: int = 10) -> list[dict]:
    """Search symbols by name."""
    try:
        args = ["query", "-j", "-p", workspace_path, "-l", str(limit)]
        if kind:
            args.extend(["-k", kind])
        args.append(query)
        proc = await _run_in_sandbox(env, args, timeout=30)
        if proc.returncode == 0 and proc.stdout and proc.stdout.strip():
            return json.loads(proc.stdout).get("results", [])
        return []
    except Exception as e:
        logger.debug("CodeGraph query failed: %s", e)
        return []


async def get_callers(env: Any, workspace_path: str, symbol: str, limit: int = 20) -> list[dict]:
    """Find every call site of a function."""
    try:
        args = ["callers", "-j", "-p", workspace_path, "-l", str(limit), symbol]
        proc = await _run_in_sandbox(env, args, timeout=30)
        if proc.returncode == 0 and proc.stdout and proc.stdout.strip():
            return json.loads(proc.stdout).get("callers", [])
        return []
    except Exception as e:
        logger.debug("CodeGraph callers failed: %s", e)
        return []


async def get_callees(env: Any, workspace_path: str, symbol: str, limit: int = 20) -> list[dict]:
    """List functions that a symbol calls."""
    try:
        args = ["callees", "-j", "-p", workspace_path, "-l", str(limit), symbol]
        proc = await _run_in_sandbox(env, args, timeout=30)
        if proc.returncode == 0 and proc.stdout and proc.stdout.strip():
            return json.loads(proc.stdout).get("callees", [])
        return []
    except Exception as e:
        logger.debug("CodeGraph callees failed: %s", e)
        return []


async def copy_db_to_host(env: Any, workspace_path: str, host_dir: str) -> str | None:
    """Copy the CodeGraph SQLite DB from sandbox to a host-accessible path.

    The sandbox keeps its own copy on the Docker volume. This exports
    it to the host filesystem for dashboard use or backup.

    This is the bridge that makes the KG survive container destruction:
    the per-session Docker volume is reaped when the session ends, but
    once we've copied the DB to the host, the next run can restore it
    into a fresh sandbox via `restore_db_from_host()` below.

    When the sandbox uses a host bind mount (``SANDBOX_WORKSPACE_DIR``),
    the file is already on the host at ``<mount>/<session>/...<db>``.
    In that case we symlink or copy to ``host_dir`` for the dashboard.
    """
    import shutil as _shutil
    db_path = os.path.join(workspace_path, ".codegraph", "codegraph.db")
    host_path = os.path.join(host_dir, "codegraph.db")
    try:
        os.makedirs(host_dir, exist_ok=True)
        # If the DB is already on the host via bind mount, skip docker cp
        if os.path.exists(host_path):
            return host_path
        container_id = getattr(env, "container_id", "")
        if not container_id:
            return None
        docker_bin = _shutil.which("docker") or "docker"
        result = subprocess.run(
            [docker_bin, "cp", f"{container_id}:{db_path}", host_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return host_path
        return None
    except Exception as e:
        logger.warning("copy_db_to_host failed: %s", e)
        return None


async def restore_db_from_host(env: Any, host_db_path: str, workspace_path: str) -> bool:
    """Reverse of `copy_db_to_host`: push a prior host-cached DB into a fresh
    sandbox so `codegraph init`/`sync` can do an incremental build instead
    of re-indexing the whole repo from scratch.

    Must be called on the BACKEND (not inside the sandbox) because `docker cp`
    is a host command. The sandbox does not have access to the host docker
    socket, so the restore must happen in the orchestrator's process.

    Returns True if the DB was placed at `<workspace_path>/.codegraph/codegraph.db`
    inside the sandbox, False otherwise (e.g., the file is missing or `docker cp`
    fails).
    """
    if not os.path.exists(host_db_path):
        return False
    container_id = getattr(env, "container_id", "")
    if not container_id:
        return False
    docker_bin = shutil.which("docker") or "docker"
    sandbox_db_dir = os.path.join(workspace_path, ".codegraph")
    target_path = os.path.join(sandbox_db_dir, "codegraph.db")
    try:
        # Ensure the parent dir exists in the sandbox. We run the mkdir
        # through `docker exec` rather than the sandbox's own run() so it
        # doesn't have to know about its own container_id.
        mkdir = subprocess.run(
            [docker_bin, "exec", container_id, "mkdir", "-p", sandbox_db_dir],
            capture_output=True, text=True, timeout=10,
        )
        if mkdir.returncode != 0:
            logger.debug("restore_db mkdir failed: %s", (mkdir.stderr or "").strip()[:200])
        cp = subprocess.run(
            [docker_bin, "cp", host_db_path, f"{container_id}:{target_path}"],
            capture_output=True, text=True, timeout=30,
        )
        return cp.returncode == 0
    except Exception as exc:
        logger.debug("restore_db_from_host failed: %s", exc)
        return False


def normalize_repo_url(repo_url: str) -> str:
    """Canonical form of a repo URL for graph-id hashing.

    Two URLs that point at the same repo should hash to the same id.
    Common normalizations:
      - Strip trailing ``.git`` (e.g. ``github.com/rails/rails.git`` ==
        ``github.com/rails/rails``)
      - Strip trailing ``/``
      - Lowercase the scheme + host
    """
    url = (repo_url or "").strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if "://" in url:
        scheme, rest = url.split("://", 1)
        host, _, path = rest.partition("/")
        url = f"{scheme.lower()}://{host.lower()}/{path}"
    else:
        url = url.lower()
    return url


def repo_graph_id(repo_url: str, branch: str = "") -> str:
    """Stable 16-char graph id keyed by `repo_url + branch`.

    Used to dedupe CodeGraph builds across runs against the same repo.
    A new run against the same `(repo_url, branch)` reuses the prior
    host-cached DB, so we pay the build cost once per repo (not once
    per session).

    The URL is normalized first (strip ``.git``, trailing ``/``,
    lowercase scheme/host) so equivalent forms (e.g. ``rails/rails``
    vs ``rails/rails.git``) produce the same id.
    """
    raw = f"{normalize_repo_url(repo_url)}|{(branch or 'main').strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def write_provenance(
    host_dir: str,
    *,
    repo_url: str,
    branch: str,
    graph_id: str,
    source_session_id: str = "",
    node_count: int | None = None,
    edge_count: int | None = None,
) -> None:
    """Write `provenance.json` next to the KG so dashboards can show which
    repo a graph_id came from. Best-effort; never raises.

    ``node_count`` and ``edge_count`` come from ``codegraph status -j``
    (canonical keys are ``nodeCount``/``edgeCount``).  When both are
    unset we read the live status from the sandbox to fill them in.
    """
    try:
        os.makedirs(host_dir, exist_ok=True)
        path = os.path.join(host_dir, "provenance.json")
        existing: dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    existing = json.load(fh) or {}
            except Exception:
                existing = {}
        existing.update({
            "graph_id": graph_id,
            "repo_url": repo_url,
            "branch": branch or "main",
            "last_indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_session_id": source_session_id,
            "node_count": node_count,
            "edge_count": edge_count,
            "builds": int(existing.get("builds", 0)) + 1,
        })
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)
    except Exception as exc:
        logger.debug("write_provenance failed (non-fatal): %s", exc)


async def select_affected_tests(
    env: Any, workspace_path: str,
    changed_files: list[str] | None = None,
    depth: int = 5, test_filter: str = "",
) -> list[str]:
    """Find which test files are affected by code changes using ``codegraph affected``."""
    if changed_files:
        args = ["affected", "--quiet", "--depth", str(depth)]
        if test_filter:
            args.extend(["--filter", test_filter])
        args.extend(changed_files)
    else:
        args = ["affected", "--stdin", "--quiet", "--depth", str(depth)]
    proc = await _run_in_sandbox(env, args, timeout=60)
    if not proc or proc.returncode != 0:
        return []
    return [f.strip() for f in (proc.stdout or "").splitlines() if f.strip()]
