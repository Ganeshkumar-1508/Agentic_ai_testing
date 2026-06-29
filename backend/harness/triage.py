"""Defect triage engine — KG-aware failure analysis.

Pattern: Rule-based triage enhanced with CodeGraph queries when available.
When a sandbox env with KG is provided, triage uses:
  - kg_search to find source files related to failing tests
  - kg_callers to trace call chains from test functions
  - git log to check if related files changed recently
Falls back to pure rule-based when no sandbox/KG available.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_RULES = {
    "critical": {"min_failures": 10, "patterns": ["assert", "exception", "500", "null", "crash", "security"]},
    "high": {"min_failures": 5, "patterns": ["timeout", "unauthorized", "validation"]},
    "medium": {"min_failures": 2, "patterns": ["element", "not found", "stale"]},
}

OWNER_PATTERNS: list[tuple[str, str]] = [
    ("test_auth", "auth-team"), ("test_login", "auth-team"),
    ("test_payment", "payments-team"), ("test_checkout", "checkout-team"),
    ("test_cart", "checkout-team"), ("test_api_", "api-team"),
    ("test_ui_", "frontend-team"), ("test_e2e_", "e2e-team"),
    ("test_perf", "perf-team"), ("test_sec", "security-team"),
]


async def triage_failures(db: Any, days: int = 7, sandbox_env: Any = None) -> list[dict[str, Any]]:
    """Run KG-aware triage on recent test failures. Returns prioritized defects."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await db.fetch(
        """SELECT test_name, error, run_id, created_at, healed_by_agent, status,
                  file_path, line_number
           FROM test_results WHERE status = 'failed' AND created_at >= $1
           ORDER BY created_at DESC""",
        since,
    )
    if not rows:
        return []

    by_test: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "test_name": "", "failures": 0, "first_seen": None, "last_seen": None,
        "errors": set(), "run_ids": set(), "healed": False, "file_paths": set(),
    })

    for r in rows:
        name = r["test_name"] or "unknown"
        entry = by_test[name]
        entry["test_name"] = name
        entry["failures"] += 1
        entry["run_ids"].add(r["run_id"] or "")
        entry["healed"] = entry["healed"] or bool(r.get("healed_by_agent"))
        if r["error"]:
            entry["errors"].add(r["error"][:200])
        if r.get("file_path"):
            entry["file_paths"].add(r["file_path"])
        ts = r["created_at"]
        if entry["first_seen"] is None or (ts and ts < entry["first_seen"]):
            entry["first_seen"] = ts
        if entry["last_seen"] is None or (ts and ts > entry["last_seen"]):
            entry["last_seen"] = ts

    # Batch KG queries for all failing tests (if sandbox available)
    kg_cache: dict[str, dict] = {}
    if sandbox_env:
        kg_cache = await _query_kg_batch(sandbox_env, list(by_test.keys()))

    triaged = []
    for name, entry in by_test.items():
        error_sample = next(iter(entry["errors"])) if entry["errors"] else ""
        kg_info = kg_cache.get(name, {})

        severity = _assign_severity_kg(entry["failures"], error_sample, kg_info)
        owner = _assign_owner_kg(name, kg_info)
        fix = _suggest_fix_kg(error_sample, kg_info)
        jira_summary = _generate_jira_summary(name, severity, error_sample)

        triaged.append({
            "test_name": name,
            "failures": entry["failures"],
            "first_seen": entry["first_seen"].isoformat() if entry["first_seen"] else "",
            "last_seen": entry["last_seen"].isoformat() if entry["last_seen"] else "",
            "unique_runs": len(entry["run_ids"]),
            "severity": severity,
            "suggested_owner": owner,
            "source_files": kg_info.get("source_files", []),
            "call_chain": kg_info.get("call_chain", []),
            "recent_changes": kg_info.get("recent_changes", ""),
            "suggested_fix": fix,
            "jira_summary": jira_summary,
            "error_sample": error_sample[:300],
            "healed": entry["healed"],
            "status": "resolved" if entry["healed"] else "open",
        })

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    triaged.sort(key=lambda x: (severity_order.get(x["severity"], 99), -x["failures"]))
    return triaged


async def _query_kg_batch(env: Any, test_names: list[str]) -> dict[str, dict]:
    """Query CodeGraph for source info about each failing test.

    Returns dict of test_name -> {source_files, call_chain, recent_changes}.
    """
    from harness.codegraph import query_symbols, get_callers

    result: dict[str, dict] = {}
    ws = "/workspace/repo"

    for name in test_names:
        info: dict[str, Any] = {"source_files": [], "call_chain": [], "recent_changes": ""}
        try:
            # Phase 1: Find the test's source file and the function it tests
            symbols = await query_symbols(env, ws, name, limit=5)
            for s in symbols:
                fp = s.get("file_path", "") or s.get("file", "") or ""
                if fp and fp not in info["source_files"]:
                    info["source_files"].append(fp)

            # Phase 2: If we found symbols, trace callers for the first one
            if symbols:
                first = symbols[0]
                sym_id = first.get("id") or first.get("name") or ""
                if sym_id:
                    callers = await get_callers(env, ws, sym_id, limit=5)
                    info["call_chain"] = [
                        c.get("name", "") or c.get("caller", "") or ""
                        for c in callers if (c.get("name", "") or c.get("caller", "") or "")
                    ]

            # Phase 3: Check git log for recent changes to source files
            if info["source_files"]:
                files_str = " ".join(f"'{f}'" for f in info["source_files"][:5])
                git = await env.run(
                    f"cd {ws} && git log --oneline -5 -- {files_str} 2>&1 | head -5",
                    timeout=10,
                )
                if git and git.stdout:
                    info["recent_changes"] = git.stdout.strip()

        except Exception as e:
            logger.debug("KG query failed for test %s: %s", name, e)

        result[name] = info

    return result


def _assign_severity_kg(failures: int, error: str, kg_info: dict) -> str:
    """Assign severity — KG-enhanced: if source files changed recently, escalate."""
    base = _assign_severity(failures, error)

    # Escalate if source files recently changed (regression likely)
    if kg_info.get("recent_changes") and base not in ("critical",):
        sev_order = {"low": 0, "medium": 1, "high": 2}
        if sev_order.get(base, 0) < 2:
            return "high"

    return base


def _assign_severity(failures: int, error: str) -> str:
    error_lower = error.lower()
    for severity, rules in SEVERITY_RULES.items():
        if failures >= rules["min_failures"]:
            for pattern in rules["patterns"]:
                if pattern in error_lower:
                    return severity
    if failures >= 10:
        return "high"
    if failures >= 3:
        return "medium"
    return "low"


def _assign_owner_kg(test_name: str, kg_info: dict) -> str:
    """Assign owner — KG-enhanced: use source file path patterns."""
    for sf in kg_info.get("source_files", []):
        sf_lower = sf.lower()
        if "auth" in sf_lower or "login" in sf_lower:
            return "auth-team"
        if "payment" in sf_lower:
            return "payments-team"
        if "api" in sf_lower:
            return "api-team"
        if "ui" in sf_lower or "component" in sf_lower or "page" in sf_lower:
            return "frontend-team"
        if "model" in sf_lower or "db" in sf_lower or "repo" in sf_lower:
            return "backend-team"
    return _assign_owner(test_name)


def _assign_owner(test_name: str) -> str:
    for pattern, owner in OWNER_PATTERNS:
        if test_name.startswith(pattern):
            return owner
    return "unassigned"


def _suggest_fix_kg(error: str, kg_info: dict) -> str:
    """Suggest fix — KG-enhanced: include source file context."""
    base = _suggest_fix(error, "")
    if kg_info.get("source_files"):
        files = kg_info["source_files"][:3]
        base = f"Files: {', '.join(files)}. " + base
    if kg_info.get("call_chain"):
        chain = " → ".join(kg_info["call_chain"][:4])
        base = f"Call chain: {chain}. " + base
    if kg_info.get("recent_changes"):
        base = f"Recent changes detected. " + base
    return base


def _suggest_fix(error: str, _test_name: str = "") -> str:
    if not error:
        return "Investigate — no error message captured"
    e = error.lower()
    if "assert" in e or "expected" in e:
        return "Check assertion values — expected/actual mismatch. Verify test data and expected outputs."
    if "element" in e and ("not found" in e or "stale" in e):
        return "UI element locator may have changed. Check for recent UI updates or try alternative selectors."
    if "timeout" in e:
        return "Test may need longer wait times or the service may be slow. Consider increasing timeout thresholds."
    if "500" in e or "internal server" in e:
        return "Backend returned 500 error. Check server logs for the failing endpoint."
    if "401" in e or "unauthorized" in e:
        return "Authentication issue. Verify test credentials and token expiry."
    if "null" in e or "undefined" in e:
        return "Null reference error. Check that all required data is initialized before use."
    return "Review test failure logs and trace to identify root cause."


def _generate_jira_summary(test_name: str, severity: str, error: str) -> str:
    error_short = (error or "No error message")[:80]
    return f"[{severity.upper()}] Test failure: {test_name} — {error_short}"


async def create_jira_ticket(
    db: Any, test_name: str, summary: str, error: str, severity: str, webhook_url: str = "",
) -> dict[str, Any]:
    if webhook_url:
        import httpx
        try:
            payload = {
                "summary": summary,
                "description": f"h3. Defect Details\n\n*Test:* {test_name}\n*Severity:* {severity}\n*Error:*\n{{code}}{error[:2000]}{{code}}",
                "priority": severity.upper(),
                "labels": ["test-failure", "auto-triaged"],
            }
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.post(webhook_url, json=payload)
                return {"created": resp.status_code == 200, "response": resp.status_code}
        except Exception as e:
            return {"created": False, "error": str(e)}
    return {"created": False, "note": "No webhook URL configured"}
