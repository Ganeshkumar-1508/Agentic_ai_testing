"""
TestAI Platform - API v1 Endpoints
FastAPI routes for agent orchestration and test generation
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import asyncio

from app.models.database import (
    get_db, Project, Requirement, TestCase, AgentRun, AgentLog,
    AgentStatus, TestStatus, RequirementStatus
)
from app.agents.swarm_manager import swarm_manager, WorkflowResult
from app.core.config import LLM_PROVIDERS, TEST_TYPES, AGENT_DEFINITIONS


router = APIRouter()


# ============== Request/Response Models ==============

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    default_provider: str = "openai"
    default_model: str = "gpt-4o"


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    default_provider: str
    default_model: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class RequirementCreate(BaseModel):
    project_id: str
    title: str
    description: Optional[str] = None
    raw_content: Optional[str] = None
    source_type: str = "text"


class RequirementResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: str
    source_type: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowStartRequest(BaseModel):
    project_id: str
    requirements: str
    test_types: List[str] = ["api", "ui", "unit"]
    provider: str = "openai"
    model: Optional[str] = None
    auto_run: bool = False


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: str
    agents: List[Dict[str, Any]]
    test_cases: List[Dict[str, Any]]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class TestCaseCreate(BaseModel):
    project_id: str
    requirement_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    test_type: str
    priority: str = "medium"
    steps: Optional[List[Dict[str, Any]]] = None
    code: Optional[str] = None
    code_language: str = "python"


class TestCaseResponse(BaseModel):
    id: str
    name: str
    test_type: str
    status: str
    priority: str
    code_language: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============== Provider & Model Info ==============

@router.get("/providers")
async def get_providers():
    """Get available LLM providers and their models"""
    return {
        "providers": [
            {
                "name": key,
                "display_name": value["name"],
                "models": value["models"],
                "default_model": value["default_model"],
            }
            for key, value in LLM_PROVIDERS.items()
        ]
    }


@router.get("/test-types")
async def get_test_types():
    """Get available test types"""
    return {"test_types": TEST_TYPES}


@router.get("/agents")
async def get_agent_types():
    """Get available agent types"""
    return {
        "agents": [
            {
                "type": key,
                "name": value["name"],
                "description": value["description"],
                "recommended_model": value["recommended_model"],
            }
            for key, value in AGENT_DEFINITIONS.items()
        ]
    }


# ============== Projects ==============

@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new project"""
    project = Project(
        name=project_data.name,
        description=project_data.description,
        default_provider=project_data.default_provider,
        default_model=project_data.default_model,
        user_id="default-user",  # TODO: Get from auth
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        status=project.status.value,
        default_provider=project.default_provider,
        default_model=project.default_model,
        created_at=project.created_at,
    )


@router.get("/projects")
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all projects"""
    result = await db.execute(
        select(Project)
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    projects = result.scalars().all()
    
    return {
        "projects": [
            ProjectResponse(
                id=str(p.id),
                name=p.name,
                description=p.description,
                status=p.status.value,
                default_provider=p.default_provider,
                default_model=p.default_model,
                created_at=p.created_at,
            )
            for p in projects
        ]
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get project details"""
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {
        "project": ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status.value,
            default_provider=project.default_provider,
            default_model=project.default_model,
            created_at=project.created_at,
        )
    }


# ============== Requirements ==============

@router.post("/requirements", response_model=RequirementResponse)
async def create_requirement(
    requirement_data: RequirementCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new requirement"""
    requirement = Requirement(
        project_id=requirement_data.project_id,
        title=requirement_data.title,
        description=requirement_data.description,
        raw_content=requirement_data.raw_content,
        source_type=requirement_data.source_type,
    )
    db.add(requirement)
    await db.commit()
    await db.refresh(requirement)
    
    return RequirementResponse(
        id=str(requirement.id),
        title=requirement.title,
        description=requirement.description,
        status=requirement.status.value,
        source_type=requirement.source_type,
        created_at=requirement.created_at,
    )


@router.get("/requirements")
async def list_requirements(
    project_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List requirements for a project"""
    result = await db.execute(
        select(Requirement)
        .where(Requirement.project_id == project_id)
        .order_by(Requirement.created_at.desc())
    )
    requirements = result.scalars().all()
    
    return {
        "requirements": [
            RequirementResponse(
                id=str(r.id),
                title=r.title,
                description=r.description,
                status=r.status.value,
                source_type=r.source_type,
                created_at=r.created_at,
            )
            for r in requirements
        ]
    }


# ============== Workflow ==============

# Store for tracking workflow progress
workflow_progress = {}


@router.post("/workflow/start")
async def start_workflow(
    request: WorkflowStartRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a test generation workflow"""
    # Create requirement record
    requirement = Requirement(
        project_id=request.project_id,
        title="Generated from workflow",
        description=request.requirements[:500],
        raw_content=request.requirements,
        status=RequirementStatus.PROCESSING,
    )
    db.add(requirement)
    await db.commit()
    await db.refresh(requirement)
    
    # Create agent run record
    agent_run = AgentRun(
        project_id=request.project_id,
        agent_type="workflow",
        agent_name="Test Generation Workflow",
        status=AgentStatus.PENDING,
        provider=request.provider,
        model=request.model or request.provider,
    )
    db.add(agent_run)
    await db.commit()
    await db.refresh(agent_run)
    
    workflow_id = str(agent_run.id)
    
    # Define progress callback
    def on_progress(agent_type: str, progress: int, message: str):
        workflow_progress[workflow_id] = {
            "agent_type": agent_type,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    # Run workflow in background
    async def run_workflow():
        try:
            result = await swarm_manager.run_test_generation_workflow(
                requirements=request.requirements,
                test_types=request.test_types,
                provider=request.provider,
                model=request.model,
                workflow_id=workflow_id,
                on_progress=on_progress,
            )
            
            # Update agent run
            agent_run.status = AgentStatus.COMPLETED if result.status == "completed" else AgentStatus.FAILED
            agent_run.completed_at = datetime.utcnow()
            
            # Save test cases
            for tc in result.test_cases:
                test_case = TestCase(
                    project_id=request.project_id,
                    requirement_id=str(requirement.id),
                    name=tc.get("name", "Generated Test"),
                    test_type=tc.get("type", "api"),
                    code=tc.get("content"),
                    code_language="python" if tc.get("type") in ["api", "unit"] else "typescript",
                )
                db.add(test_case)
            
            # Update requirement status
            requirement.status = RequirementStatus.COMPLETED
            
            await db.commit()
            
        except Exception as e:
            agent_run.status = AgentStatus.FAILED
            agent_run.error_message = str(e)
            requirement.status = RequirementStatus.FAILED
            await db.commit()
    
    background_tasks.add_task(run_workflow)
    
    return {
        "success": True,
        "workflow_id": workflow_id,
        "requirement_id": str(requirement.id),
        "message": "Workflow started",
    }


@router.get("/workflow/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get workflow status and progress"""
    # Get from swarm manager
    workflow_result = swarm_manager.get_workflow(workflow_id)
    
    # Get from database
    result = await db.execute(
        select(AgentRun).where(AgentRun.id == workflow_id)
    )
    agent_run = result.scalar_one_or_none()
    
    if not agent_run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Get progress
    progress = workflow_progress.get(workflow_id, {})
    
    return {
        "workflow_id": workflow_id,
        "status": agent_run.status.value,
        "provider": agent_run.provider,
        "model": agent_run.model,
        "progress": progress,
        "started_at": agent_run.started_at,
        "completed_at": agent_run.completed_at,
        "error_message": agent_run.error_message,
    }


@router.get("/workflows")
async def list_workflows(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all workflows"""
    query = select(AgentRun).order_by(AgentRun.created_at.desc())
    
    if project_id:
        query = query.where(AgentRun.project_id == project_id)
    
    result = await db.execute(query.limit(20))
    agent_runs = result.scalars().all()
    
    return {
        "workflows": [
            {
                "id": str(ar.id),
                "agent_type": ar.agent_type,
                "status": ar.status.value,
                "provider": ar.provider,
                "model": ar.model,
                "created_at": ar.created_at,
                "completed_at": ar.completed_at,
            }
            for ar in agent_runs
        ]
    }


# ============== Test Cases ==============

@router.post("/testcases", response_model=TestCaseResponse)
async def create_test_case(
    test_case_data: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a test case"""
    test_case = TestCase(
        project_id=test_case_data.project_id,
        requirement_id=test_case_data.requirement_id,
        name=test_case_data.name,
        description=test_case_data.description,
        test_type=test_case_data.test_type,
        priority=test_case_data.priority,
        steps=test_case_data.steps,
        code=test_case_data.code,
        code_language=test_case_data.code_language,
    )
    db.add(test_case)
    await db.commit()
    await db.refresh(test_case)
    
    return TestCaseResponse(
        id=str(test_case.id),
        name=test_case.name,
        test_type=test_case.test_type,
        status=test_case.status.value,
        priority=test_case.priority,
        code_language=test_case.code_language,
        created_at=test_case.created_at,
    )


@router.get("/testcases")
async def list_test_cases(
    project_id: str = Query(...),
    test_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List test cases for a project"""
    query = select(TestCase).where(TestCase.project_id == project_id)
    
    if test_type:
        query = query.where(TestCase.test_type == test_type)
    if status:
        query = query.where(TestCase.status == status)
    
    query = query.order_by(TestCase.created_at.desc())
    
    result = await db.execute(query)
    test_cases = result.scalars().all()
    
    return {
        "test_cases": [
            {
                "id": str(tc.id),
                "name": tc.name,
                "test_type": tc.test_type,
                "status": tc.status.value,
                "priority": tc.priority,
                "code_language": tc.code_language,
                "created_at": tc.created_at,
            }
            for tc in test_cases
        ]
    }


@router.get("/testcases/{test_case_id}")
async def get_test_case(
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get test case details"""
    result = await db.execute(
        select(TestCase).where(TestCase.id == test_case_id)
    )
    test_case = result.scalar_one_or_none()
    
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    return {
        "test_case": {
            "id": str(test_case.id),
            "name": test_case.name,
            "description": test_case.description,
            "test_type": test_case.test_type,
            "status": test_case.status.value,
            "priority": test_case.priority,
            "steps": test_case.steps,
            "code": test_case.code,
            "code_language": test_case.code_language,
            "error_message": test_case.error_message,
            "created_at": test_case.created_at,
        }
    }


@router.delete("/testcases/{test_case_id}")
async def delete_test_case(
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a test case"""
    result = await db.execute(
        select(TestCase).where(TestCase.id == test_case_id)
    )
    test_case = result.scalar_one_or_none()
    
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    
    await db.delete(test_case)
    await db.commit()
    
    return {"success": True, "message": "Test case deleted"}


# ============== Dashboard ==============

@router.get("/dashboard")
async def get_dashboard(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics"""
    # Test case counts
    tc_query = select(TestCase)
    if project_id:
        tc_query = tc_query.where(TestCase.project_id == project_id)
    
    result = await db.execute(tc_query)
    test_cases = result.scalars().all()
    
    # Count by status
    status_counts = {}
    for tc in test_cases:
        status = tc.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Count by type
    type_counts = {}
    for tc in test_cases:
        t_type = tc.test_type
        type_counts[t_type] = type_counts.get(t_type, 0) + 1
    
    # Calculate pass rate
    passed = status_counts.get("passed", 0)
    failed = status_counts.get("failed", 0)
    total_with_result = passed + failed
    pass_rate = (passed / total_with_result * 100) if total_with_result > 0 else 0
    
    # Recent agent runs
    ar_query = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(5)
    if project_id:
        ar_query = ar_query.where(AgentRun.project_id == project_id)
    
    result = await db.execute(ar_query)
    recent_runs = result.scalars().all()
    
    return {
        "stats": {
            "total_tests": len(test_cases),
            "passed": passed,
            "failed": failed,
            "pending": status_counts.get("pending", 0),
            "pass_rate": round(pass_rate, 1),
            "by_type": [{"type": k, "count": v} for k, v in type_counts.items()],
        },
        "recent_runs": [
            {
                "id": str(ar.id),
                "agent_type": ar.agent_type,
                "status": ar.status.value,
                "created_at": ar.created_at,
            }
            for ar in recent_runs
        ],
    }
