"""Slash command API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from harness.chat.slash_base import dispatch as dispatch_slash, list_all as list_commands

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/slash")
async def handle_slash(body: dict[str, Any]):
    """Handle a slash command. Body: {command: str, args?: str, session_id?: str}"""
    command = body.get("command", "").lstrip("/")
    args = body.get("args", "")
    session_id = body.get("session_id", "")

    if not command:
        return {"status": "error", "output": "No command provided"}

    output = await dispatch_slash(command, args=args, session_id=session_id)
    return {"status": "ok", "output": output}


@router.get("/commands")
async def get_commands():
    """List available slash commands."""
    return {"commands": list_commands()}
