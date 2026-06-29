"""Seed the database with realistic demo data to verify dashboard components."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import os

DSN = os.environ.get("DATABASE_URL", "postgresql://testai:testai@localhost:5432/testai")

TEST_NAMES = [
    "Button renders without crashing",
    "Button onClick handler fires",
    "Button disabled state prevents click",
    "Button shows loading spinner",
    "Input renders with placeholder",
    "Input onChange updates value",
    "Input shows error state",
    "Input handles max length",
    "Modal opens on trigger click",
    "Modal closes on escape key",
    "Modal renders children content",
    "Select dropdown shows options",
    "Select onChange fires with value",
    "Table renders header row",
    "Table sorts columns on click",
    "Table handles empty state",
    "Form validates required fields",
    "Form submits with valid data",
    "Form shows API error message",
    "API returns 200 on GET /users",
    "API returns 404 for missing user",
    "API validates request body",
    "Auth middleware rejects invalid token",
    "Auth middleware allows valid token",
    "WebSocket connects and receives messages",
]


def make_run(status: str, delta_hours: int) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc) - timedelta(hours=delta_hours)
    completed = created + timedelta(minutes=max(1, abs(delta_hours) % 12 + 1))

    if status == "completed":
        passed = 10 + abs(hash(run_id)) % 15
        failed = abs(hash(run_id + "f")) % 4
        skipped = abs(hash(run_id + "s")) % 3
        total = passed + failed + skipped
        duration = 12.4 + total * 2.1 + failed * 8.3
    else:
        passed = 0
        failed = 0
        skipped = 0
        total = 0
        duration = 0

    return {
        "id": run_id,
        "status": status,
        "inputs": json.dumps({"requirements": f"Run test batch {delta_hours}h ago"}),
        "artifacts": json.dumps([]),
        "created_at": created,
        "completed_at": completed if status == "completed" else None,
        "test_count": total,
        "passed_count": passed,
        "failed_count": failed,
        "skipped_count": skipped,
        "duration": round(duration, 1),
    }


async def seed():
    conn = await asyncpg.connect(DSN)
    print("Connected to database.")

    # Clear existing data
    for table in ["pipeline_runs", "test_results", "test_cases", "coverage_reports", "flaky_tests", "trace_events", "sessions"]:
        await conn.execute(f"DELETE FROM {table}")
    print("Cleared existing demo data.")

    # ── Pipeline runs ──────────────────────────────────────────────
    runs = []
    for i in range(24):
        status = "completed" if i < 20 else ("failed" if i < 22 else "running")
        delta = i * 2
        runs.append(make_run(status, delta))
    for i in range(24, 28):
        runs.append(make_run("completed", i * 2))

    for r in runs:
        await conn.execute(
            """INSERT INTO pipeline_runs
               (id, status, inputs, artifacts, created_at, completed_at,
                test_count, passed_count, failed_count, skipped_count, duration)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
            r["id"], r["status"], r["inputs"], r["artifacts"],
            r["created_at"], r["completed_at"],
            r["test_count"], r["passed_count"], r["failed_count"],
            r["skipped_count"], r["duration"],
        )
    print(f"Inserted {len(runs)} pipeline runs.")

    # ── Test results ───────────────────────────────────────────────
    test_rows = 0
    for r in runs:
        if r["status"] != "completed":
            continue
        for name in TEST_NAMES[:6]:
            passed = 1 if abs(hash(r["id"] + name)) % 4 > 0 else 0
            status = "passed" if passed else "failed"
            dur = round(8 + abs(hash(r["id"] + name + "d")) % 40, 1)
            await conn.execute(
                """INSERT INTO test_results (id, run_id, test_name, status, duration_ms, error, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                str(uuid.uuid4()), r["id"], name, status, dur,
                "" if passed else "AssertionError: expected element not found",
                r["created_at"],
            )
            test_rows += 1

            # Also add some results where the test_name comes from pipeline_run id
            id_name = f"Test run {r['id'][:8]}"
            await conn.execute(
                "INSERT INTO test_results (id, run_id, test_name, status, duration_ms, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
                str(uuid.uuid4()), r["id"], id_name, status, round(dur * 0.7, 1), r["created_at"],
            )
            test_rows += 1
    print(f"Inserted {test_rows} test results.")

    # ── Coverage reports ───────────────────────────────────────────
    for i, r in enumerate(runs[:20]):
        if r["status"] != "completed":
            continue
        line_cov = round(30 + abs(hash(r["id"])) % 50, 1)
        branch_cov = round(line_cov - 5 - abs(hash(r["id"] + "b")) % 15, 1)
        await conn.execute(
            """INSERT INTO coverage_reports (id, run_id, language, framework, line_coverage, branch_coverage, total_lines, covered_lines, report_data, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            str(uuid.uuid4()), r["id"], "typescript", "vitest",
            line_cov, branch_cov, 200, int(line_cov * 2), "{}", r["created_at"],
        )
    print("Inserted coverage reports.")

    # ── Flaky tests ────────────────────────────────────────────────
    flaky_names = [
        "Modal opens on trigger click",
        "Select dropdown shows options",
        "WebSocket connects and receives messages",
    ]
    for i, name in enumerate(flaky_names):
        total = 10 - i * 2
        passed = int(total * (0.3 + i * 0.15))
        failed = total - passed
        score = round((min(passed, failed) / max(total, 1)) * 100, 1)
        await conn.execute(
            """INSERT INTO flaky_tests (test_name, run_id, branch, total_runs, pass_count, fail_count, flaky_score, is_quarantined)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            name, runs[0]["id"], "main", total, passed, failed, score, score > 35,
        )
    print("Inserted flaky test entries.")

    # ── Test cases ────────────────────────────────────────────────
    case_names = [
        ("User authentication API", "api", "Verify user login with valid credentials returns JWT token", "passed", "high"),
        ("User registration form", "ui", "Validate registration form with all required fields", "passed", "high"),
        ("Payment webhook handler", "api", "Process incoming Stripe payment events correctly", "passed", "medium"),
        ("Search indexing pipeline", "performance", "Index 10k documents under 5 seconds", "failed", "high"),
        ("Notification dispatcher", "api", "Dispatch email and push notifications for events", "pending", "medium"),
        ("Profile page rendering", "ui", "Render user profile with avatar, bio, and stats", "passed", "low"),
        ("Database migration v2.1", "integration", "Migrate schema from v2.0 to v2.1 without data loss", "passed", "critical"),
        ("Rate limiter middleware", "security", "Enforce 100 req/min per user with proper headers", "passed", "high"),
        ("File upload validator", "security", "Reject files over 10MB and disallowed extensions", "pending", "medium"),
        ("Session management", "api", "Refresh token rotation and session expiry handling", "passed", "high"),
        ("WebSocket reconnection", "performance", "Reconnect within 3 seconds after connection drop", "failed", "medium"),
        ("Cache invalidation strategy", "integration", "Invalidate Redis cache entries on data update", "passed", "medium"),
    ]
    case_code = """import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('Component', () => {
  it('renders without crashing', () => {
    expect(() => render(<Component />)).not.toThrow();
  });

  it('handles user interaction', async () => {
    const handler = vi.fn();
    render(<Component onClick={handler} />);
    await userEvent.click(screen.getByRole('button'));
    expect(handler).toHaveBeenCalledTimes(1);
  });
});"""
    for name, typ, desc, status, priority in case_names:
        await conn.execute(
            """INSERT INTO test_cases (id, project_id, name, description, test_type, status, priority, code, code_language, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            str(uuid.uuid4()), "default-project", name, desc, typ, status, priority,
            case_code, "typescript",
            datetime.now(timezone.utc) - timedelta(hours=abs(hash(name)) % 72),
        )
    print(f"Inserted {len(case_names)} test cases.")

    # ── Sessions ───────────────────────────────────────────────────
    for i, r in enumerate(runs[:10]):
        await conn.execute(
            "INSERT INTO sessions (id, status, prompt, total_tokens, total_cost, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
            r["id"], "completed" if r["status"] == "completed" else "running",
            f"Test session {i + 1}: {TEST_NAMES[i % len(TEST_NAMES)]}",
            1200 + abs(hash(r["id"])) % 5000,
            round(0.02 + abs(hash(r["id"] + "c")) % 100 / 1000, 4),
            r["created_at"],
        )
    print("Inserted sessions.")

    # ── Trace events ───────────────────────────────────────────────
    for r in runs[:10]:
        for typ in ["agent:start", "round:start", "tool:start", "tool:end", "agent:end"]:
            await conn.execute(
                "INSERT INTO trace_events (id, run_id, event_type, event_data, created_at) VALUES ($1,$2,$3,$4,$5)",
                str(uuid.uuid4()), r["id"], typ,
                json.dumps({"event_type": typ, "name": "test_executor", "success": r["status"] == "completed"}),
                r["created_at"],
            )
    print("Inserted trace events.")

    # ── Summary ────────────────────────────────────────────────────
    for tbl in ["pipeline_runs", "test_results", "test_cases", "coverage_reports", "flaky_tests", "trace_events", "sessions"]:
        cnt = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
        print(f"  {tbl}: {cnt}")
    print("\nDemo data seeded. Refresh the app to see real data.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
