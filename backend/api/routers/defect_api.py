"""Defect prediction API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/defect", tags=["defect"])


@router.get("/predict")
async def predict_defects(request: Request, days: int = 30):
    """Get defect risk predictions for all modules."""
    db = get_db(request)
    from harness.defect_prediction import compute_risk_scores
    result = await compute_risk_scores(db, days=days)
    return result
