"""Saved Filters API — CRUD for reusable dashboard/test filters."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/api/saved-filters", tags=["saved-filters"])


class SaveFilterRequest(BaseModel):
    name: str
    description: str = ""
    filter_data: str = "{}"
    icon: str = "Filter"


@router.get("")
async def list_filters(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM saved_filters ORDER BY sort_order ASC, name ASC")
    return {"filters": [dict(r) for r in rows]}


@router.post("")
async def create_filter(request: Request, body: SaveFilterRequest):
    db = get_db(request)
    await db.execute(
        "INSERT INTO saved_filters (name, description, filter_data, icon) VALUES ($1, $2, $3, $4)",
        body.name, body.description, body.filter_data, body.icon,
    )
    return {"status": "ok"}


@router.put("/{filter_id}")
async def update_filter(request: Request, filter_id: str, body: SaveFilterRequest):
    db = get_db(request)
    await db.execute(
        "UPDATE saved_filters SET name=$1, description=$2, filter_data=$3, icon=$4 WHERE id=$5",
        body.name, body.description, body.filter_data, body.icon, filter_id,
    )
    return {"status": "ok"}


@router.delete("/{filter_id}")
async def delete_filter(request: Request, filter_id: str):
    db = get_db(request)
    await db.execute("DELETE FROM saved_filters WHERE id=$1", filter_id)
    return {"status": "deleted"}
