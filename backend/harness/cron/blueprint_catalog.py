"""Automation Blueprints — pre-built cron job templates with typed slots.

A blueprint is a parameterized automation template. Users fill in slots
(time, channel, keywords) via a UI form and it creates a cron job — no
cron syntax required.

Pattern from Hermes' cron/blueprint_catalog.py:
  - Blueprint = parameterized cron job template with typed slots
  - Slot types: time, enum, text, weekdays
  - fill_blueprint() -> cron job config dict
  - blueprint_form_schema() -> JSON schema for UI form rendering
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Slot types ───────────────────────────────────────────────────────

SLOT_TYPES = frozenset({"time", "enum", "text", "weekdays"})


WEEKDAY_PRESETS: dict[str, str] = {
    "everyday": "*",
    "weekdays": "1-5",
    "weekends": "0,6",
}

WEEKDAY_NAMES: dict[str, int] = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}


class BlueprintFillError(ValueError):
    """Raised when supplied slot values fail validation."""


@dataclass(frozen=True)
class BlueprintSlot:
    """A single fillable field on a blueprint."""

    name: str
    type: str  # time | enum | text | weekdays
    label: str
    default: Any = None
    options: tuple = ()
    optional: bool = False
    help: str = ""
    strict: bool = True


@dataclass(frozen=True)
class AutomationBlueprint:
    """A parameterized automation blueprint."""

    key: str
    title: str
    description: str
    category: str
    schedule_template: str
    prompt_template: str
    slots: list[BlueprintSlot] = field(default_factory=list)
    tags: tuple = ()
    skills: tuple = ()


# ── Built-in catalog ──────────────────────────────────────────────────

_TIME = lambda default="08:00": BlueprintSlot(
    name="time", type="time", label="What time?", default=default,
    help="24h local time, e.g. 08:00",
)

CATALOG: list[AutomationBlueprint] = [
    AutomationBlueprint(
        key="morning-brief",
        title="Morning Briefing",
        description="A short daily briefing: today's date, top priorities, and anything urgent.",
        category="Daily",
        schedule_template="{minute} {hour} * * *",
        prompt_template="Produce a concise morning briefing: today's date, "
        "top priorities from recent context, and any urgent items.",
        slots=[_TIME("08:00")],
        tags=("daily", "briefing"),
    ),
    AutomationBlueprint(
        key="weekly-review",
        title="Weekly Review",
        description="A weekly recap: what got done, what's still open, and what's coming up.",
        category="Weekly",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template="Produce a weekly review: what was accomplished this week, "
        "still-open items, and next week's focus areas.",
        slots=[
            _TIME("18:00"),
            BlueprintSlot(
                name="day", type="enum", label="Which day?",
                default="friday", options=("sunday", "monday", "friday", "saturday"),
            ),
        ],
        tags=("weekly", "review"),
    ),
    AutomationBlueprint(
        key="test-status",
        title="Test Status Report",
        description="A periodic report of recent pipeline run results and test health.",
        category="Engineering",
        schedule_template="{minute} {hour} * * 1-5",
        prompt_template="Review recent pipeline runs and test results. "
        "Summarize pass/fail rates, flaky tests, and any regressions since the last report.",
        slots=[_TIME("09:00")],
        tags=("testing", "pipeline"),
    ),
    AutomationBlueprint(
        key="cost-report",
        title="Weekly Cost Report",
        description="A weekly breakdown of LLM spend by model and session.",
        category="Ops",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template="Produce a weekly cost report: total LLM spend, cost by model, "
        "top 5 most expensive sessions, cost trend vs last week, and any budget warnings.",
        slots=[
            _TIME("09:00"),
            BlueprintSlot(
                name="day", type="enum", label="Which day?",
                default="monday", options=("monday", "friday"),
            ),
        ],
        tags=("cost", "ops"),
    ),
    AutomationBlueprint(
        key="security-scan",
        title="Daily Security Advisory Scan",
        description="Check for new security advisories in project dependencies.",
        category="Ops",
        schedule_template="{minute} {hour} * * *",
        prompt_template="Run osv_check on all project dependencies. "
        "Report any new critical or high-severity advisories. "
        "If none found, report that the dependency tree is clean.",
        slots=[_TIME("07:00")],
        tags=("security", "daily"),
    ),
    AutomationBlueprint(
        key="health-check",
        title="Infrastructure Health Check",
        description="Check system health: disk usage, running services, recent errors.",
        category="Ops",
        schedule_template="{minute} {hour} * * *",
        prompt_template="Check system health: disk usage on /workspace, "
        "running services status, recent error logs, and any performance anomalies. "
        "Flag anything that needs attention.",
        slots=[_TIME("06:00")],
        tags=("ops", "health"),
    ),
    AutomationBlueprint(
        key="dependency-update",
        title="Dependency Update Check",
        description="Check for outdated or vulnerable dependencies across all projects.",
        category="Engineering",
        schedule_template="0 10 * * 1",
        prompt_template="Scan project dependencies for available updates. "
        "Check for: outdated major/minor versions, security patches, "
        "and deprecation notices. Prioritize security updates.",
        slots=[],
        tags=("engineering", "deps"),
    ),
]


def get_blueprint(key: str) -> AutomationBlueprint | None:
    for bp in CATALOG:
        if bp.key == key:
            return bp
    return None


def blueprint_form_schema(bp: AutomationBlueprint) -> dict[str, Any]:
    """Generate a JSON form schema for the blueprint's slots."""
    properties = {}
    required = []
    for slot in bp.slots:
        field: dict[str, Any] = {
            "type": slot.type,
            "title": slot.label,
            "default": slot.default,
        }
        if slot.help:
            field["description"] = slot.help
        if slot.type == "enum":
            field["enum"] = list(slot.options)
        if not slot.optional:
            required.append(slot.name)
        properties[slot.name] = field

    return {
        "title": bp.title,
        "description": bp.description,
        "type": "object",
        "properties": properties,
        "required": required,
    }


def fill_blueprint(bp: AutomationBlueprint, values: dict[str, Any]) -> dict[str, Any]:
    """Validate slot values and produce a cron job config dict.

    Returns a dict ready for cron_jobs table:
      {name, prompt, schedule_type, schedule_expr, ...}
    """
    resolved: dict[str, Any] = {}

    for slot in bp.slots:
        val = values.get(slot.name, slot.default)
        if val is None and not slot.optional:
            raise BlueprintFillError(f"'{slot.name}' is required")

        if slot.type == "enum" and slot.strict and val not in slot.options:
            raise BlueprintFillError(
                f"'{val}' is not a valid option for '{slot.name}'. "
                f"Options: {', '.join(slot.options)}"
            )
        resolved[slot.name] = val

    # Resolve schedule template
    schedule = bp.schedule_template
    # Time slot -> minute + hour
    if "time" in resolved:
        try:
            hour_str, min_str = resolved["time"].strip().split(":")
            resolved["hour"] = hour_str.zfill(2)
            resolved["minute"] = min_str.zfill(2)
        except (ValueError, AttributeError):
            raise BlueprintFillError(f"Invalid time format: {resolved['time']}. Use HH:MM")

    # Weekday slot -> dow
    if "day" in resolved:
        day = resolved["day"].strip().lower()
        if day in WEEKDAY_NAMES:
            resolved["dow"] = str(WEEKDAY_NAMES[day])
        else:
            resolved["dow"] = day  # pass through raw number

    # Fill placeholders
    try:
        schedule_expr = schedule.format(**resolved)
    except KeyError as e:
        raise BlueprintFillError(f"Missing slot value for {e}")

    # Resolve prompt template
    prompt = bp.prompt_template.format(**resolved)

    # Determine schedule_type
    if bp.category.lower() == "daily" or "hour" in schedule:
        schedule_type = "cron"
    else:
        schedule_type = "cron"

    # Calculate next run
    from harness.scheduler.jobs import parse_schedule
    next_run = parse_schedule(schedule_type, schedule_expr)

    return {
        "name": bp.title,
        "prompt": prompt,
        "schedule_type": schedule_type,
        "schedule_expr": schedule_expr,
        "next_run_at": next_run.isoformat() if next_run else None,
        "skills": list(bp.skills),
    }
