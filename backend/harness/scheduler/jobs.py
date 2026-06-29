from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from croniter import croniter
except ImportError:
    croniter = None


def parse_schedule(schedule_type: str, schedule_expr: str) -> datetime | None:
    now = datetime.now(timezone.utc)

    if schedule_type == "delay":
        seconds = _parse_duration(schedule_expr)
        return now + timedelta(seconds=seconds)

    if schedule_type == "interval":
        seconds = _parse_duration(schedule_expr)
        return now + timedelta(seconds=seconds)

    if schedule_type == "cron":
        if not croniter:
            return now + timedelta(hours=1)
        cron = croniter(schedule_expr, now)
        return cron.get_next(datetime)

    if schedule_type == "timestamp":
        try:
            return datetime.fromisoformat(schedule_expr).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    return None


def _parse_duration(expr: str) -> int:
    expr = expr.strip().lower()
    total = 0
    for match in re.finditer(r"(\d+)\s*(s|m|h|d|sec|min|hr|day|seconds?|minutes?|hours?|days?)", expr):
        val = int(match.group(1))
        unit = match.group(2)[0]
        if unit == "s":
            total += val
        elif unit == "m":
            total += val * 60
        elif unit == "h":
            total += val * 3600
        elif unit == "d":
            total += val * 86400
    return total if total > 0 else 3600


def should_skip_output(output: str) -> bool:
    return "[SILENT]" in output
