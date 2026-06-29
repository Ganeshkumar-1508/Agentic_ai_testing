from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from harness.scheduler import jobs as schedule_util
from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry


class CronJobTool(BaseTool):
    name = "cronjob"
    db: Any = None
    description = (
        "Manage scheduled tasks. Create, list, pause, resume, run, or remove "
        "cron jobs. Supports delay (30m), interval (every 2h), cron expression "
        "(0 9 * * *), and ISO timestamp schedules."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "pause", "resume", "run", "remove"],
                        "description": "Action to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Job name (for create, pause, resume, run, remove)",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "Job ID (for pause, resume, run, remove)",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Agent prompt to run (for create)",
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Schedule: '30m', 'every 2h', '0 9 * * *', ISO timestamp (for create)",
                    },
                    "skill": {
                        "type": "string",
                        "description": "Skill to load before running (for create)",
                    },
                    "max_repeats": {
                        "type": "integer",
                        "description": "Max executions, null = infinite (for create)",
                    },
                },
                "required": ["action"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        job_id = kwargs.get("job_id", "")
        prompt = kwargs.get("prompt", "")
        schedule = kwargs.get("schedule", "")
        skill = kwargs.get("skill", "")
        max_repeats = kwargs.get("max_repeats")

        if not self.db:
            return ToolResult(success=False, output="Database not configured", error="no_db")

        from harness.scheduler.store import create_job, list_jobs, get_job, update_job, delete_job

        if action == "create":
            if not name or not prompt or not schedule:
                return ToolResult(
                    success=False,
                    output="name, prompt, and schedule required",
                    error="missing_fields",
                )
            schedule_type, schedule_expr = self._parse_schedule(schedule)
            if not schedule_type:
                return ToolResult(
                    success=False,
                    output=f"Invalid schedule: {schedule}. Use '30m', 'every 2h', '0 9 * * *', or ISO timestamp.",
                    error="bad_schedule",
                )
            next_run = schedule_util.parse_schedule(schedule_type, schedule_expr)
            job = await create_job(self.db, {
                "name": name,
                "prompt": prompt,
                "schedule_type": schedule_type,
                "schedule_expr": schedule_expr,
                "skill": skill or None,
                "max_repeats": max_repeats,
                "next_run_at": next_run,
            })
            return ToolResult(
                success=True,
                output=f"Job '{name}' created (id={job['id']}). Next run: {next_run}",
                data={"job": job},
            )

        if action == "list":
            jobs = await list_jobs(self.db)
            if not jobs:
                return ToolResult(success=True, output="No cron jobs configured.")
            lines = ["## Cron Jobs\n"]
            for j in jobs:
                status = "running" if j.get("state") == "running" else ("paused" if not j.get("enabled") else j.get("state", "unknown"))
                lines.append(f"- **{j['name']}** ({j['schedule_expr']}) [{status}]")
            return ToolResult(success=True, output="\n".join(lines), data={"jobs": jobs})

        resolved_id = job_id or ""
        if not resolved_id and name:
            jobs = await list_jobs(self.db)
            for j in jobs:
                if j["name"] == name:
                    resolved_id = j["id"]
                    break

        if not resolved_id:
            return ToolResult(success=False, output="Job not found. Provide job_id or name.", error="not_found")

        if action == "pause":
            await update_job(self.db, resolved_id, {"enabled": False})
            return ToolResult(success=True, output=f"Job '{resolved_id}' paused")

        if action == "resume":
            job = await get_job(self.db, resolved_id)
            if not job:
                return ToolResult(success=False, output="Job not found", error="not_found")
            next_run = schedule_util.parse_schedule(job["schedule_type"], job["schedule_expr"])
            await update_job(self.db, resolved_id, {"enabled": True, "state": "scheduled", "next_run_at": next_run})
            return ToolResult(success=True, output=f"Job '{resolved_id}' resumed. Next run: {next_run}")

        if action == "run":
            job = await get_job(self.db, resolved_id)
            if not job:
                return ToolResult(success=False, output="Job not found", error="not_found")
            return ToolResult(
                success=True,
                output=f"Job '{resolved_id}' will run on next scheduler tick.",
                data={"job_id": resolved_id},
            )

        if action == "remove":
            await delete_job(self.db, resolved_id)
            return ToolResult(success=True, output=f"Job '{resolved_id}' removed")

        return ToolResult(success=False, output=f"Unknown action: {action}", error="bad_action")

    def _parse_schedule(self, s: str) -> tuple[str, str]:
        s = s.strip()
        lowered = s.lower()
        if lowered.startswith("every "):
            return ("interval", lowered[6:])
        if re.match(r"^\d+[smhd]", lowered):
            return ("delay", lowered)
        if re.match(r"^\d{4}-\d{2}", s) and ("T" in s or " " in s):
            return ("timestamp", s)
        if re.match(r"^(\d+|\*)\s+(\d+|\*)\s+(\d+|\*)\s+(\d+|\*)\s+(\d+|\*)$", s):
            return ("cron", s)
        return ("", "")


registry.register(CronJobTool(), toolset="delegate")
