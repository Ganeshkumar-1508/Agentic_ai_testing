"""Test Impact Analysis API — maps code changes to affected tests."""

from __future__ import annotations

import subprocess

from fastapi import APIRouter, Request

from ..deps import get_db
from harness.codegraph import select_affected_tests
from harness.backends.factory import get_backend

router = APIRouter(prefix="/api/impact", tags=["impact"])


@router.post("/analyze")
async def analyze_impact(request: Request, changed_files: list[str] = [], repo_path: str = ""):
    """Analyze which tests are affected by changed files.

    If repo_path is provided, runs `git diff --name-only` to get changed files.
    If changed_files is provided directly, uses those.

    Delegates to CodeGraph's `codegraph affected` (via the
    `harness.codegraph.select_affected_tests` wrapper). Per the
    CodeGraph docs, this traces import dependencies transitively
    across all indexed languages, not just Python AST imports.
    """
    sm = SandboxManager()
    # The orchestrator keeps the running env in its sandbox manager. The
    # API surface operates on the host's view of the repo, so the
    # delegate call needs an env to be available. If there's no
    # current session, the wrapper returns an empty list and the
    # router responds accordingly.
    env = await sm.get_env("") if hasattr(sm, "get_env") else None

    if not changed_files and repo_path:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1"],
                cwd=repo_path, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                changed_files = [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            pass

    if not changed_files:
        return {"impacted_tests": [], "uncovered_changes": [], "error": "No changes detected"}

    if env is None:
        # No active sandbox — fall back to the host-side TIA helper so
        # the API still works for host-mode runs (PRs, pipeline runs
        # that operate on the host filesystem).
        from harness.test_impact import compute_impact_summary
        # repo_path is the host path; if absent, compute against the
        # current working directory.
        target = repo_path or ""
        summary = compute_impact_summary(target)
        return {
            "impacted_tests": summary.get("affected_tests", []),
            "uncovered_changes": [],
            "total_changed": len(summary.get("changed_files", [])),
            "summary": f"CodeGraph not available; used host TIA fallback",
        }

    affected = await select_affected_tests(env, "/workspace/repo", changed_files=changed_files)
    return {
        "impacted_tests": affected,
        "uncovered_changes": [],
        "total_changed": len(changed_files),
        "summary": (
            f"CodeGraph `affected` found {len(affected)} test(s) "
            f"affected by {len(changed_files)} changed file(s)."
        ),
    }


@router.get("/status")
async def get_impact_status(request: Request):
    """Get summary of current test impact analysis state."""
    db = get_db(request)
    try:
        coverage_row = await db.fetchrow(
            "SELECT COUNT(DISTINCT run_id) as run_count, "
            "COUNT(*) as test_count FROM test_results"
        )
        return {
            "total_test_runs": coverage_row["run_count"] if coverage_row else 0,
            "total_test_results": coverage_row["test_count"] if coverage_row else 0,
        }
    except Exception as e:
        return {"error": str(e)}
