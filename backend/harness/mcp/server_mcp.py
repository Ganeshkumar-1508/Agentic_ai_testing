"""TestAI MCP Server — expose TestAI as a Model Context Protocol server.

IDEs (Cursor, VS Code, Windsurf, Claude Code) connect via MCP transport
and can trigger runs, check results, query knowledge graphs, and more.

Usage:
    python -m backend.harness.mcp.server_mcp             # stdio (default)
    python -m backend.harness.mcp.server_mcp http        # Streamable HTTP
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "TestAI",
    instructions="AI-powered test automation and code validation platform. "
    "Trigger runs, inspect results, analyze code, and manage PRs from your IDE. "
    "Use prompts for common workflows: /analyze-failures, /generate-tests, /review-changes.",
)

API_BASE = os.environ.get("TESTAI_API_URL", "http://localhost:8001")
_RUNNING_TEXT = "running"


# ── Helpers ────────────────────────────────────────────────────────


def _fmt_status(s: str) -> str:
    return {"completed": "[PASS]", "failed": "[FAIL]", "running": "[RUN]", "pending": "[--]"}.get(s, "[??]")


# ── Resources (data loaded into LLM context) ───────────────────────


@mcp.resource("testai://runs/latest")
def resource_latest_runs() -> str:
    """Most recent pipeline runs with status summary."""
    import httpx
    try:
        r = httpx.get(f"{API_BASE}/api/runs?limit=5", timeout=10)
        runs = r.json().get("runs", [])
        if not runs:
            return "No runs found."
        return "\n".join(
            f"- {_fmt_status(r.get('status',''))} `{r['id'][:8]}` — "
            f"{r.get('testCount',0)} tests, {r.get('passedCount',0)}/{r.get('failedCount',0)} pass/fail"
            for r in runs
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.resource("testai://runs/{run_id}")
def resource_run_detail(run_id: str) -> str:
    """Detailed results for a pipeline run."""
    import httpx
    try:
        run = httpx.get(f"{API_BASE}/api/runs/{run_id}", timeout=10).json().get("run", {})
        if not run:
            return "Run not found."
        lines = [f"# Run {run.get('id', run_id)[:8]}  Status: {run.get('status','?')}"]
        if run.get("testCount"):
            lines.append(f"Tests: {run['testCount']} total, {run['passedCount']} passed, {run['failedCount']} failed")
        if run.get("duration"):
            lines.append(f"Duration: {run['duration']}ms")
        if run.get("costUsd"):
            lines.append(f"Cost: ${run['costUsd']:.4f}")
        if run.get("requirements"):
            lines.append(f"\nRequirement: {run['requirements']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.resource("testai://runs/{run_id}/results")
def resource_run_results(run_id: str) -> str:
    """Raw test results for a run — all tests with status and errors."""
    import httpx
    try:
        t = httpx.get(f"{API_BASE}/api/runs/{run_id}/test-results", timeout=10).json().get("tests", [])
        if not t:
            return "No test results found."
        lines = [f"# Test Results ({len(t)} tests)"]
        failed = [x for x in t if x.get("status") == "failed"]
        if failed:
            lines.append(f"\n## Failed ({len(failed)})")
            for f in failed[:15]:
                lines.append(f"- {f['testName']}: {f.get('error','')[:120]}")
        passed = [x for x in t if x.get("status") == "passed"]
        if passed:
            lines.append(f"\n## Passed ({len(passed)})")
            for p in passed[:10]:
                lines.append(f"- {p['testName']} ({p.get('durationMs',0)}ms)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.resource("testai://runs/{run_id}/coverage")
def resource_run_coverage(run_id: str) -> str:
    """Coverage summary for a pipeline run."""
    import httpx
    try:
        reports = httpx.get(f"{API_BASE}/api/coverage/history?limit=20", timeout=10).json().get("reports", [])
        cov = [r for r in reports if r.get("runId") == run_id]
        if not cov:
            return "No coverage data for this run."
        return "\n".join(
            f"- {c['language']} ({c['framework']}): {c['lineCoverage']}% line coverage, {c['totalLines']} lines"
            for c in cov
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.resource("testai://knowledge-graph/search/{query}")
def resource_kg_search(query: str) -> str:
    """Search the code knowledge graph. Returns files, functions, classes matching the query."""
    import httpx
    try:
        graphs = httpx.get(f"{API_BASE}/api/knowledge-graph/recent?limit=1", timeout=10).json().get("graphs", [])
        if not graphs:
            return "No knowledge graph found. Run ANALYZE first."
        resp = httpx.post(f"{API_BASE}/api/knowledge-graph/{graphs[0]['id']}/search",
                          json={"query": query, "max_results": 8}, timeout=10)
        results = resp.json().get("results", [])
        if not results:
            return f"No nodes matching '{query}'."
        return "\n".join(
            f"- **{r.get('name', r.get('id','?'))}** — {r.get('summary','')[:120]}"
            for r in results
        )
    except Exception as e:
        return f"Error: {e}"


# ── Tools (actions the LLM can take) ───────────────────────────────


@mcp.tool()
def run_tests(requirements: str, repo_url: str = "", branch: str = "main") -> str:
    """Trigger a new test pipeline run.

    Args:
        requirements: Description of what to test or fix (e.g., "Fix failing auth tests")
        repo_url: Optional repository URL (e.g., "owner/repo"). Uses default if omitted.
        branch: Branch to run against (default: main).
    """
    import httpx
    import uuid
    try:
        run_id = str(uuid.uuid4())
        resp = httpx.post(f"{API_BASE}/api/runs",
                          json={"requirements": requirements, "repo_url": repo_url, "branch": branch}, timeout=15)
        if resp.is_success:
            data = resp.json()
            rid = data.get("run_id", run_id)
            return f"Run created: `{rid[:8]}`\nStatus: pending\nTrack at: {API_BASE}/api/runs/{rid}"
        return f"Error {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return f"Failed: {e}"


@mcp.tool()
def list_runs(limit: int = 10, status: str = "") -> str:
    """List recent pipeline runs with optional status filter.

    Args:
        limit: Max results (default 10, max 50).
        status: Filter by status (completed, failed, running, pending). Empty = all.
    """
    import httpx
    try:
        r = httpx.get(f"{API_BASE}/api/runs", params={"limit": min(limit, 50), **(status and {"status": status})}, timeout=10)
        runs = r.json().get("runs", [])
        if not runs:
            return "No runs found."
        return "\n".join(
            f"- `{r['id'][:8]}` {r.get('status','?')} — {r.get('testCount',0)} tests, "
            f"{r.get('passedCount',0)}/{r.get('failedCount',0)} pass/fail"
            for r in runs
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_run_results(run_id: str) -> str:
    """Get detailed test results for a pipeline run.

    Args:
        run_id: The run ID (full or first 8 chars).
    """
    import httpx
    try:
        run = httpx.get(f"{API_BASE}/api/runs/{run_id}", timeout=10).json().get("run", {})
        tests = httpx.get(f"{API_BASE}/api/runs/{run_id}/test-results", timeout=10).json().get("tests", [])
        lines = [f"# Run {run.get('id', run_id)[:8]}  Status: {run.get('status','?')}"]
        if run.get("testCount"):
            lines.append(f"Tests: {run['testCount']} | Passed: {run['passedCount']} | Failed: {run['failedCount']}")
        failed = [t for t in tests if t.get("status") == "failed"]
        if failed:
            lines.append(f"\n## Failed ({len(failed)})")
            for t in failed[:10]:
                lines.append(f"- {t['testName']}: {t.get('error','')[:120]}")
        return "\n".join(lines) if len(lines) > 1 else "Run not found."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def search_knowledge_graph(query: str) -> str:
    """Search the code knowledge graph for files, functions, or classes.

    Args:
        query: Search term matching node names, summaries, and tags.
    """
    import httpx
    try:
        graphs = httpx.get(f"{API_BASE}/api/knowledge-graph/recent?limit=1", timeout=10).json().get("graphs", [])
        if not graphs:
            return "No knowledge graph. Run a pipeline with ANALYZE enabled."
        resp = httpx.post(f"{API_BASE}/api/knowledge-graph/{graphs[0]['id']}/search",
                          json={"query": query, "max_results": 5}, timeout=10)
        results = resp.json().get("results", [])
        if not results:
            return f"No results for '{query}'."
        return "\n".join(
            f"- **{r.get('name', r.get('id','?'))}** — {r.get('summary','')[:100]}"
            for r in results
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_run_artifacts(run_id: str) -> str:
    """List available artifacts from a pipeline run (test files, coverage reports, logs).

    Args:
        run_id: The run ID.
    """
    import httpx
    try:
        events = httpx.get(f"{API_BASE}/api/runs/{run_id}/events?limit=50", timeout=10).json().get("events", [])
        files = []
        for e in events:
            d = e.get("data", {})
            if e["type"] == "tool_result" and d.get("name") in ("write_file", "edit_file"):
                files.append(d.get("name", "?"))
        if not files:
            return "No artifacts found for this run."
        return f"Artifacts from run `{run_id[:8]}`:\n" + "\n".join(f"- {f}" for f in set(files)[:20])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def re_run_tests(run_id: str, test_names: str = "") -> str:
    """Re-run specific tests from a previous run.

    Args:
        run_id: Original run ID.
        test_names: Comma-separated test names. Empty = re-run all failed.
    """
    import httpx
    try:
        # Fetch failed tests if none specified
        if not test_names.strip():
            tests = httpx.get(f"{API_BASE}/api/runs/{run_id}/test-results", timeout=10).json().get("tests", [])
            failed = [t["testName"] for t in tests if t.get("status") == "failed"]
            if not failed:
                return "No failed tests to re-run."
            test_names = ",".join(failed)

        selected = [t.strip() for t in test_names.split(",") if t.strip()]
        resp = httpx.post(f"{API_BASE}/api/runs/{run_id}/rerun",
                          json={"test_names": selected}, timeout=15)
        if resp.is_success:
            data = resp.json()
            rid = data.get("run_id", "")
            return f"Re-run created: `{rid[:8]}`\nTests: {len(selected)}\nTrack at: {API_BASE}/api/runs/{rid}"
        return f"Error: {resp.text[:200]}"
    except Exception as e:
        return f"Failed: {e}"


@mcp.tool()
def create_pr_comment(run_id: str, pr_number: int, repo: str = "") -> str:
    """Post test results as a comment on a GitHub PR.

    Args:
        run_id: Run ID whose results to post.
        pr_number: GitHub PR number.
        repo: Repository in "owner/repo" format. Uses default if omitted.
    """
    import httpx
    try:
        run = httpx.get(f"{API_BASE}/api/runs/{run_id}", timeout=10).json().get("run", {})
        tests = httpx.get(f"{API_BASE}/api/runs/{run_id}/test-results", timeout=10).json().get("tests", [])
        passed = sum(1 for t in tests if t.get("status") == "passed")
        failed = [t for t in tests if t.get("status") == "failed"]

        body = f"## TestAI Results\n\n**Status:** {run.get('status','?')}\n"
        body += f"**Tests:** {len(tests)} total, {passed} passed, {len(failed)} failed\n"
        if failed:
            body += "\n### Failed Tests\n"
            for f in failed[:5]:
                body += f"- `{f['testName']}`: {f.get('error','')[:200]}\n"
        if run.get("duration"):
            body += f"\nDuration: {run['duration']}ms"
        if run.get("costUsd"):
            body += f" | Cost: ${run['costUsd']:.4f}"

        return f"PR comment ready for PR #{pr_number}:\n\n{body}"
    except Exception as e:
        return f"Error: {e}"


# ── Prompts (reusable workflow templates) ──────────────────────────


@mcp.prompt()
def analyze_failures() -> str:
    """Diagnose failures from the most recent failed run and suggest fixes."""
    return (
        "Please analyze the most recent failed pipeline run:\n"
        "1. Call list_runs(status=\"failed\") to find the latest failure\n"
        "2. Call get_run_results(id) to see which tests failed and why\n"
        "3. Group failures by error type and suggest possible root causes\n"
        "4. If a knowledge graph exists, search it for the failing modules\n"
        "5. Summarize findings and recommended fixes"
    )


@mcp.prompt()
def generate_tests(file_path: str = "") -> str:
    """Generate tests for a file or the current changeset.

    Args:
        file_path: Optional path to the file to test. Empty = detect from workspace.
    """
    prompt = "Generate comprehensive tests for the codebase.\n\n"
    if file_path:
        prompt += f"Target file: {file_path}\n"
    prompt += (
        "1. Analyze the code structure (functions, classes, edge cases)\n"
        "2. Write tests covering: happy path, edge cases, error states\n"
        "3. Use the project's existing test framework and patterns\n"
        "4. Verify tests would pass by checking dependencies\n"
        "5. Output the complete test file"
    )
    return prompt


@mcp.prompt()
def review_changes() -> str:
    """Review uncommitted changes for quality, security, and correctness."""
    return (
        "Please review the current changes in this workspace:\n"
        "1. Check for common issues: type errors, missing error handling, security concerns\n"
        "2. Verify tests exist for the changed code\n"
        "3. Check if the knowledge graph shows cross-file impact\n"
        "4. Suggest improvements and highlight risks\n"
        "5. If changes are safe, recommend creating a pipeline run"
    )


@mcp.prompt()
def check_quality() -> str:
    """Run quality gates on the project: tests, coverage, lint."""
    return (
        "Run quality checks on this project:\n"
        "1. Check the last pipeline run status via list_runs()\n"
        "2. If no recent run, trigger one with run_tests() describing the project\n"
        "3. Once complete, fetch results with get_run_results()\n"
        "4. Check coverage via the coverage resource\n"
        "5. Summarize: pass rate, coverage, failed tests, recommendations"
    )


def main():
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport="streamable-http" if transport in ("http", "streamable-http") else "stdio")


if __name__ == "__main__":
    main()
