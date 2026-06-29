"""MCP Config Manager — Filesystem-first MCP server configuration.

Reads from ``<cwd>/.testai/mcp.json`` and ``~/.testai/mcp.json`` (industry
standard pattern shared by VS Code, Claude Code, Cursor, OpenCode, Hermes).
Postgres mirrors the filesystem for dashboard queries — file is source of truth.

Format (matches VS Code ``mcp.json`` standard):

.. code:: json

    {
      "mcpServers": {
        "server-name": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-github"],
          "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" }
        }
      }
    }

Resolution order (highest priority first):
  1. ``MCP_CONFIG_PATH`` env var
  2. ``<cwd>/.testai/mcp.json`` (project)
  3. ``~/.testai/mcp.json`` (global)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_config_path() -> Path | None:
    """Resolve the MCP config file path using resolution order."""
    env_path = os.environ.get("MCP_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    cwd = Path.cwd()
    project_path = cwd / ".testai" / "mcp.json"
    if project_path.exists():
        return project_path

    home_path = Path.home() / ".testai" / "mcp.json"
    if home_path.exists():
        return home_path

    return None


def get_default_config_path() -> Path:
    """Return the default config path (project first, fallback to home)."""
    cwd = Path.cwd()
    project_dir = cwd / ".testai"
    if project_dir.exists() or not (Path.home() / ".testai").exists():
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / "mcp.json"
    home_dir = Path.home() / ".testai"
    home_dir.mkdir(parents=True, exist_ok=True)
    return home_dir / "mcp.json"


def serialize_server(server: dict) -> dict:
    """Convert a DB row to the mcp.json server entry format."""
    entry: dict[str, Any] = {}
    if server.get("server_url"):
        if server.get("server_type") == "command":
            entry["command"] = server["server_url"]
        else:
            entry["url"] = server["server_url"]
    elif server.get("config"):
        try:
            cfg = json.loads(server["config"]) if isinstance(server["config"], str) else server["config"]
            if isinstance(cfg, dict):
                for k in ("command", "args", "env", "transport", "timeout", "connect_timeout", "headers"):
                    if k in cfg:
                        entry[k] = cfg[k]
                if "command" in entry and "args" not in entry:
                    entry["args"] = []
        except (json.JSONDecodeError, TypeError):
            pass
    return entry


def deserialize_server(name: str, entry: dict) -> dict:
    """Convert an mcp.json server entry to a DB row dict."""
    server_url = entry.get("url", "")
    server_type = "http" if "url" in entry else "command"
    if not server_url and "command" in entry:
        server_url = entry["command"]

    config = {}
    for k in ("command", "args", "env", "transport", "timeout", "connect_timeout", "headers"):
        if k in entry:
            config[k] = entry[k]

    return {
        "name": name,
        "display_name": entry.get("displayName", name),
        "description": entry.get("description", ""),
        "category": entry.get("category", "custom"),
        "server_type": server_type,
        "server_url": server_url,
        "enabled": entry.get("disabled", False) is not True,
        "config": json.dumps(config) if config else None,
    }


def load_config() -> list[dict]:
    """Load MCP servers from the filesystem config file.

    Returns a list of DB-row-shaped dicts (ready for DB upsert).
    Returns empty list if no config file found.
    """
    config_path = get_config_path()
    if not config_path:
        return []

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        servers_raw = data.get("mcpServers", {})
        if not isinstance(servers_raw, dict):
            logger.warning("mcp.json: 'mcpServers' must be an object")
            return []

        servers = []
        for name, entry in servers_raw.items():
            if not isinstance(entry, dict):
                continue
            servers.append(deserialize_server(name, entry))
        return servers
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load MCP config: %s", e)
        return []


def save_config(servers: list[dict]) -> None:
    """Save MCP servers to the filesystem config file.

    Args:
        servers: List of DB-row-shaped dicts.
    """
    config_path = get_default_config_path()

    mcp_servers: dict[str, dict] = {}
    for srv in servers:
        name = srv.get("name", "")
        if not name:
            continue
        mcp_servers[name] = serialize_server(srv)
        mcp_servers[name]["displayName"] = srv.get("display_name", name)
        if srv.get("description"):
            mcp_servers[name]["description"] = srv["description"]
        if srv.get("category") and srv["category"] not in ("custom", ""):
            mcp_servers[name]["category"] = srv["category"]

    data = {"mcpServers": mcp_servers}
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Saved MCP config to %s (%d servers)", config_path, len(mcp_servers))


async def sync_to_db(db, servers: list[dict]) -> None:
    """Sync filesystem config to the Postgres mirror.

    Upserts each server, deletes servers in DB not in the file.
    """
    if not servers:
        return

    names_in_file = {s["name"] for s in servers}

    # Upsert each server from file
    for srv in servers:
        existing = await db.fetchrow("SELECT id FROM mcp_configs WHERE name = $1", srv["name"])
        if existing:
            sets = []
            vals = []
            i = 1
            for col in ("display_name", "description", "category", "server_type", "server_url", "config"):
                val = srv.get(col)
                if val is not None:
                    sets.append(f"{col} = ${i}")
                    vals.append(val)
                    i += 1
            sets.append(f"enabled = ${i}")
            vals.append(srv.get("enabled", True))
            i += 1
            if sets:
                sets.append("updated_at = NOW()")
                vals.append(existing["id"])
                await db.execute(
                    f"UPDATE mcp_configs SET {', '.join(sets)} WHERE id = ${i}",
                    *vals,
                )
        else:
            await db.execute(
                "INSERT INTO mcp_configs (name, display_name, description, category, server_type, server_url, enabled, config) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                srv["name"], srv.get("display_name", srv["name"]), srv.get("description"),
                srv.get("category", "custom"), srv.get("server_type", "command"),
                srv.get("server_url", ""), srv.get("enabled", True), srv.get("config"),
            )

    # Delete servers in DB not in file
    existing_rows = await db.fetch("SELECT name FROM mcp_configs")
    for row in existing_rows:
        if row["name"] not in names_in_file:
            await db.execute("DELETE FROM mcp_configs WHERE name = $1", row["name"])

    logger.info("Synced MCP config to DB: %d servers", len(servers))
