"""Read/write helpers for the session_backend_configs table."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def get_backend_config(db, session_id: str) -> dict[str, Any]:
    """Read config JSON for a session. Returns {} if no row exists."""
    row = db.fetchone(
        "SELECT config FROM session_backend_configs WHERE session_id = $1",
        [session_id],
    )
    if row and row[0]:
        if isinstance(row[0], dict):
            return row[0]
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def upsert_backend_config(db, session_id: str, config: dict[str, Any]) -> None:
    """Insert or update the config row for a session."""
    now = datetime.now(timezone.utc)
    db.execute(
        """INSERT INTO session_backend_configs (session_id, config, created_at, updated_at)
           VALUES ($1, $2::jsonb, $3, $3)
           ON CONFLICT (session_id)
           DO UPDATE SET config = $2::jsonb, updated_at = $3""",
        [session_id, json.dumps(config), now],
    )
