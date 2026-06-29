"""Workflow API — CRUD + run + schedule + history for multi-step workflows.

Endpoints:
  GET    /api/workflows                    → list all workflow definitions
  POST   /api/workflows                    → create a new workflow
  GET    /api/workflows/{key}              → get a single workflow
  PUT    /api/workflows/{key}              → update a workflow
  DELETE /api/workflows/{key}              → delete a workflow
  POST   /api/workflows/{key}/run          → execute a workflow on-demand
  POST   /api/workflows/{key}/schedule     → schedule a workflow as cron
  GET    /api/workflows/{key}/executions   → list execution history for a workflow
  GET    /api/workflows/executions/{id}    → get a single execution detail
  POST   /api/workflows/executions/{id}/retry → retry a failed execution
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from harness.workflow import WorkflowDefinition, WorkflowExecutor, WorkflowStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# In-memory store for workflow definitions (migrate to DB when needed)
_workflows: dict[str, WorkflowDefinition] = {}


@router.get("")
async def list_workflows():
    """List all registered workflow definitions."""
    return {
        "workflows": [
            wf.to_dict() for wf in _workflows.values()
        ]
    }


@router.post("")
async def create_workflow(body: dict[str, Any]):
    """Create a new workflow definition from JSON body."""
    key = body.get("key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    if key in _workflows:
        raise HTTPException(status_code=409, detail=f"Workflow '{key}' already exists")

    wf = WorkflowDefinition.from_dict(body)
    _workflows[key] = wf
    return {"status": "ok", "workflow": wf.to_dict()}


@router.get("/{key}")
async def get_workflow(key: str):
    """Get a single workflow definition."""
    wf = _workflows.get(key)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{key}' not found")
    return {"workflow": wf.to_dict()}


@router.put("/{key}")
async def update_workflow(key: str, body: dict[str, Any]):
    """Update an existing workflow definition."""
    if key not in _workflows:
        raise HTTPException(status_code=404, detail=f"Workflow '{key}' not found")

    if body.get("key") and body["key"] != key:
        old_key = key
        new_key = body["key"]
        del _workflows[old_key]
        key = new_key

    wf = WorkflowDefinition.from_dict({**body, "key": key})
    _workflows[key] = wf
    return {"status": "ok", "workflow": wf.to_dict()}


@router.delete("/{key}")
async def delete_workflow(key: str):
    """Delete a workflow definition."""
    if key not in _workflows:
        raise HTTPException(status_code=404, detail=f"Workflow '{key}' not found")
    del _workflows[key]
    return {"status": "deleted"}


@router.post("/{key}/run")
async def run_workflow(request: Request, key: str, body: dict[str, Any] | None = None):
    """Execute a workflow on-demand. Context can be passed in body."""
    wf = _workflows.get(key)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{key}' not found")

    context = dict(body or {}).get("context", {})
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    executor = WorkflowExecutor(db=db)
    result = await executor.execute(wf, context=context)
    return {
        "status": result["status"],
        "workflow_key": key,
        "steps": result.get("steps", {}),
    }


@router.post("/{key}/schedule")
async def schedule_workflow(request: Request, key: str, body: dict[str, Any]):
    """Schedule a workflow as a cron job using the existing blueprint system."""
    wf = _workflows.get(key)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{key}' not found")

    schedule_expr = body.get("schedule", "0 9 * * 1-5")
    values = body.get("values", {})

    try:
        from harness.scheduler.store import create_table, create_job
        from ..deps import get_db
        db = get_db(request)
        await create_table(db)

        job_config = {
            "name": wf.title,
            "prompt": json.dumps({"workflow_key": key, "values": values}),
            "schedule_type": "cron",
            "schedule_expr": schedule_expr,
            "workflow_key": key,
        }
        job = await create_job(db, job_config)
        return {"status": "ok", "job": job}
    except Exception as e:
        logger.error("Failed to schedule workflow %s: %s", key, e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Execution history endpoints
# ---------------------------------------------------------------------------


@router.get("/executions")
async def list_all_executions(request: Request, limit: int = 50):
    """List all workflow executions across all workflows."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    from harness.workflow.store import list_executions, create_workflow_executions_table
    await create_workflow_executions_table(db)
    records = await list_executions(db, limit=limit)
    return {"executions": [r.to_dict() for r in records]}


@router.get("/{key}/executions")
async def list_workflow_executions(request: Request, key: str, limit: int = 20):
    """List execution history for a specific workflow."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    from harness.workflow.store import list_executions, create_workflow_executions_table
    await create_workflow_executions_table(db)
    records = await list_executions(db, workflow_key=key, limit=limit)
    return {"executions": [r.to_dict() for r in records]}


@router.get("/executions/{execution_id}")
async def get_workflow_execution(request: Request, execution_id: str):
    """Get a single execution record with full step details."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    from harness.workflow.store import get_execution
    record = await get_execution(db, execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return {"execution": record.to_dict()}


@router.post("/executions/{execution_id}/retry")
async def retry_workflow_execution(request: Request, execution_id: str):
    """Retry a failed execution. Re-runs the workflow with the same definition."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    from harness.workflow.store import get_execution
    original = await get_execution(db, execution_id)
    if original is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    wf = _workflows.get(original.workflow_key)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{original.workflow_key}' not found")

    executor = WorkflowExecutor(db=db)
    result = await executor.execute(wf, triggered_by="retry", retry_of=execution_id)
    return {
        "status": result["status"],
        "execution_id": result.get("execution_id"),
        "retry_of": execution_id,
    }
