"""Session Recordings API — list and serve JSONL session recordings."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from harness.recording import SESSION_LOG_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/recordings")
async def list_recordings(request: Request):
    """List all JSONL session recordings."""
    log_dir = Path(SESSION_LOG_DIR)
    if not log_dir.exists():
        return {"recordings": []}

    recordings = []
    for f in sorted(log_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        stats = f.stat()
        recordings.append({
            "session_id": f.stem,
            "path": f.name,
            "size_bytes": stats.st_size,
            "created_at": f.stat().st_mtime,
        })
    return {"recordings": recordings}


@router.get("/recordings/{session_id}")
async def get_recording(request: Request, session_id: str):
    """Get the full JSONL content for a session recording."""
    log_dir = Path(SESSION_LOG_DIR)
    file_path = log_dir / f"{session_id}.jsonl"
    if not file_path.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Recording not found"})

    events = []
    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {"session_id": session_id, "events": events}


@router.get("/recordings/{session_id}/download")
async def download_recording(request: Request, session_id: str):
    """Download the JSONL file."""
    log_dir = Path(SESSION_LOG_DIR)
    file_path = log_dir / f"{session_id}.jsonl"
    if not file_path.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Recording not found"})
    content = file_path.read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="application/x-ndjson",
                             headers={"Content-Disposition": f'attachment; filename="{session_id}.jsonl"'})
