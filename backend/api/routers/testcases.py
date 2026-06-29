"""Test cases API — thin router, delegates to TestCasesService."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import get_db, get_llm, get_agent
from harness.tools.registry import registry
from harness.services.testcases_service import TestCasesService

router = APIRouter(prefix="/api", tags=["testcases"])


class TestCaseCreate(BaseModel):
    project_id: str = "default-project"
    requirement_id: str | None = None
    name: str
    description: str | None = None
    test_type: str = "api"
    status: str = "pending"
    priority: str = "medium"
    steps: dict | list | None = None
    expected: str | None = None
    test_data: dict | list | None = None
    code: str | None = None
    code_language: str = "python"


class TestCaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    test_type: str | None = None
    status: str | None = None
    priority: str | None = None
    steps: dict | list | None = None
    expected: str | None = None
    test_data: dict | list | None = None
    code: str | None = None
    code_language: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None


class HealRequest(BaseModel):
    test_name: str
    test_code: str = ""
    failure_output: str = ""
    language: str = "python"
    framework: str = "pytest"
    run_id: str = ""


class AnalyzeRequest(BaseModel):
    files: list[str]
    contents: dict[str, str] = {}
    project_name: str = ""


class FolderCreate(BaseModel):
    name: str
    filter_types: list[str] = []
    icon: str = "folder"


@router.get("/testcases")
async def list_test_cases(request: Request, project_id: str = "default-project",
                           test_type: str | None = None, status: str | None = None):
    svc = TestCasesService(get_db(request))
    return {"test_cases": await svc.list_test_cases(project_id, test_type, status)}


# NOTE: `/testcases/folders*` routes MUST be declared before
# `/testcases/{test_case_id}` — otherwise the path parameter swallows
# `folders` and the folder endpoints become unreachable.


@router.get("/testcases/folders")
async def list_folders(request: Request):
    svc = TestCasesService(get_db(request))
    return {"folders": await svc.list_folders()}


@router.post("/testcases/folders")
async def create_folder(request: Request, req: FolderCreate):
    svc = TestCasesService(get_db(request))
    return {"folder": await svc.create_folder(req.name, req.filter_types, req.icon)}


@router.delete("/testcases/folders/{folder_id}")
async def delete_folder(request: Request, folder_id: str):
    svc = TestCasesService(get_db(request))
    await svc.delete_folder(folder_id)
    return {"status": "ok"}


@router.get("/testcases/{test_case_id}")
async def get_test_case(request: Request, test_case_id: str):
    svc = TestCasesService(get_db(request))
    result = await svc.get_test_case(test_case_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Test case not found"})
    return {"test_case": result}


@router.post("/testcases")
async def create_test_case(request: Request, req: TestCaseCreate):
    svc = TestCasesService(get_db(request))
    result = await svc.create_test_case(req.model_dump())
    return {"test_case": result}


@router.put("/testcases/{test_case_id}")
async def update_test_case(request: Request, test_case_id: str, req: TestCaseUpdate):
    svc = TestCasesService(get_db(request))
    result = await svc.update_test_case(test_case_id, req.model_dump())
    if not result:
        return JSONResponse(status_code=400, content={"error": "No fields to update"})
    return {"test_case": result}


@router.post("/testcases/{test_case_id}/run")
async def run_test_case(request: Request, test_case_id: str):
    db = get_db(request)
    row = await db.fetchrow("SELECT code, code_language FROM test_cases WHERE id = $1", test_case_id)
    if not row:
        return JSONResponse(status_code=404, content={"error": "Test case not found"})
    code = row["code"] or ""
    language = row["code_language"] or "python"
    if not code:
        return JSONResponse(status_code=400, content={"error": "Test case has no code"})
    from harness.tools.docker_executor import DockerExecutorTool
    result = await DockerExecutorTool().run(code=code, language=language, timeout=120)
    return {"output": result.output, "success": result.success, "error": result.error}


@router.delete("/testcases/{test_case_id}")
async def delete_test_case(request: Request, test_case_id: str):
    svc = TestCasesService(get_db(request))
    await svc.delete_test_case(test_case_id)
    return {"status": "ok"}


@router.post("/tests/heal")
async def heal_test(request: Request, req: HealRequest):
    from harness.llm import ChatMessage
    db = get_db(request)
    agent = get_agent(request)
    llm = get_llm(request)
    executor = registry.get("test_executor")
    if not executor:
        from harness.tools.test_executor import TestExecutorTool
        executor = TestExecutorTool()
    code = req.test_code
    for attempt in range(1, 2):
        retry_result = await executor.run(code=code, language=req.language, framework=req.framework, timeout_ms=10_000)
        if retry_result.success:
            await db.execute("UPDATE test_results SET retry_count=$1, status='passed' WHERE run_id=$2 AND test_name=$3",
                             attempt, req.run_id, req.test_name)
            return {"status": "passed", "attempt": attempt, "healed": False, "output": retry_result.output}
    if not agent or not llm:
        return {"status": "failed", "error": "Agent not available for self-heal"}
    failure_snippet = (retry_result.output or req.failure_output)[:2000] if 'retry_result' in dir() else req.failure_output[:2000]
    for heal_iter in range(1, 2):
        messages = [
            ChatMessage(role="system", content="You are a test repair specialist. Return ONLY the corrected code, no explanations."),
            ChatMessage(role="user", content=f"Test: {req.test_name}\nLanguage: {req.language}\nFramework: {req.framework}\n\n"
                        f"Code:\n```\n{code}\n```\n\nFailure:\n```\n{failure_snippet}\n```"),
        ]
        try:
            response = await llm.chat(messages=messages)
            fixed_code = response.content.strip()
            if fixed_code.startswith("```"):
                fixed_code = fixed_code.split("\n", 1)[-1].rsplit("```", 1)[0]
        except Exception as e:
            return {"status": "failed", "error": f"LLM heal failed: {e}"}
        if not fixed_code or fixed_code == code:
            break
        result = await executor.run(code=fixed_code, language=req.language, framework=req.framework, timeout_ms=10_000)
        if result.success:
            await db.execute("UPDATE test_results SET status='passed', healed_by_agent=true WHERE run_id=$1 AND test_name=$2",
                             req.run_id, req.test_name)
            return {"status": "healed", "healed": True, "fixed_code": fixed_code, "output": result.output}
        code = fixed_code
        failure_snippet = (result.output or "")[:2000]
    return {"status": "failed", "error": "Max heal iterations reached"}


@router.get("/tests/flaky")
async def get_flaky_tests(request: Request, limit: int = 20):
    svc = TestCasesService(get_db(request))
    return {"flaky": await svc.get_flaky_tests(limit)}


@router.post("/tests/flaky/{test_name}/quarantine")
async def toggle_quarantine(request: Request, test_name: str, req: dict[str, Any]):
    svc = TestCasesService(get_db(request))
    await svc.toggle_quarantine(test_name, req.get("branch", ""), req.get("quarantine", True))
    return {"status": "ok", "testName": test_name, "isQuarantined": req.get("quarantine", True)}


@router.post("/analyze")
async def analyze_project(request: Request, req: AnalyzeRequest):
    agent = get_agent(request)
    if not agent:
        return JSONResponse(status_code=503, content={"error": "Agent not initialized"})
    from harness.tools.tech_stack import TechStackDetectorTool
    detect_result = await TechStackDetectorTool().run(files=req.files, contents=req.contents)
    tech = detect_result.data if detect_result.success else {}
    return {
        "success": True,
        "techStack": {
            "language": tech.get("primary_language"),
            "framework": tech.get("flags", {}).get("framework"),
            "testFramework": None, "version": None,
            "packageManager": tech.get("flags", {}).get("package_manager"),
            "configFiles": [f for f in req.files if any(f.endswith(c) for c in
                           ["package.json", "requirements.txt", "pyproject.toml", "go.mod",
                            "Cargo.toml", "Gemfile", "composer.json", "build.gradle",
                            "pom.xml", "tsconfig.json", "Dockerfile"])],
            "hasTests": any("test" in f.lower() or "spec" in f.lower() for f in req.files),
            "confidence": "high" if tech.get("has_config") else "medium",
        },
        "totalFiles": len(req.files),
    }


@router.patch("/testcases/{test_case_id}/tags")
async def update_test_case_tags(request: Request, test_case_id: str):
    svc = TestCasesService(get_db(request))
    body = await request.json()
    tags = body.get("tags", [])
    await svc.update_tags(test_case_id, tags)
    return {"status": "ok", "tags": tags}
