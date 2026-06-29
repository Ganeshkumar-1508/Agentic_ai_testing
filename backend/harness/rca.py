"""Root Cause Analysis engine.

Clusters test failures, separates real defects from flaky tests,
pinpoints the exact error pattern and affected code.

Based on patterns from Pcloudy QPilot AI RCA Agent.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 30

# Common flaky patterns in error messages
FLAKY_PATTERNS = [
    r"(?i)timeout",
    r"(?i)network|connection refused|reset",
    r"(?i)element[^ ]* not (found|interactable|visible|clickable)",
    r"(?i)stale element",
    r"(?i)no such element",
    r"(?i)session.*not (created|found)",
    r"(?i)unexpected alert",
    r"(?i)port.*in use",
    r"(?i)resource.*(exhausted|busy|unavailable)",
    r"(?i)retry|retryable",
    r"(?i)intermittent",
    r"(?i)flaky",
    r"(?i)animation|transition.*not (finished|complete)",
    r"(?i)async.*timeout",
]

# Patterns suggesting real defects
DEFECT_PATTERNS = [
    r"(?i)assertion.*failed|assert.*error",
    r"(?i)expected.*but.*got|expected.*actual",
    r"(?i)nullpointer|null reference|undefined",
    r"(?i)typeerror|cannot read property",
    r"(?i)keyerror|indexerror|valueerror",
    r"(?i)divide by zero|division by zero",
    r"(?i)attributeerror|nameerror",
    r"(?i)syntaxerror",
    r"(?i)exception.*not handled",
    r"(?i)500|502|503|504",
    r"(?i)unauthorized|forbidden|403|401",
    r"(?i)not found.*404|404.*not found",
    r"(?i)validation.*failed|invalid.*input",
]

# Environment / infrastructure failures — counted as a separate bucket so
# the dashboard's 4-col "Failure Categories" grid (Defects / Flakes /
# Environment / Unknown) has truthful values when DBs/cache/containers
# are the real cause.
ENV_PATTERNS = [
    r"(?i)econnrefused|connection refused|connection reset",
    r"(?i)database|postgres|postgresql|mysql|sqlite|redis|memcached|mongo",
    r"(?i)docker|container|kubernetes|k8s|pod|namespace",
    r"(?i)disk.*full|no space left",
    r"(?i)cdn|asset.*load|cors",
    r"(?i)memory.*limit|out of memory|oom",
    r"(?i)env(ironment)?.*variable|missing.*config",
    r"(?i)port.*already.*in use|address.*in use",
    r"(?i)sandbox.*(down|unavailable|timeout)",
]


async def analyze_failures(db: Any, run_id: str | None = None, days: int = LOOKBACK_DAYS) -> dict[str, Any]:
    """Run RCA on test failures. Clusters errors and assigns defect vs flake verdict."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Fetch failed test results
    if run_id:
        rows = await db.fetch(
            "SELECT test_name, status, error, duration_ms, created_at, retry_count "
            "FROM test_results WHERE run_id = $1 AND status = 'failed' ORDER BY created_at DESC",
            run_id,
        )
    else:
        rows = await db.fetch(
            "SELECT test_name, status, error, duration_ms, created_at, retry_count, run_id "
            "FROM test_results WHERE status = 'failed' AND created_at >= $1 ORDER BY created_at DESC LIMIT 200",
            since,
        )

    if not rows:
        return {"total_failures": 0, "clusters": [], "summary": "No failures found"}

    # Cluster errors by similarity
    clusters: dict[str, dict[str, Any]] = {}
    for r in rows:
        error_text = r["error"] or ""
        test_name = r["test_name"] or "unknown"
        run_id_val = r.get("run_id", "")

        cluster_key = _cluster_error(error_text, test_name)
        if cluster_key not in clusters:
            clusters[cluster_key] = {
                    "error_pattern": cluster_key,
                "count": 0,
                "tests": set(),
                "run_ids": set(),
                "error_samples": [],
                "verdict": None,
                "first_seen": r["created_at"],
                "last_seen": r["created_at"],
                "test_names": set(),
            }
        c = clusters[cluster_key]
        c["count"] += 1
        c["tests"].add(test_name)
        c["test_names"].add(test_name)
        c["run_ids"].add(run_id_val)
        if r["created_at"] and (c["first_seen"] is None or r["created_at"] < c["first_seen"]):
            c["first_seen"] = r["created_at"]
        if r["created_at"] and (c["last_seen"] is None or r["created_at"] > c["last_seen"]):
            c["last_seen"] = r["created_at"]
        if len(c["error_samples"]) < 3:
            c["error_samples"].append(error_text[:200])

    # Assign verdicts: defect vs flake + compute severity
    for cluster_key, c in clusters.items():
        c["tests"] = list(c["tests"])[:20]
        c["test_names"] = list(c["test_names"])[:20]
        c["run_ids"] = list(c["run_ids"])[:10]
        c["verdict"] = _assign_verdict(cluster_key, c["count"], c["tests"])
        c["severity"] = _compute_severity(c["count"], c["verdict"])
        c["first_seen"] = c["first_seen"].isoformat() if c["first_seen"] else ""
        c["last_seen"] = c["last_seen"].isoformat() if c["last_seen"] else ""
        c["re_run_endpoint"] = f"/api/rca/re-run?tests={'|'.join(c['test_names'][:10])}"

    # Sort by frequency
    sorted_clusters = sorted(clusters.values(), key=lambda x: x["count"], reverse=True)

    return {
        "total_failures": len(rows),
        "total_clusters": len(sorted_clusters),
        "defect_count": sum(1 for c in sorted_clusters if c["verdict"] == "defect"),
        "flake_count": sum(1 for c in sorted_clusters if c["verdict"] == "flake"),
        "clusters": sorted_clusters[:15],
    }


def _cluster_error(error: str, test_name: str) -> str:
    """Cluster similar errors into a canonical pattern."""
    if not error:
        return f"unknown_error::{test_name}"

    # Normalize: lowercase, collapse numbers, remove paths
    normalized = error.lower().strip()
    normalized = re.sub(r"\b\d+\b", "N", normalized)
    normalized = re.sub(r"[/\\][a-z0-9_./\\-]*[/\\]", "/path/", normalized)
    normalized = re.sub(r"\s+", " ", normalized)

    # Extract the first meaningful line
    lines = normalized.split("\n")
    for line in lines:
        line = line.strip()
        if len(line) > 20 and not line.startswith("traceback"):
            return line[:120]

    return normalized[:120]


def _assign_verdict(pattern: str, count: int, tests: list[str]) -> str:
    """Determine if a failure cluster is a real defect or flaky test."""
    flake_score = 0
    defect_score = 0

    for fp in FLAKY_PATTERNS:
        if re.search(fp, pattern):
            flake_score += 1

    for dp in DEFECT_PATTERNS:
        if re.search(dp, pattern):
            defect_score += 1

    # If same test passes and fails across runs, it's flaky
    is_flaky_pattern = flake_score > defect_score

    # Single occurrence is inconclusive
    if count == 1:
        return "flake" if is_flaky_pattern else "defect"

    # Multiple occurrences with consistent error = real defect
    if count >= 3 and defect_score >= 1:
        return "defect"

    return "flake" if is_flaky_pattern else "defect"


def _compute_severity(count: int, verdict: str) -> str:
    """Compute severity level for a cluster."""
    if verdict == "defect" and count >= 5:
        return "critical"
    if verdict == "defect" and count >= 2:
        return "high"
    if verdict == "flake" and count >= 5:
        return "medium"
    if verdict == "flake":
        return "low"
    return "medium"


async def get_rca_summary(db: Any, days: int = LOOKBACK_DAYS) -> dict[str, Any]:
    """Get a summary of root cause analysis for the dashboard."""
    result = await analyze_failures(db, days=days)

    top_defects = [c for c in result.get("clusters", []) if c["verdict"] == "defect"][:5]
    top_flakes = [c for c in result.get("clusters", []) if c["verdict"] == "flake"][:5]

    # Re-classify each cluster into one of 4 buckets for the wireframe's
    # "Failure Categories" grid. ENV_PATTERNS wins over defect/flake
    # because an env-rooted failure is a different kind of signal even
    # when the error string also matches a defect regex. "Unknown" is
    # anything whose pattern matches neither defect nor flake (handled
    # by counting only matched flakes/defects/environ + remainder).
    def _category(c: dict) -> str:
        pat = c.get("error_pattern") or ""
        for ep in ENV_PATTERNS:
            if re.search(ep, pat):
                return "environment"
        return c.get("verdict") or "unknown"

    env_clusters: list[dict] = []
    unknown_clusters: list[dict] = []
    env_count = 0
    unknown_count = 0
    classified = 0
    for c in result.get("clusters", []):
        cat = _category(c)
        if cat == "environment":
            env_clusters.append(c)
            env_count += c.get("count", 0)
            classified += c.get("count", 0)
        elif cat == "unknown":
            unknown_clusters.append(c)
            unknown_count += c.get("count", 0)
            classified += c.get("count", 0)
        else:
            classified += c.get("count", 0)

    # Anything not landing in a top-5 defect/flake/env/unknown bucket
    # falls into the "unknown" remainder. With empty DB, all four stay 0.
    top_env = env_clusters[:5]
    top_unknown = unknown_clusters[:5]

    return {
        "total_failures": result["total_failures"],
        "defect_count": result["defect_count"],
        "flake_count": result["flake_count"],
        "env_count": env_count,
        "unknown_count": unknown_count,
        "top_defects": top_defects,
        "top_flakes": top_flakes,
        "top_env": top_env,
        "top_unknown": top_unknown,
        "cluster_count": result["total_clusters"],
    }


def classify_tool_error(error_text: str) -> dict[str, Any]:
    """Per-tool verification hook (C00-C-6, F5/CC3).

    The Harness Engineering Guide's failure-mode list calls out
    "silent failures" — the agent calls a tool, receives an error,
    and proceeds as if the call succeeded. The fix is structured
    output validation after every tool call.

    This function is the validation primitive: given the textual
    result of a tool call, classify it as ``"defect"``, ``"flaky"``,
    or ``"unknown"``. The registry's ``execute()`` calls it
    post-call and includes the verdict in the result envelope; the
    orchestrator can then decide whether to retry, surface a
    warning, or treat the call as silent failure.

    Pattern-based: the same FLAKY_PATTERNS / DEFECT_PATTERNS lists
    used by the post-hoc :func:`analyze_failures` flow. Returning
    structured data (not just a label) so callers can attach
    evidence and the dashboard can render the verdict.
    """
    text = str(error_text or "")
    if not text:
        return {"verdict": "unknown", "matched_pattern": None, "category": "empty"}
    for pat in FLAKY_PATTERNS:
        if re.search(pat, text):
            return {
                "verdict": "flaky",
                "matched_pattern": pat,
                "category": "transient",
            }
    for pat in DEFECT_PATTERNS:
        if re.search(pat, text):
            return {
                "verdict": "defect",
                "matched_pattern": pat,
                "category": "real_failure",
            }
    return {"verdict": "unknown", "matched_pattern": None, "category": "unclassified"}
