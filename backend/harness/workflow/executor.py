"""WorkflowExecutor — runs a WorkflowDefinition by dispatching to existing primitives.

Maps each WorkflowStep to:
  - agent        → delegate_task(goal=step.prompt, role=step.config.role, ...)
  - human_input  → question(question=step.prompt, options=...)
  - router       → evaluate branch_rules against accumulated outputs
  - sub_workflow → recursive WorkflowExecutor.execute()

Supports retry per step (config.max_attempts), error workflow dispatch
(config.error_workflow_key), and execution history persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from harness.workflow.models import (
    ExecutionStatus,
    StepExecutionRecord,
    WorkflowDefinition,
    WorkflowExecutionRecord,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class WorkflowExecutionError(Exception):
    """Raised when a workflow step fails irrecoverably."""


class WorkflowExecutor:
    """Executes steps by dispatching to existing harness primitives."""

    def __init__(self, db: Any = None):
        self._db = db
        self._results: dict[str, Any] = {}
        self._step_records: list[StepExecutionRecord] = []

    async def execute(
        self,
        definition: WorkflowDefinition,
        context: dict[str, Any] | None = None,
        triggered_by: str = "manual",
        retry_of: str = "",
    ) -> dict[str, Any]:
        """Run all steps in dependency order. Persists execution record."""
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        self._results = {}
        self._step_records = []

        steps = list(definition.steps)
        if not steps:
            record = WorkflowExecutionRecord(
                id=execution_id, workflow_key=definition.key,
                status="completed", started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                triggered_by=triggered_by, retry_of=retry_of,
            )
            await self._persist(record)
            return {"status": "completed", "execution_id": execution_id, "steps": {}}

        context = dict(context or {})
        overall_failed = False
        overall_error = ""

        try:
            ordered = self._topological_sort(steps)
            for batch in ordered:
                if len(batch) == 1:
                    step = batch[0]
                    step_start = time.monotonic()
                    try:
                        result = await self._execute_step_with_retry(step, context)
                        self._results[step.id] = result
                        self._step_records.append(StepExecutionRecord(
                            step_id=step.id, label=step.label, type=step.type,
                            status="completed",
                            started_at=datetime.now(timezone.utc).isoformat(),
                            duration_sec=round(time.monotonic() - step_start, 2),
                            output=json.dumps(result)[:500],
                        ))
                    except WorkflowExecutionError as exc:
                        self._step_records.append(StepExecutionRecord(
                            step_id=step.id, label=step.label, type=step.type,
                            status="failed",
                            started_at=datetime.now(timezone.utc).isoformat(),
                            duration_sec=round(time.monotonic() - step_start, 2),
                            error=str(exc),
                        ))
                        overall_failed = True
                        overall_error = str(exc)
                        break
                else:
                    tasks = []
                    for s in batch:
                        step_start = time.monotonic()
                        tasks.append(self._execute_step_with_retry(s, context))
                    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                    for step, outcome in zip(batch, outcomes):
                        if isinstance(outcome, Exception):
                            self._step_records.append(StepExecutionRecord(
                                step_id=step.id, label=step.label, type=step.type,
                                status="failed",
                                started_at=datetime.now(timezone.utc).isoformat(),
                                duration_sec=0, error=str(outcome),
                            ))
                            overall_failed = True
                            overall_error = str(outcome)
                            break
                        self._results[step.id] = outcome
                        self._step_records.append(StepExecutionRecord(
                            step_id=step.id, label=step.label, type=step.type,
                            status="completed",
                            started_at=datetime.now(timezone.utc).isoformat(),
                            duration_sec=round(time.monotonic() - step_start, 2),
                            output=json.dumps(outcome)[:500],
                        ))
                    if overall_failed:
                        break
        except WorkflowExecutionError as exc:
            overall_failed = True
            overall_error = str(exc)

        completed_at = datetime.now(timezone.utc).isoformat()
        total_duration = round(
            (datetime.fromisoformat(completed_at).timestamp()
             - datetime.fromisoformat(started_at).timestamp()), 2
        )

        status: ExecutionStatus = "failed" if overall_failed else "completed"
        record = WorkflowExecutionRecord(
            id=execution_id, workflow_key=definition.key,
            status=status, started_at=started_at,
            completed_at=completed_at, duration_sec=total_duration,
            steps=self._step_records, error=overall_error,
            triggered_by=triggered_by, retry_of=retry_of,
        )
        await self._persist(record)

        if overall_failed:
            await self._dispatch_error_workflow(definition, record)

        return {
            "status": status,
            "execution_id": execution_id,
            "error": overall_error,
            "steps": {s.step_id: {"status": s.status, "output": s.output, "error": s.error}
                      for s in self._step_records},
        }

    async def _execute_step_with_retry(self, step: WorkflowStep, context: dict[str, Any]) -> Any:
        """Execute a step with configurable retry logic."""
        cfg = step.config or {}
        max_attempts = int(cfg.get("max_attempts", 1))
        retry_delay = float(cfg.get("retry_delay_sec", 1.0))
        last_error = None

        for attempt in range(max_attempts):
            try:
                return await self._execute_step(step, context)
            except WorkflowExecutionError as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    logger.info("Retrying step %s (attempt %d/%d): %s",
                                step.id, attempt + 1, max_attempts, exc)
                    await asyncio.sleep(retry_delay * (attempt + 1))

        raise WorkflowExecutionError(str(last_error))

    async def _execute_step(self, step: WorkflowStep, context: dict[str, Any]) -> Any:
        """Dispatch a single step to the appropriate harness primitive."""
        previous = self._results.get(step.depends_on[0]) if step.depends_on else None

        if step.mode == "conditional" and previous:
            return await self._execute_conditional(step, context, previous)

        if step.mode == "parallel" and step.children:
            return await self._execute_parallel(step, context)

        if step.type == "agent":
            return await self._execute_agent(step, context)
        elif step.type == "human_input":
            return await self._execute_human_input(step, context)
        elif step.type == "sub_workflow":
            return await self._execute_sub_workflow(step, context)
        elif step.type == "router":
            return await self._execute_router(step, context, previous)
        else:
            raise WorkflowExecutionError(f"Unknown step type: {step.type}")

    async def _execute_agent(self, step: WorkflowStep, context: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to delegate_task (subagent)."""
        goal = self._interpolate(step.prompt, context)
        try:
            from harness.tools.delegate_task import DelegateTaskTool
            tool = DelegateTaskTool()
            cfg = step.config or {}
            result = await tool.run(
                goal=goal,
                toolsets=cfg.get("toolsets", ("read",)),
                role=cfg.get("role", "leaf"),
                model=cfg.get("model"),
                context=json.dumps(context) if context else None,
            )
            return {
                "step_id": step.id, "status": "completed" if result.success else "failed",
                "output": result.output, "data": result.data,
            }
        except Exception as exc:
            raise WorkflowExecutionError(str(exc)) from exc

    async def _execute_human_input(self, step: WorkflowStep, context: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to question tool (HITL pause)."""
        question = self._interpolate(step.prompt, context)
        options = (step.config or {}).get("options")
        timeout = (step.config or {}).get("timeout_sec", 300)
        try:
            from harness.tools.question_tool import QuestionTool
            tool = QuestionTool()
            result = await tool.run(question=question, options=options)
            return {"step_id": step.id, "status": "completed", "output": result.output, "data": result.data}
        except Exception as exc:
            raise WorkflowExecutionError(str(exc)) from exc

    async def _execute_router(self, step: WorkflowStep, context: dict[str, Any], previous: Any) -> dict[str, Any]:
        """Evaluate branch rules against previous output to pick next step."""
        if not step.branch_rules:
            return {"step_id": step.id, "status": "completed", "selected": None}
        prev_str = json.dumps(previous) if previous else ""
        for rule in step.branch_rules:
            try:
                if re.search(rule.condition, prev_str, re.IGNORECASE):
                    return {"step_id": step.id, "status": "completed", "selected": rule.target_step, "reason": rule.label}
            except re.error:
                if rule.condition in prev_str:
                    return {"step_id": step.id, "status": "completed", "selected": rule.target_step, "reason": rule.label}
        return {"step_id": step.id, "status": "completed", "selected": None}

    async def _execute_parallel(self, step: WorkflowStep, context: dict[str, Any]) -> dict[str, Any]:
        """Run child steps concurrently via delegate_task fan-out."""
        if not step.children:
            return {"step_id": step.id, "status": "completed", "children": []}
        tasks = [self._interpolate(c.prompt, context) for c in step.children]
        try:
            from harness.tools.delegate_task import DelegateTaskTool
            tool = DelegateTaskTool()
            cfg = step.config or {}
            result = await tool.run(
                tasks=tasks, toolsets=cfg.get("toolsets", ("read",)),
                role=cfg.get("role", "leaf"), model=cfg.get("model"),
            )
            return {"step_id": step.id, "status": "completed" if result.success else "failed",
                    "output": result.output, "data": result.data, "children_count": len(tasks)}
        except Exception as exc:
            raise WorkflowExecutionError(str(exc)) from exc

    async def _execute_conditional(self, step: WorkflowStep, context: dict[str, Any], previous: Any) -> dict[str, Any]:
        return await self._execute_router(step, context, previous)

    async def _execute_sub_workflow(self, step: WorkflowStep, context: dict[str, Any]) -> dict[str, Any]:
        sub_def = WorkflowDefinition(
            key=f"{step.id}-sub", title=step.label, description="",
            steps=step.children if step.children else [],
        )
        sub = WorkflowExecutor(db=self._db)
        return await sub.execute(sub_def, context)

    async def _dispatch_error_workflow(self, definition: WorkflowDefinition, record: WorkflowExecutionRecord) -> None:
        """If the step config has an error_workflow_key, dispatch the error context there."""
        error_key = None
        for step in definition.steps:
            if step.config and step.config.get("error_workflow_key"):
                error_key = step.config["error_workflow_key"]
                break
        if not error_key:
            return
        try:
            from harness.workflow.models import WorkflowDefinition as WD
            from ..api.routers.workflows import _workflows
            error_wf = _workflows.get(error_key)
            if error_wf:
                error_ctx = {
                    "failed_workflow": definition.key,
                    "execution_id": record.id,
                    "error": record.error,
                    "steps": [s.step_id for s in self._step_records if s.status == "failed"],
                }
                sub = WorkflowExecutor(db=self._db)
                asyncio.create_task(sub.execute(error_wf, context=error_ctx, triggered_by="error"))
        except Exception as exc:
            logger.warning("Error workflow dispatch failed: %s", exc)

    async def _persist(self, record: WorkflowExecutionRecord) -> None:
        """Save execution record to DB (or memory fallback)."""
        try:
            from harness.workflow.store import save_execution, create_workflow_executions_table
            await create_workflow_executions_table(self._db)
            await save_execution(self._db, record)
        except Exception as exc:
            logger.warning("Failed to persist execution: %s", exc)

    def _topological_sort(self, steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
        deps: dict[str, set[str]] = {}
        step_map: dict[str, WorkflowStep] = {}
        for s in steps:
            deps[s.id] = set(s.depends_on) if s.depends_on else set()
            step_map[s.id] = s
        resolved: set[str] = set()
        batches: list[list[WorkflowStep]] = []
        while len(resolved) < len(steps):
            batch = []
            for s in steps:
                if s.id in resolved:
                    continue
                if deps[s.id].issubset(resolved):
                    batch.append(s)
            if not batch:
                raise WorkflowExecutionError("Circular dependency detected in workflow steps")
            for s in batch:
                resolved.add(s.id)
            batches.append(batch)
        return batches

    @staticmethod
    def _interpolate(template: str, context: dict[str, Any]) -> str:
        def _replacer(m: re.Match) -> str:
            key = m.group(1)
            val = context.get(key)
            return str(val) if val is not None else m.group(0)
        return re.sub(r"\{(\w+)\}", _replacer, template)
