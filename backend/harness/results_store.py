from __future__ import annotations

import json
import logging
import re
from typing import Any

from harness.memory.database import Database

logger = logging.getLogger(__name__)


async def persist_pipeline_results(db: Database, run_id: str, repo_url: str = "", workspace_path: str = "") -> None:
    """Parse test results from trace events and persist to DB.

    Call this after agent.run() completes. Reads tool:end trace events
    for test_executor, parses structured results, inserts into test_results,
    and updates pipeline_runs with aggregate counts.

    If repo_url and workspace_path are provided, also syncs CODEOWNERS
    from the cloned workspace to populate the test_owners table.
    """
    events = await db.fetch(
        "SELECT event_data FROM trace_events WHERE run_id = $1 AND event_type IN ('tool.execution.completed', 'tool:end') ORDER BY created_at ASC",
        run_id,
    )
    test_count = 0
    pass_count = 0
    fail_count = 0
    skip_count = 0
    total_duration = 0.0
    test_names_seen: set[str] = set()

    for row in events:
        try:
            data = json.loads(row["event_data"]) if isinstance(row["event_data"], str) else row["event_data"]
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("name") != "test_executor":
            continue

        output = data.get("output_preview", "")
        results = _parse_test_output(output)

        for t in results.get("tests", []):
            name = t.get("name", "unknown")
            if name in test_names_seen:
                continue
            test_names_seen.add(name)
            test_count += 1
            status = t.get("status", "unknown")
            duration = t.get("duration", 0.0)
            total_duration += duration

            if status == "passed":
                pass_count += 1
            elif status == "failed":
                fail_count += 1
            elif status == "skipped":
                skip_count += 1

            try:
                await db.execute(
                    "INSERT INTO test_results (run_id, test_name, status, duration_ms, error) VALUES ($1, $2, $3, $4, $5)",
                    run_id, name, status, duration, t.get("error", ""),
                )
                # Update flaky score after each test result
                from harness.flaky_detector import update_flaky_score
                await update_flaky_score(db, name)
                # Attempt self-healing if test failed with locator error
                if status == "failed":
                    from harness.self_healing import attempt_heal
                    await attempt_heal(db, name, t.get("error", ""), run_id)
                # Check for coverage data in the output and ingest it
                coverage_text = t.get("coverage", "") or t.get("coverage_output", "") or t.get("raw_output", "")
                if coverage_text and "coverage" in str(coverage_text).lower():
                    try:
                        from harness.coverage_gaps import ingest_coverage_report
                        await ingest_coverage_report(db, run_id, "", "", coverage_text)
                    except Exception:
                        pass
            except Exception:
                pass

        if results.get("counts"):
            c = results["counts"]
            if not test_count:
                test_count = c.get("total", 0)
                pass_count = c.get("passed", 0)
                fail_count = c.get("failed", 0)
                skip_count = c.get("skipped", 0)

    if test_count > 0:
        try:
            await db.execute(
                "UPDATE pipeline_runs SET test_count = $1, passed_count = $2, failed_count = $3, skipped_count = $4, duration = $5 WHERE id = $6",
                test_count, pass_count, fail_count, skip_count, total_duration, run_id,
            )
        except Exception:
            pass

    # Sync CODEOWNERS for test ownership
    if repo_url:
        try:
            from harness.codeowners_parser import read_codeowners_from_workspace, fetch_codeowners_via_api, sync_test_owners

            content = None
            if workspace_path:
                content = await read_codeowners_from_workspace(workspace_path)
            if not content:
                content = await fetch_codeowners_via_api(repo_url)
            if content:
                count = await sync_test_owners(db, repo_url, content)
                if count:
                    logger.info("Synced %d CODEOWNERS entries for %s", count, repo_url)
        except Exception:
            logger.debug("CODEOWNERS sync skipped", exc_info=True)


def _parse_test_output(output: str) -> dict[str, Any]:
    """Parse test executor text output into structured results."""
    result: dict[str, Any] = {"tests": [], "counts": {}}

    passed = output.count("PASSED")
    failed = output.count("FAILED")
    skipped_token = output.count("SKIPPED")

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Try parsing: "✓ test_name (0.12s)" or "✗ test_name (0.34s)"
        m = re.match(r"[✓✔✗✘✕✖✗✘×]?\s*(.+?)\s+\(([\d.]+)s\)", line)
        if m:
            name = m.group(1).strip()
            duration = float(m.group(2))
            if "FAILED" in line:
                status = "failed"
            elif "SKIPPED" in line or "skip" in line.lower():
                status = "skipped"
            else:
                status = "passed" if "PASSED" in line or "passed" in line.lower() else "passed"
            result["tests"].append({"name": name, "status": status, "duration": duration})
            continue

        # Try parsing: "✓ name" or "✗ name" (no duration)
        m = re.match(r"[✓✔✗✘✕✖✓✔✗✘]\s+(.+)", line)
        if m:
            name = m.group(1).strip()
            has_fail = any(w in line.lower() for w in ["fail", "error", "✗", "✘"])
            has_pass = any(w in line.lower() for w in ["pass", "✓", "✔"])
            status = "failed" if has_fail else "passed" if has_pass else "unknown"
            result["tests"].append({"name": name, "status": status, "duration": 0})
            continue

        # Try pytest summary: "1 passed, 2 failed, 3 skipped in 4.5s"
        m = re.match(r"(\d+)\s+passed.*?(\d+)\s+failed.*?(\d+)\s+skipped.*?in\s+([\d.]+)s", line)
        if m:
            result["counts"] = {"passed": int(m.group(1)), "failed": int(m.group(2)), "skipped": int(m.group(3)), "total": int(m.group(1)) + int(m.group(2)) + int(m.group(3))}
            continue

    if result["counts"]:
        return result
    if not result["tests"] and (passed or failed or skipped_token):
        result["counts"] = {"passed": passed, "failed": failed, "skipped": skipped_token, "total": passed + failed + skipped_token}
    return result
