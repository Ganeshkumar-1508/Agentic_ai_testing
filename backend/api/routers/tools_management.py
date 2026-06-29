from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, UploadFile, File
from pydantic import BaseModel

from harness.tools.registry import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])

BUILTIN_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "harness" / "tools"
USER_TOOLS_DIR = Path.home() / ".testai" / "tools"
PROJECT_TOOLS_DIR = Path.cwd() / ".testai" / "tools"

# Per-tool config for enable/disable
TOOL_CONFIG_FILE = USER_TOOLS_DIR / "config.json"


def _load_disabled_tools() -> set[str]:
    try:
        if TOOL_CONFIG_FILE.exists():
            cfg = json.loads(TOOL_CONFIG_FILE.read_text())
            return set(cfg.get("disabled", []))
    except Exception:
        pass
    return set()


def _save_disabled_tools(disabled: set[str]) -> None:
    TOOL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOOL_CONFIG_FILE.write_text(json.dumps({"disabled": list(sorted(disabled))}, indent=2))


@router.get("")
async def list_tools():
    """List all registered tools with their source (bundled vs user)."""
    entries = registry.list_entries()
    disabled = _load_disabled_tools()
    result: list[dict[str, Any]] = []

    for entry in entries:
        source = "bundled"
        if entry.toolset in ("custom", "user"):
            source = "user"
        spec = entry.spec
        result.append({
            "name": entry.name,
            "description": spec.get("description", ""),
            "toolset": entry.toolset,
            "source": source,
            "capabilities": entry.capabilities,
            "is_async": entry.is_async,
            "enabled": entry.name not in disabled,
            "tier": getattr(entry, "default_level", "ask") or "ask",
        })

    return {
        "tools": sorted(result, key=lambda t: (t["source"], t["name"])),
        "bundled_count": sum(1 for t in result if t["source"] == "bundled"),
        "user_count": sum(1 for t in result if t["source"] == "user"),
    }


@router.get("/toolsets")
async def list_toolsets():
    """Enumerate the named toolsets (curated bundles) available to roles.

    A toolset is a named list of tools + a list of included sub-toolsets.
    Resolving a list of toolset names yields the flat list of tools the
    role is allowed to call. See `harness/tools/toolsets.py` for the source
    of truth.
    """
    from harness.tools import toolsets as _ts
    out = []
    for name, cfg in _ts.TOOLSETS.items():
        flat = _ts.resolve_toolsets([name])
        out.append({
            "name": name,
            "description": cfg.get("description", ""),
            "tools": cfg.get("tools", []),
            "includes": cfg.get("incluye", cfg.get("includes", [])),
            "resolved": flat,
            "tool_count": len(flat),
        })
    return {"toolsets": out}


@router.post("/toggle")
async def toggle_tool(request: Request):
    """Enable or disable a tool."""
    body = await request.json()
    name = body.get("name", "")
    enabled = body.get("enabled", True)
    disabled = _load_disabled_tools()
    if enabled:
        disabled.discard(name)
    else:
        disabled.add(name)
    _save_disabled_tools(disabled)
    return {"status": "ok", "name": name, "enabled": enabled}


class ToolUploadResponse(BaseModel):
    status: str
    name: str
    message: str


@router.post("/install")
async def install_tool(file: UploadFile = File(...)):
    """Install a user tool. Accepts .py files or .zip/.tar.gz bundles."""
    if not file.filename:
        return ToolUploadResponse(status="error", name="", message="No file provided")

    USER_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()

    # Handle zip/tar.gz bundles
    if file.filename.endswith((".zip", ".tar.gz", ".tgz")):
        return await _install_bundle(file.filename, content)

    # Single .py file
    if not file.filename.endswith(".py"):
        return ToolUploadResponse(status="error", name="", message="File must be .py, .zip, or .tar.gz")

    dest = USER_TOOLS_DIR / file.filename
    dest.write_bytes(content)

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(file.filename[:-3], dest)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        return ToolUploadResponse(
            status="success",
            name=file.filename[:-3],
            message=f"Tool '{file.filename[:-3]}' installed. Restart backend or run discover_tools() to activate.",
        )
    except Exception as e:
        dest.unlink()
        return ToolUploadResponse(status="error", name=file.filename[:-3], message=f"Failed to load: {e}")


async def _install_bundle(filename: str, content: bytes) -> ToolUploadResponse:
    """Install a tool bundle (zip/tar.gz) with dependencies."""
    import io
    import tarfile

    USER_TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                zf.extractall(USER_TOOLS_DIR)
        elif filename.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
                tf.extractall(USER_TOOLS_DIR)
    except Exception as e:
        return ToolUploadResponse(status="error", name="", message=f"Extraction failed: {e}")

    # Install requirements if present
    req_file = USER_TOOLS_DIR / "requirements.txt"
    if req_file.exists():
        try:
            subprocess.run(
                ["pip", "install", "-r", str(req_file)],
                capture_output=True, text=True, timeout=120,
            )
        except Exception as e:
            logger.warning("Failed to install tool dependencies: %s", e)

    return ToolUploadResponse(
        status="success",
        name=filename,
        message=f"Tool bundle '{filename}' extracted. Run discover_tools() to activate.",
    )


@router.delete("/{tool_name}")
async def remove_user_tool(tool_name: str):
    """Remove a user-installed tool by name."""
    # Check user dirs
    for base in (USER_TOOLS_DIR, PROJECT_TOOLS_DIR):
        tool_file = base / f"{tool_name}.py"
        if tool_file.exists():
            tool_file.unlink()
            # Also deregister from registry
            registry.deregister(tool_name)
            return {"status": "removed", "name": tool_name, "message": f"Tool '{tool_name}' removed. Restart to fully unload."}

    return {"status": "not_found", "name": tool_name, "message": f"Tool '{tool_name}' not found in user directories"}
