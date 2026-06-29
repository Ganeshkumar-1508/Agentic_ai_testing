"""Sandbox configuration API — read/update sandbox settings.

Supports:
  - Size presets: auto, small, medium, large, xlarge
  - Custom image override
  - Network mode override
  - Backend type selector (local / docker / ssh)
  - SSH connection config (host, user, port, key_path)
  - Default timeout & container persistence toggle
  - GET returns current config, POST updates it
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import get_db
from harness.sandbox_scope import SANDBOX_SIZES, apply_size_preset

router = APIRouter(prefix="/api/settings/sandbox", tags=["sandbox"])

BACKEND_TYPES = ("local", "docker", "ssh")
NETWORK_MODES = ("bridge", "none", "host")

DEFAULTS = {
    "size": "auto",
    "image": "nikolaik/python-nodejs:python3.11-nodejs20",
    "network": "bridge",
    "default_backend_type": "local",
    "default_timeout": "120",
    "container_persistent": "true",
    "ssh_host": "",
    "ssh_user": "",
    "ssh_port": "22",
    "ssh_key_path": "",
}


class SandboxConfigUpdate(BaseModel):
    size: str | None = None
    image: str | None = None
    network: str | None = None
    default_backend_type: str | None = None
    default_timeout: str | None = None
    container_persistent: str | None = None
    ssh_host: str | None = None
    ssh_user: str | None = None
    ssh_port: str | None = None
    ssh_key_path: str | None = None


@router.get("")
async def get_sandbox_config(request: Request):
    """Get current sandbox configuration."""
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM sandbox_config ORDER BY key")
    config = {r["key"]: r["value"] for r in rows}
    result = {**DEFAULTS, **config}
    result["size_presets"] = SANDBOX_SIZES
    result["default_size"] = "auto"
    size = result.get("size", "auto")
    preset = apply_size_preset(size)
    result["effective_cpus"] = preset.get("cpus", "2.0")
    result["effective_memory"] = preset.get("memory", "4g")
    return {"config": result}


@router.post("")
async def update_sandbox_config(request: Request, body: SandboxConfigUpdate):
    """Update sandbox configuration. Pass only fields to change."""
    db = get_db(request)
    updates = {}

    if body.size is not None:
        if body.size not in ("auto", *SANDBOX_SIZES.keys()):
            return {"error": f"Invalid size: {body.size}. Must be one of: auto, {', '.join(SANDBOX_SIZES.keys())}"}
        updates["size"] = body.size

    if body.image is not None:
        updates["image"] = body.image

    if body.network is not None:
        if body.network not in NETWORK_MODES:
            return {"error": f"Invalid network: {body.network}. Must be one of: {', '.join(NETWORK_MODES)}"}
        updates["network"] = body.network

    if body.default_backend_type is not None:
        if body.default_backend_type not in BACKEND_TYPES:
            return {"error": f"Invalid backend_type: {body.default_backend_type}. Must be one of: {', '.join(BACKEND_TYPES)}"}
        updates["default_backend_type"] = body.default_backend_type

    if body.default_timeout is not None:
        try:
            val = int(body.default_timeout)
            if val < 1 or val > 3600:
                return {"error": "default_timeout must be between 1 and 3600"}
        except ValueError:
            return {"error": "default_timeout must be an integer"}
        updates["default_timeout"] = body.default_timeout

    if body.container_persistent is not None:
        if body.container_persistent not in ("true", "false"):
            return {"error": "container_persistent must be 'true' or 'false'"}
        updates["container_persistent"] = body.container_persistent

    if body.ssh_host is not None:
        updates["ssh_host"] = body.ssh_host
    if body.ssh_user is not None:
        updates["ssh_user"] = body.ssh_user
    if body.ssh_port is not None:
        updates["ssh_port"] = body.ssh_port
    if body.ssh_key_path is not None:
        updates["ssh_key_path"] = body.ssh_key_path

    for key, value in updates.items():
        await db.execute(
            "INSERT INTO sandbox_config (key, value) VALUES ($1, $2) "
            "ON CONFLICT (key) DO UPDATE SET value = $2",
            key, str(value),
        )

    return {"status": "ok", "updated": updates}
