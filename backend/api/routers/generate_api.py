"""AI test generation from requirements API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/api/generate", tags=["generate"])


class GenerateRequest(BaseModel):
    requirements: str
    project_id: str = "default"
    count: int = 10
    test_type: str = "all"


@router.post("/tests")
async def generate_tests(request: Request, body: GenerateRequest):
    """Generate test cases from requirements using AI."""
    llm_router = request.app.state.llm if hasattr(request.app.state, "llm") else None

    if not llm_router:
        return {"error": "LLM not initialized", "test_cases": [], "count": 0}

    from harness.test_generator import generate_test_cases, save_test_cases
    test_cases = await generate_test_cases(body.requirements, llm_router, count=body.count)

    if not test_cases:
        return {"error": "Failed to generate test cases", "test_cases": [], "count": 0}

    # Save to database
    db = get_db(request)
    saved = await save_test_cases(db, body.project_id, "ai-generated", test_cases)

    return {
        "test_cases": test_cases,
        "count": len(test_cases),
        "saved": saved,
        "project_id": body.project_id,
    }
