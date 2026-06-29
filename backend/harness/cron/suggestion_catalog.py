"""Curated catalog of starter cron-job suggestions.

Built-in automations offered to users out of the box. Each entry is a
complete cron job spec — the user accepts it and it's created instantly.
Nothing here auto-schedules; the user always confirms first.

Pattern from Hermes' cron/suggestion_catalog.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SuggestionEntry:
    """A curated starter automation offered as a suggestion."""

    key: str
    title: str
    description: str
    job_spec: dict[str, Any]


CATALOG: list[SuggestionEntry] = [
    SuggestionEntry(
        key="catalog:daily-briefing",
        title="Daily Briefing",
        description="Every morning at 8am: today's date, top priorities from recent runs, and test health summary.",
        job_spec={
            "name": "Daily Briefing",
            "prompt": "Produce a concise daily briefing for the user: today's date, "
            "top priorities from recent context, and any urgent items from recent "
            "pipeline runs.",
            "schedule_type": "cron",
            "schedule_expr": "0 8 * * *",
        },
    ),
    SuggestionEntry(
        key="catalog:weekly-review",
        title="Weekly Review",
        description="Every Friday at 6pm: a recap of the week's pipeline runs, pass/fail trends, and open items.",
        job_spec={
            "name": "Weekly Review",
            "prompt": "Review the past week's pipeline runs. Summarize pass/fail rates, "
            "flaky tests, any regressions, and items still in progress.",
            "schedule_type": "cron",
            "schedule_expr": "0 18 * * 5",
        },
    ),
    SuggestionEntry(
        key="catalog:test-health",
        title="Test Health Monitor",
        description="Every 4 hours: check pipeline health and alert if failure rate exceeds 20%.",
        job_spec={
            "name": "Test Health Monitor",
            "prompt": "Review recent pipeline runs. If the failure rate exceeds 20%, "
            "list the failed runs and suggest investigation. Otherwise, respond with [SILENT].",
            "schedule_type": "cron",
            "schedule_expr": "0 */4 * * *",
        },
    ),
]


def get_suggestion(key: str) -> SuggestionEntry | None:
    for s in CATALOG:
        if s.key == key:
            return s
    return None


def get_unsuggested(
    existing_job_names: list[str],
) -> list[dict[str, Any]]:
    """Return catalog entries that don't match existing cron jobs (by name)."""
    existing_lower = [n.lower() for n in existing_job_names]
    return [
        {
            "key": s.key,
            "title": s.title,
            "description": s.description,
            "job_spec": dict(s.job_spec),
        }
        for s in CATALOG
        if s.job_spec.get("name", "").lower() not in existing_lower
    ]
