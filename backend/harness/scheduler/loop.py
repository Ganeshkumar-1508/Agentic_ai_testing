from __future__ import annotations

import asyncio
import logging

from harness.context import manager as scope_manager
from harness.memory.database import Database
from harness.llm import LLMRouter
from harness.agent import Agent
from harness.scheduler import jobs as schedule_util
from harness.scheduler.store import due_jobs, update_job, get_job

logger = logging.getLogger(__name__)

_TICK_INTERVAL = 60


class Scheduler:
    def __init__(self, db: Database, llm: LLMRouter, agent_factory: callable):
        self._db = db
        self._llm = llm
        self._agent_factory = agent_factory
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())
            logger.info("Scheduler started (tick=%ss)", _TICK_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Scheduler stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler tick failed: %s", e)
            await asyncio.sleep(_TICK_INTERVAL)

    async def _tick(self) -> None:
        if self._lock.locked():
            return

        async with self._lock:
            jobs = await due_jobs(self._db)
            if not jobs:
                return

            logger.info("Scheduler tick: %d due job(s)", len(jobs))

            for job in jobs:
                try:
                    await self._execute_job(job)
                except Exception as e:
                    logger.error("Job %s (%s) failed: %s", job["id"], job["name"], e)
                    await update_job(self._db, job["id"], {
                        "last_status": "failed",
                        "state": "scheduled",
                    })

    async def _execute_job(self, job: dict) -> None:
        job_id = job["id"]
        await update_job(self._db, job_id, {"state": "running"})

        try:
            repo_url = job.get("repo_url") or ""
            if repo_url:
                from harness.orchestrator import OrchestratorEngine
                engine = OrchestratorEngine()
                result = await engine.run(
                    run_id=job_id, session_id=f"cron-{job_id}",
                    repo_url=repo_url, goal=job["prompt"],
                    branch=job.get("branch", ""),
                )
                task_count = len(result.get("tasks", []))
                await update_job(self._db, job_id, {"last_status": "ok" if result.get("success") else "failed"})
                logger.info("Job %s: orchestration %s, %d tasks", job_id, "done" if result.get("success") else "failed", task_count)
            else:
                agent = self._agent_factory(allowed_tools=None)
                prompt = job["prompt"]
                if job.get("skill"):
                    from harness.tools.skill_tools import _load_skill
                    skill = _load_skill(job["skill"])
                    if skill:
                        prompt = f"{skill['content']}\n\n{prompt}"

                async with scope_manager.scope(
                    session_id=job_id,
                    labels={"pipeline_step": "scheduler_job"},
                ):
                    result = await agent.run(prompt)
            silent = schedule_util.should_skip_output(result)

            await update_job(self._db, job_id, {
                "last_status": "silent" if silent else "ok",
                "last_run_at": "NOW()",
                "repeat_count": (job.get("repeat_count") or 0) + 1,
            })

            max_repeats = job.get("max_repeats")
            if max_repeats is not None and (job.get("repeat_count") or 0) + 1 >= max_repeats:
                await update_job(self._db, job_id, {"state": "completed"})
                logger.info("Job %s completed (max repeats)", job_id)
            else:
                from harness.scheduler.jobs import parse_schedule
                next_run = parse_schedule(job["schedule_type"], job["schedule_expr"])
                await update_job(self._db, job_id, {
                    "state": "scheduled",
                    "next_run_at": next_run,
                })
                logger.info("Job %s executed, next run: %s", job_id, next_run)

        except Exception as e:
            await update_job(self._db, job_id, {
                "state": "scheduled",
                "last_status": "failed",
            })
            raise
