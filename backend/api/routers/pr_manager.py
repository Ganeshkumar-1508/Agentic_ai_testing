from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prs", tags=["prs"])


@router.get("")
async def list_prs(request: Request):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT * FROM pr_tracker ORDER BY "
        "CASE priority::text WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END, updated_at DESC",
    )
    return {"prs": [dict(r) for r in rows]}


@router.get("/{pr_id}")
async def get_pr(request: Request, pr_id: str):
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM pr_tracker WHERE id = $1", pr_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "PR not found"})
    runs = await db.fetch(
        "SELECT * FROM pr_test_runs WHERE pr_id = $1 ORDER BY created_at DESC LIMIT 20",
        pr_id,
    )
    return {"pr": dict(row), "runs": [dict(r) for r in runs]}


@router.post("/sync")
async def sync_prs(request: Request):
    """Fetch open PRs from connected repos and upsert them."""
    db = get_db(request)
    import json
    try:
        raw = await request.body()
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {e}. Raw: {raw[:200]}"})
    raw_url = body.get("repo_url", "")
    provider = body.get("provider", "github")
    token = body.get("token", "")
    clone_repo = body.get("clone_repo", False)

    if not raw_url:
        return JSONResponse(status_code=400, content={"error": "repo_url required"})

    from harness.ci.git_providers import get_provider, get_provider_from_url
    detected = get_provider_from_url(raw_url)
    if detected:
        provider, repo_url, _ = detected
    else:
        import re
        repo_url = re.sub(r"https?://[^/]+/", "", raw_url).rstrip("/").rstrip(".git")
    gh = get_provider(provider)

    try:
        logger.info("Fetching PRs for %s with provider %s (token length: %d)", repo_url, provider, len(token))
        prs = await gh.list_open_prs(repo_url, token)
        logger.info("Found %d open PRs", len(prs))
    except httpx.HTTPStatusError as e:
        detail = f"GitHub API returned {e.response.status_code} for {repo_url}. Check that the repo exists and your token has access."
        logger.error("Sync failed: %s", detail)
        return JSONResponse(status_code=502, content={"error": detail})
    except Exception as e:
        logger.error("Sync failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": f"Failed to fetch PRs: {e}"})

    count = 0
    for pr_data in prs:
        risk = (pr_data.get("changed_files", 0) * 3 + pr_data.get("additions", 0) * 0.5 + pr_data.get("deletions", 0) * 0.3)
        risk = min(round(risk, 1), 100)
        await db.execute(
            """INSERT INTO pr_tracker (repo_url, repo_provider, pr_number, title, description,
               head_sha, base_sha, source_branch, target_branch, author, status, files_changed,
               additions, deletions, labels, reviewers, milestone, risk_score)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'open',
               $11, $12, $13, $14, $15, $16, $17)
               ON CONFLICT (repo_url, pr_number) DO UPDATE SET
               title = EXCLUDED.title, head_sha = EXCLUDED.head_sha,
               source_branch = EXCLUDED.source_branch, target_branch = EXCLUDED.target_branch,
               files_changed = EXCLUDED.files_changed, risk_score = EXCLUDED.risk_score,
               labels = EXCLUDED.labels, updated_at = NOW()""",
            repo_url, provider, pr_data["number"], pr_data["title"],
            pr_data.get("body", ""), pr_data.get("head_sha", ""),
            pr_data.get("base_sha", ""), pr_data.get("source_branch", ""),
            pr_data.get("target_branch", ""), pr_data.get("user", ""),
            pr_data.get("changed_files", 0), pr_data.get("additions", 0),
            pr_data.get("deletions", 0), pr_data.get("labels", []),
            pr_data.get("reviewers", []), pr_data.get("milestone", ""),
            risk,
        )
        count += 1

    return {"status": "ok", "synced": count, "repo": repo_url}


@router.get("/{pr_id}/impact")
async def pr_impact_analysis(request: Request, pr_id: str):
    """Run Test Impact Analysis on a PR's repo."""
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM pr_tracker WHERE id = $1", pr_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "PR not found"})
    repo_path = row.get("repo_url", "")
    from harness.test_impact import compute_impact_summary, get_changed_files, build_dependency_map, select_tests
    result = compute_impact_summary(repo_path)
    return {"pr_id": pr_id, **result}


@router.patch("/{pr_id}")
async def update_pr(request: Request, pr_id: str):
    db = get_db(request)
    body = await request.json()
    fields = []
    vals: list[Any] = []
    i = 1
    for key in ("priority", "agent_config", "status"):
        if key in body:
            val = body[key]
            if isinstance(val, dict):
                val = json.dumps(val)
            fields.append(f"{key} = ${i}")
            vals.append(val)
            i += 1
    if not fields:
        return JSONResponse(status_code=400, content={"error": "no fields"})
    fields.append("updated_at = NOW()")
    vals.append(pr_id)
    await db.execute(f"UPDATE pr_tracker SET {', '.join(fields)} WHERE id = ${i}", *vals)
    return {"status": "ok"}


@router.post("/{pr_id}/run")
async def run_pr_tests(request: Request, pr_id: str):
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM pr_tracker WHERE id = $1", pr_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "PR not found"})

    body = await request.json()
    agent_config = body.get("agent_config", row["agent_config"] or "{}")
    if isinstance(agent_config, str):
        agent_config = json.loads(agent_config)

    run_id = None
    import uuid
    run_id = str(uuid.uuid4())

    await db.execute(
        "INSERT INTO pr_test_runs (id, pr_id, status, triggered_by) VALUES ($1, $2, 'running', $3)",
        run_id, pr_id, body.get("triggered_by", "manual"),
    )

    import asyncio
    asyncio.create_task(
        _execute_pr_pipeline(db, pr_id, run_id, row, agent_config),
        name=f"pr-run-{pr_id[:8]}",
    )

    # Generate test cases from PR title in background
    try:
        llm = getattr(request.app.state, "llm", None)
        if llm and row.get("title", "").strip():
            asyncio.create_task(
                _generate_test_cases_for_pr(db, llm, row["title"], row["id"], run_id),
                name=f"pr-gen-{pr_id[:8]}",
            )
    except Exception:
        pass

    return {"status": "started", "run_id": run_id}


@router.patch("/{pr_id}/notifications")
async def update_pr_notifications(request: Request, pr_id: str):
    db = get_db(request)
    body = await request.json()
    channels = body.get("channels", [])
    await db.execute(
        "UPDATE pr_tracker SET notification_channels = $1, updated_at = NOW() WHERE id = $2",
        json.dumps(channels), pr_id,
    )
    return {"status": "ok", "channels": channels}


@router.post("/{pr_id}/auto-fix")
async def auto_fix_pr(request: Request, pr_id: str):
    """Start an auto-fix loop: run tests → classify → fix → commit → retry."""
    db = get_db(request)
    row = await db.fetchrow("SELECT * FROM pr_tracker WHERE id = $1", pr_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "PR not found"})

    body = await request.json()
    max_cycles = body.get("max_cycles", row.get("auto_fix_max_cycles", 5))

    await db.execute("UPDATE pr_tracker SET auto_fix_enabled = true, auto_fix_max_cycles = $1 WHERE id = $2", max_cycles, pr_id)

    import asyncio
    asyncio.create_task(
        _run_auto_fix_loop(db, pr_id, row, max_cycles=max_cycles),
        name=f"autofix-{pr_id[:8]}",
    )

    return {"status": "auto_fix_started", "pr_id": pr_id, "max_cycles": max_cycles}


async def _run_auto_fix_loop(db, pr_id: str, pr_row: dict, max_cycles: int = 5):
    """Run the auto-fix loop: test → classify → fix → commit → retry."""
    from harness.pr_auto_fix import compute_logaf_score, extract_fixable_errors, build_fix_prompt, build_logaf_summary
    from harness.tools.registry import registry
    from harness.ci.git_providers import get_provider

    token = None  # Would come from settings store
    repo_url = pr_row["repo_url"]
    pr_number = pr_row["pr_number"]
    provider_name = pr_row.get("repo_provider", "github")
    all_cycles: list[dict[str, Any]] = []

    try:
        provider = get_provider(provider_name)
    except Exception as e:
        logger.error("Auto-fix: unknown provider %s: %s", provider_name, e)
        return

    for cycle in range(1, max_cycles + 1):
        logger.info("Auto-fix cycle %d/%d for PR #%d", cycle, max_cycles, pr_number)

        import uuid
        run_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO pr_test_runs (id, pr_id, status, triggered_by, cycle_number) VALUES ($1, $2, 'running', 'auto_fix', $3)",
            run_id, pr_id, cycle,
        )

        dt = registry.get("delegate_task")
        if not dt:
            logger.error("Auto-fix: delegate_task not available")
            break
        dt._session_id = run_id

        goal = f"Test PR #{pr_number} for {repo_url}\n\n{pr_row.get('title', '')}"
        try:
            result = await dt.run(goal=goal, toolsets=["read", "write", "analyze", "delegate"], role="orchestrator")
        except Exception as e:
            logger.error("Auto-fix cycle %d: delegate_task failed: %s", cycle, e)
            await db.execute(
                "UPDATE pr_test_runs SET status = 'error', cycle_number = $1 WHERE id = $2",
                cycle, run_id,
            )
            break

        output = result.output or ""
        error = result.error or ""
        success = result.success

        # Agent reads error output and decides next action dynamically
        fixable_errors = extract_fixable_errors(output) if not success else []
        failures_fixed = 0
        failures_remaining = len(fixable_errors)

        # Attempt to fix if there are fixable errors
        if not success and fixable_errors:
            try:
                pr_diff = await provider.get_pr_diff(repo_url, pr_number, token or "")
                fix_prompt = build_fix_prompt(fixable_errors, pr_diff)
                fix_result = await dt.run(goal=fix_prompt, toolsets=["read", "write"], role="leaf")

                if fix_result.success:
                    await provider.post_pr_comment(repo_url, pr_number, token or "",
                        f"TestAI auto-fix cycle {cycle}: attempting to fix {len(fixable_errors)} issue(s).")
                    failures_fixed = len(fixable_errors)
                    failures_remaining = 0
            except Exception as e:
                logger.warning("Auto-fix cycle %d: fix attempt failed: %s", cycle, e)

        # Compute LOGAF score
        logaf = compute_logaf_score(
            total_tests=1, passed=1 if success else 0, failed=0 if success else 1,
            cycle=cycle, max_cycles=max_cycles,
        )

        cycle_data = {
            "cycle": cycle, "status": "passed" if success else "failed",
            "logaf_score": logaf, "passed": 1 if success else 0, "total": 1,
            "failures_fixed": failures_fixed, "failures_remaining": failures_remaining,
            "failure_tier": tier,
        }
        all_cycles.append(cycle_data)

        await db.execute(
            """UPDATE pr_test_runs SET status = $1, failure_tier = $2, logaf_score = $3,
               failures_fixed = $4, failures_remaining = $5, completed_at = NOW()
               WHERE id = $6""",
            "completed" if success else "failed", tier, logaf,
            failures_fixed, failures_remaining, run_id,
        )

        await db.execute(
            "UPDATE pr_tracker SET last_test_status = $1, last_test_run_at = NOW(), last_logaf_score = $2, total_fix_cycles = $3, updated_at = NOW() WHERE id = $4",
            "passed" if success else "failed", logaf, cycle, pr_id,
        )

        # Update commit status
        try:
            status_state = "success" if success else "pending" if cycle < max_cycles else "failure"
            status_desc = f"TestAI auto-fix: cycle {cycle}/{max_cycles}" if not success else "TestAI: all checks passed"
            await provider.set_pr_status(repo_url, pr_number, token or "", status_state, status_desc)
        except Exception as e:
            logger.warning("Auto-fix: commit status update failed: %s", e)

        if success:
            logger.info("Auto-fix: all tests passed after %d cycle(s)", cycle)
            break

    # Summary
    summary = build_logaf_summary(all_cycles, pr_row.get("title", ""), pr_number)
    try:
        await provider.post_pr_comment(repo_url, pr_number, token or "", summary)
    except Exception as e:
        logger.warning("Auto-fix: failed to post summary: %s", e)

    await db.execute(
        "UPDATE pr_tracker SET auto_fix_enabled = false, last_notification_sent_at = NOW() WHERE id = $1",
        pr_id,
    )

    # Send notifications via delivery router
    try:
        channels_raw = pr_row.get("notification_channels", "[]")
        if isinstance(channels_raw, str):
            channels_raw = json.loads(channels_raw)
        if channels_raw:
            from harness.delivery.router import DeliveryRouter
            from harness.delivery.adapters.base import DeliveryTarget
            router = DeliveryRouter()
            targets = [DeliveryTarget.parse(c) for c in channels_raw]
            await router.deliver(summary, targets, job_id=f"pr-{pr_number}", job_name=f"PR #{pr_number} Auto-Fix Report")
    except Exception as e:
        logger.warning("Auto-fix notification failed: %s", e)

    logger.info("Auto-fix loop completed for PR #%s (%d cycles)", pr_number, len(all_cycles))


async def _execute_pr_pipeline(db, pr_id: str, run_id: str, pr_row: dict, agent_config: dict):
    from harness.pr_integration import build_pr_comment
    from harness.tools.registry import registry

    try:
        dt = registry.get("delegate_task")
        if not dt:
            raise RuntimeError("delegate_task tool not available")
        dt._session_id = f"pr-{pr_row.get('pr_number', 'unknown')}"

        goal = (
            f"Test PR #{pr_row['pr_number']} for {pr_row['repo_url']}\n\n"
            f"## PR Context\n"
            f"Title: {pr_row.get('title', '')}\n"
            f"Description: {pr_row.get('description', '')}\n"
            f"Branch: {pr_row.get('source_branch', '')} -> {pr_row.get('target_branch', 'main')}\n\n"
            f"Files changed: {pr_row.get('files_changed', 0)}, "
            f"Additions: +{pr_row.get('additions', 0)}, "
            f"Deletions: -{pr_row.get('deletions', 0)}\n\n"
            f"## Orchestration Plan\n\n"
            f"### Phase 1: Baseline\n"
            f"1. Clone the PR branch, detect tech stack\n"
            f"2. Read the PR diff to understand what changed\n"
            f"3. Run existing tests to establish a baseline pass/fail\n"
            f"4. Output: stack detected, baseline results, changed files list\n\n"
            f"### Phase 2: Generate Tests\n"
            f"Spawn focused subagents via delegate_task per concern:\n"
            f"- Subagent A: Tests covering new functionality added by the PR (happy path)\n"
            f"- Subagent B: Edge cases and boundary conditions for the changed code\n"
            f"- Subagent C: Regression tests — verify existing behavior is not broken\n"
            f"- Subagent D: Security review of the changed code (injection, auth, data exposure)\n"
            f"Each subagent receives:\n"
            f"  - The PR diff and affected files\n"
            f"  - Project conventions and test framework\n"
            f"  - Build and test commands\n"
            f"  - Acceptance criteria\n\n"
            f"### Phase 3: Execute & Classify\n"
            f"1. Run all tests together\n"
            f"2. Classify each failure by tier:\n"
            f"   - F1: Pre-existing failure (was failing before PR)\n"
            f"   - F2: Regression (this PR broke something that worked)\n"
            f"   - F3: New bug found by new tests\n"
            f"   - F4: Flaky (intermittent, not reproducible)\n"
            f"3. Diagnose and fix failures tier F2-F3\n"
            f"4. Rerun until all pass or max cycles reached\n\n"
            f"### Phase 4: Report\n"
            f"Return structured output:\n"
            f"- Total tests, passed, failed (by tier), skipped\n"
            f"- LOGAF score: likelihood the PR is good\n"
            f"- List of generated test files\n"
            f"- Any flaky tests detected\n\n"
            f"## Skills\n"
            f"Scan the Available Skills section above. Load testing skills via `skill_view(name)` "
            f"(test-generation, testing-qa, api-testing, security-testing, flaky-debug) "
            f"that match the detected stack and PR changes. Follow their instructions.\n\n"
            f"## Quality Standards\n"
            f"- Deterministic, isolated tests — no shared state or network dependencies\n"
            f"- Assert on observable behavior, not implementation internals\n"
            f"- One assertion concept per test (ARRANGE-ACT-ASSERT pattern)\n"
            f"- Include both positive and negative test cases\n"
            f"- Cover changed code paths specifically\n"
            f"- Use the project's existing conventions and test framework\n"
            f"- Diagnose → fix → rerun on failure — do not leave failures unaddressed"
        )
        result = await dt.run(goal=goal, toolsets=["read", "write", "analyze", "delegate"], role="orchestrator")

        test_summary = {"total": 0, "passed": 0, "failed": 0}
        coverage = None

        await db.execute(
            "UPDATE pr_test_runs SET status = $1, test_summary = $2, completed_at = NOW() WHERE id = $3",
            "completed" if result.success else "failed",
            json.dumps(test_summary), run_id,
        )

        await db.execute(
            "UPDATE pr_tracker SET last_test_status = $1, last_test_run_at = NOW(), updated_at = NOW() WHERE id = $2",
            "passed" if result.success else "failed", pr_id,
        )

        # Compute risk score after test run
        try:
            from harness.risk_scoring import update_pr_risk_score
            await update_pr_risk_score(db, pr_id)
        except Exception:
            pass

        comment = build_pr_comment(test_summary=test_summary, coverage=coverage)
        logger.info("PR %s test run %s completed", pr_id, run_id)

    except Exception as e:
        logger.error("PR test run %s failed: %s", run_id, e)
        await db.execute(
            "UPDATE pr_test_runs SET status = 'error', completed_at = NOW() WHERE id = $1",
            run_id,
        )

    # Scan for flaky tests after PR run
    try:
        from harness.flaky_auto_quarantine import scan_and_quarantine
        await scan_and_quarantine(db)
    except Exception:
        pass


async def _generate_test_cases_for_pr(db: any, llm: any, title: str, pr_id: str, run_id: str) -> None:
    """Generate test cases from a PR title and save them."""
    try:
        from harness.test_generator import generate_test_cases, save_test_cases
        test_cases = await generate_test_cases(title, llm, count=5)
        if test_cases:
            saved = await save_test_cases(db, "default-project", f"pr-{pr_id}", test_cases)
            logger.info("Generated %d test cases from PR '%s' (%d saved)", len(test_cases), title[:40], saved)
    except Exception as e:
        logger.warning("PR test case generation failed: %s", e)
