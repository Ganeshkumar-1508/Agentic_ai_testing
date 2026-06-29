"""PR Auto-Fix Loop — Run tests, fix code, commit, retry.

Flow:
  1. Fetch PR diff + review comments
  2. Run tests via delegate_task
  3. Agent reads error output and decides next action dynamically
  4. If failures found: agent fixes code
  5. Commit + push fixes
  6. Update commit status
  7. Re-trigger tests → loop until all pass or max cycles reached
  8. Send notification on completion
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MAX_CYCLES_DEFAULT = 5
LOGAF_PASS_THRESHOLD = 95.0


def compute_logaf_score(
    total_tests: int, passed: int, failed: int,
    coverage_pct: float = 0, cycle: int = 1, max_cycles: int = MAX_CYCLES_DEFAULT,
) -> float:
    """Compute LOGAF (Level Of Goodness As judged by Automated Feedback) score.

    Score 0-100 where 100 = perfect. Weighted by:
      - Pass rate (60%)
      - Coverage (20%)
      - Cycle efficiency (20%) — earlier cycles score higher
    """
    if total_tests == 0:
        return 0.0

    pass_rate = (passed / total_tests) * 100
    pass_component = min(pass_rate, 100) * 0.6

    cov_component = min(coverage_pct, 100) * 0.2

    cycle_efficiency = max(0, (1 - (cycle - 1) / max_cycles)) * 20

    score = pass_component + cov_component + cycle_efficiency
    return round(min(score, 100), 1)


def extract_fixable_errors(output: str) -> list[dict[str, Any]]:
    """Extract individual fixable errors from test output.

    Returns list of: {file, line, message, type}
    """
    errors = []
    lines = output.split("\n")
    for i, line in enumerate(lines):
        line_lower = line.lower()

        # Python traceback: File "...", line X, in Y
        if 'file "' in line_lower and "line" in line_lower:
            import re
            m = re.search(r'File "([^"]+)", line (\d+)', line)
            if m:
                msg = lines[i + 1] if i + 1 < len(lines) else ""
                errors.append({"file": m.group(1), "line": int(m.group(2)), "message": msg.strip(), "type": "traceback"})

        # TypeScript/ESLint: line:X col:Y
        if ":" in line and ("error" in line_lower or "warning" in line_lower):
            import re
            m = re.search(r"(\S+\.(?:ts|tsx|js|jsx))\((\d+),\d+\)", line)
            if m:
                errors.append({"file": m.group(1), "line": int(m.group(2)), "message": line.strip(), "type": "lint"})

    return errors


def build_fix_prompt(errors: list[dict[str, Any]], pr_diff: str) -> str:
    """Build a prompt for the agent to fix identified errors."""
    from harness.prompt_builder import load_agent_prompt
    base = load_agent_prompt("code-reviewer")
    error_lines = "\n".join(
        f"  - {e['file']}:{e.get('line', '?')} — {e['message'][:200]}"
        for e in errors[:10]
    )
    return f"{base}\n\n## Input\nPR Diff:\n{pr_diff[:3000]}\n\nIssues to fix:\n{error_lines}\n\nFix all issues. Do NOT add new functionality. Run tests after fixing."


def build_logaf_summary(
    cycles: list[dict[str, Any]], pr_title: str, pr_number: int,
) -> str:
    """Build a human-readable summary of the auto-fix loop execution."""
    lines = [f"## TestAI Auto-Fix Report — PR #{pr_number}: {pr_title}\n"]

    if not cycles:
        lines.append("No auto-fix cycles executed.\n")
        return "\n".join(lines)

    first = cycles[0]
    last = cycles[-1]
    total_cycles = len(cycles)
    passed = last.get("passed", 0)
    total = last.get("total", 0) or 1
    final_logaf = last.get("logaf_score", 0)
    failures_fixed = sum(c.get("failures_fixed", 0) for c in cycles)

    lines.append(f"**Cycles:** {total_cycles} | **Final LOGAF:** {final_logaf}/100 | **Tests:** {passed}/{total} passing")
    lines.append(f"**Failures fixed:** {failures_fixed} | **Status:** {'[PASS] All passing' if final_logaf >= LOGAF_PASS_THRESHOLD else '[FAIL] Some failures remain'}\n")

    lines.append("### Cycle History\n")
    lines.append("| Cycle | Status | LOGAF | Tests Passing | Failures Fixed | Tier |")
    lines.append("|---|---|---|---|---|---|")
    for c in cycles:
        tier = c.get("failure_tier", "—")
        lines.append(f"| {c.get('cycle', '?')} | {c.get('status', '?')} | {c.get('logaf_score', '—')} | {c.get('passed', 0)}/{c.get('total', 0)} | {c.get('failures_fixed', 0)} | {tier} |")

        lines.append("\n---\n")
    if final_logaf >= LOGAF_PASS_THRESHOLD:
        lines.append("[PASS] All checks pass. PR is ready for review.")
    else:
        remaining = last.get("failures_remaining", 0)
        lines.append(f"[FAIL] {remaining} failure(s) remain after {total_cycles} cycle(s). Manual review needed.")

    return "\n".join(lines)
