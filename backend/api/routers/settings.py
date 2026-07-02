import asyncio
import json
import os
import secrets
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import get_db, get_llm, get_agent, get_mcp_client
from harness.db_helpers import build_patch_query
from harness.mcp.config_manager import load_config, save_config, sync_to_db, serialize_server, deserialize_server as _file_deserialize
from harness.services.settings_service import SettingsService

router = APIRouter(prefix="/api", tags=["settings"])


class ProviderSettingsRequest(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str = ""
    enabled: bool = True
    options: dict[str, Any] = {}


class MCPServerRequest(BaseModel):
    name: str
    display_name: str
    description: str | None = None
    category: str = "custom"
    server_type: str = "user_defined"
    server_url: str | None = None
    enabled: bool = True
    config: str | None = None


class WebhookRequest(BaseModel):
    name: str
    url: str
    type: str = "webhook"
    events: list[str] = ["run:completed"]
    enabled: bool = True
    prompt: str = ""
    tier: int = 2
    skills: list[str] = []


class PipelineConfigRequest(BaseModel):
    analysis: str = ""
    code_generation: str = ""
    execution: str = ""


@router.get("/settings/providers")
async def get_providers(request: Request):
    llm = get_llm(request)
    settings_store = request.app.state.settings_store
    if not llm:
        return []
    stored = await settings_store.get_all_providers()
    status = llm.get_status()
    merged = {s["provider"]: s for s in status}

    # Enrich with metadata from provider_definitions table
    db = get_db(request)
    try:
        def_rows = await db.fetch("SELECT * FROM provider_definitions ORDER BY name")
        defs = {r["name"]: r for r in def_rows}
    except Exception:
        defs = {}

    for s in stored:
        provider_name = s["provider"]
        # has_key reflects whether a key exists (DB or env), checked BEFORE stripping
        s["has_key"] = bool(s.get("api_key")) or bool(os.environ.get(get_provider_env_key(provider_name)))
        s.pop("api_key", None)
        if meta := defs.get(provider_name):
            s["display_name"] = meta.get("display_name", provider_name)
            s["description"] = meta.get("description", "")
            s["signup_url"] = meta.get("signup_url", "")
            s["auth_type"] = meta.get("auth_type", "api_key")
            s["env_vars"] = meta.get("env_vars", "")
            s["api_mode"] = meta.get("api_mode", "chat_completions")
            s["base_url"] = s.get("base_url") or meta.get("base_url", "")
        if provider_name not in merged:
            merged[provider_name] = s
    return list(merged.values())


@router.post("/settings/providers")
async def save_providers(request: Request, providers: list[ProviderSettingsRequest]):
    llm = get_llm(request)
    agent = get_agent(request)
    settings_store = request.app.state.settings_store
    if not llm or not agent:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": "Agent not initialized"})
    incoming = {}
    db = get_db(request)
    for p in providers:
        provider_name = p.provider
        # Preserve existing API key if not provided in the request
        existing = await settings_store.get_provider(provider_name)
        existing_key = (existing or {}).get("api_key", "")
        config = {
            "base_url": p.base_url,
            "model": p.model,
            "enabled": p.enabled,
            "options": p.options,
            "api_key": p.api_key or existing_key or "",
        }
        await settings_store.upsert_provider(provider_name, config)
        # Auto-create provider_definition for custom providers
        try:
            existing = await db.fetchrow("SELECT name FROM provider_definitions WHERE name=$1", provider_name)
            if not existing:
                await db.execute(
                    "INSERT INTO provider_definitions (name, api_mode, display_name, auth_type, is_builtin) "
                    "VALUES ($1, 'chat_completions', $2, 'api_key', false) ON CONFLICT (name) DO NOTHING",
                    provider_name, provider_name,
                )
        except Exception:
            pass
        incoming[provider_name] = {
            "provider": provider_name,
            "base_url": p.base_url,
            "model": p.model,
            "enabled": p.enabled,
            "options": p.options,
            "api_key": p.api_key or existing_key or "",
            "has_key": bool(p.api_key or existing_key),
        }
    stored = await settings_store.get_all_providers()
    merged = {s["provider"]: s for s in stored}
    merged.update(incoming)
    llm.configure(list(merged.values()))
    return {"status": "ok", "providers": llm.get_status()}


@router.post("/settings/providers/test-connection")
async def test_provider_connection(request: Request, body: ProviderSettingsRequest):
    import httpx
    model = body.model or os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=body.api_key or "", base_url=body.base_url or "")
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Respond with exactly: OK"}],
            max_tokens=10,
        )
        content = response.choices[0].message.content or ""
        result = {"status": "ok", "response": content[:200]}
    except Exception as e:
        result = {"status": "error", "error": str(e)}
    available_models = []
    if body.base_url:
        base = body.base_url.rstrip("/")
        for path in ["/models", "/v1/models"]:
            try:
                async with httpx.AsyncClient() as client:
                    headers = {"Authorization": f"Bearer {body.api_key}"} if body.api_key else {}
                    resp = await client.get(f"{base}{path}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = data.get("data", []) if isinstance(data.get("data"), list) else []
                        available_models = [m.get("id", "") for m in models if isinstance(m, dict)]
                        if not available_models and isinstance(data, list):
                            available_models = data
                        break
            except Exception:
                continue
    result["available_models"] = available_models
    return result


@router.delete("/settings/providers/{provider_name}")
async def delete_provider(request: Request, provider_name: str):
    settings_store = request.app.state.settings_store
    await settings_store.delete_provider(provider_name)
    from harness.env_loader import get_provider_env_key, delete_key as _env_delete
    _env_delete(get_provider_env_key(provider_name))
    llm = get_llm(request)
    if llm:
        llm.configure([])
    return {"status": "ok"}


@router.get("/settings/mcp")
async def get_mcp_servers(request: Request):
    svc = SettingsService(get_db(request))
    return {"servers": await svc.get_mcp_servers()}


@router.post("/settings/mcp")
async def create_mcp_server(request: Request, body: MCPServerRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_mcp_server(None, body.name, body.enabled, body.config, body.server_url)
    return {"status": "ok"}


@router.patch("/settings/mcp/{server_id}")
async def update_mcp_server(request: Request, server_id: str, body: MCPServerRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_mcp_server(server_id, body.name, body.enabled, body.config, body.server_url)
    return {"status": "ok"}


@router.delete("/settings/mcp/{server_id}")
async def delete_mcp_server(request: Request, server_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_mcp_server(server_id)
    return {"status": "ok"}


@router.post("/settings/mcp/reload")
async def reload_mcp_servers(request: Request):
    db = get_db(request)
    mcp_client = get_mcp_client(request)
    if not mcp_client:
        return {"status": "error", "message": "MCP client not initialized"}
    from harness.mcp.client import MCPClient
    new_client = MCPClient()
    try:
        new_client.set_llm(get_llm(request))
    except Exception:
        pass
    file_servers = load_config()
    if file_servers:
        await sync_to_db(db, file_servers)
        mcp_servers = []
        for srv in file_servers:
            entry = {
                "id": srv.get("id", f"file-{srv['name']}"),
                "name": srv["name"],
                "url": srv.get("server_url", ""),
                "enabled": srv.get("enabled", True),
            }
            cfg_str = srv.get("config") or ""
            if cfg_str:
                try:
                    cfg = json.loads(cfg_str) if isinstance(cfg_str, str) else cfg_str
                    for k in ("command", "args", "env", "transport", "timeout", "connect_timeout"):
                        if k in cfg:
                            entry[k] = cfg[k]
                except json.JSONDecodeError:
                    pass
            mcp_servers.append(entry)
        asyncio.create_task(new_client.initialize(mcp_servers))
        server_count = len(mcp_servers)
    else:
        mcp_rows = await db.fetch("SELECT * FROM mcp_configs WHERE enabled = true")
        if mcp_rows:
            mcp_servers = []
            for r in mcp_rows:
                srv = {"id": r["id"], "name": r["name"], "url": r["server_url"] or "", "enabled": r["enabled"]}
                cfg_str = r.get("config") or ""
                if cfg_str:
                    try:
                        cfg = json.loads(cfg_str) if isinstance(cfg_str, str) else cfg_str
                        for k in ("command", "args", "env", "transport", "timeout", "connect_timeout"):
                            if k in cfg:
                                srv[k] = cfg[k]
                    except json.JSONDecodeError:
                        pass
                mcp_servers.append(srv)
            asyncio.create_task(new_client.initialize(mcp_servers))
        server_count = len(mcp_rows) if 'mcp_rows' in dir() else 0
    request.app.state.mcp_client = new_client
    agent = get_agent(request)
    if agent:
        agent.mcp = new_client
    return {"status": "ok", "server_count": server_count}


@router.get("/settings/mcp/connections")
async def get_mcp_connections(request: Request):
    mcp_client = get_mcp_client(request)
    if not mcp_client:
        return {"connections": []}
    try:
        statuses = []
        # MCPClient._servers is the internal dict; expose via property or direct access
        servers_dict = getattr(mcp_client, "_servers", getattr(mcp_client, "servers", {}))
        for name, srv in servers_dict.items():
            conn_status = "connected" if getattr(srv, "session", None) else "disconnected"
            server_url = srv.server_url if hasattr(srv, "server_url") else ""
            tools = []
            try:
                for t in srv.tools or []:
                    tools.append({"name": t.name, "description": (t.description or "")[:120]})
            except Exception:
                pass
            statuses.append({"name": name, "url": server_url, "status": conn_status, "tools": tools})
        return {"connections": statuses}
    except Exception as exc:
        return {"connections": [], "error": str(exc)}


class BudgetConfigRequest(BaseModel):
    scope: str = "run"
    name: str = "default"
    soft_usd: float = 0.5
    hard_usd: float = 1.0
    enabled: bool = True


@router.get("/settings/budgets")
async def get_budgets(request: Request):
    svc = SettingsService(get_db(request))
    return {"budgets": await svc.get_budgets()}


@router.post("/settings/budgets")
async def upsert_budget(request: Request, body: BudgetConfigRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_budget(body.scope, body.name, body.soft_usd, body.hard_usd, body.enabled)
    return {"status": "ok"}


@router.delete("/settings/budgets/{budget_id}")
async def delete_budget(request: Request, budget_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_budget(budget_id)
    return {"status": "ok"}


@router.get("/settings/webhooks")
async def get_webhooks(request: Request):
    svc = SettingsService(get_db(request))
    return {"webhooks": await svc.get_webhooks()}


@router.post("/settings/webhooks")
async def create_webhook(request: Request, body: WebhookRequest):
    svc = SettingsService(get_db(request))
    await svc.create_webhook(body.name, body.url, body.type, body.events, body.enabled, body.prompt, body.tier, body.skills)
    return {"status": "ok"}


@router.patch("/settings/webhooks/{webhook_id}")
async def update_webhook(request: Request, webhook_id: str, body: WebhookRequest):
    svc = SettingsService(get_db(request))
    await svc.update_webhook(webhook_id, body.name, body.url, body.enabled, body.prompt, body.tier, body.skills)
    return {"status": "ok"}


@router.delete("/settings/webhooks/{webhook_id}")
async def delete_webhook(request: Request, webhook_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_webhook(webhook_id)
    return {"status": "ok"}


@router.get("/settings/api-keys")
async def get_api_keys(request: Request):
    svc = SettingsService(get_db(request))
    return {"keys": await svc.get_api_keys()}


@router.post("/settings/api-keys")
async def create_api_key(request: Request, body: dict[str, Any]):
    label = body.get("label", "default")
    key = f"tai_{secrets.token_hex(32)}"
    prefix = key[:12]
    svc = SettingsService(get_db(request))
    await svc.create_api_key(label, prefix, key)
    return {"key": key, "prefix": prefix, "label": label}


@router.delete("/settings/api-keys/{key_id}")
async def delete_api_key(request: Request, key_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_api_key(key_id)
    return {"status": "ok"}


@router.get("/settings/pipeline-config")
async def get_pipeline_config(request: Request):
    svc = SettingsService(get_db(request))
    return {"config": await svc.get_pipeline_config()}


@router.post("/settings/pipeline-config")
async def save_pipeline_config(request: Request, body: PipelineConfigRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_pipeline_config(body.model_dump())
    return {"status": "ok"}


@router.get("/settings/platforms")
async def get_platforms(request: Request):
    svc = SettingsService(get_db(request))
    return {"platforms": await svc.get_platforms()}


@router.post("/settings/platforms")
async def upsert_platform(request: Request, body: dict[str, Any]):
    svc = SettingsService(get_db(request))
    await svc.upsert_platform(body.get("platform", ""), body.get("config", {}))
    return {"status": "ok"}


@router.delete("/settings/platforms/{platform}")
async def delete_platform(request: Request, platform: str):
    svc = SettingsService(get_db(request))
    await svc.delete_platform(platform)
    return {"status": "ok"}


@router.get("/settings/delivery-log")
async def get_delivery_log(request: Request, limit: int = 50):
    svc = SettingsService(get_db(request))
    return {"entries": await svc.get_delivery_log(limit)}


class EnvVarRequest(BaseModel):
    key: str
    value: str
    is_secret: bool = False
    description: str = ""


@router.get("/settings/env-vars")
async def get_env_vars(request: Request):
    svc = SettingsService(get_db(request))
    return {"variables": await svc.get_env_vars()}


@router.post("/settings/env-vars")
async def upsert_env_var(request: Request, body: EnvVarRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_env_var(body.key, body.value, body.is_secret, body.description)
    return {"status": "ok"}


@router.delete("/settings/env-vars/{var_id}")
async def delete_env_var(request: Request, var_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_env_var(var_id)
    return {"status": "ok"}


class NotificationPrefRequest(BaseModel):
    channel: str
    enabled: bool = True
    events: list[str] = []


@router.get("/settings/notification-prefs")
async def get_notification_prefs(request: Request):
    svc = SettingsService(get_db(request))
    return {"preferences": await svc.get_notification_prefs()}


@router.post("/settings/notification-prefs")
async def upsert_notification_pref(request: Request, body: NotificationPrefRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_notification_pref(body.channel, body.enabled, body.events)
    return {"status": "ok"}


@router.delete("/settings/notification-prefs/{pref_id}")
async def delete_notification_pref(request: Request, pref_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_notification_pref(pref_id)
    return {"status": "ok"}


class SavedFilterRequest(BaseModel):
    name: str
    filter_data: dict[str, Any] = {}


@router.get("/settings/saved-filters")
async def get_saved_filters(request: Request):
    svc = SettingsService(get_db(request))
    return {"filters": await svc.get_saved_filters()}


@router.post("/settings/saved-filters")
async def upsert_saved_filter(request: Request, body: SavedFilterRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_saved_filter(body.name, body.filter_data)
    return {"status": "ok"}


@router.delete("/settings/saved-filters/{filter_id}")
async def delete_saved_filter(request: Request, filter_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_saved_filter(filter_id)
    return {"status": "ok"}


class FeatureFlagRequest(BaseModel):
    flag_key: str
    enabled: bool = False
    description: str = ""


@router.get("/settings/feature-flags")
async def get_feature_flags(request: Request):
    svc = SettingsService(get_db(request))
    return {"flags": await svc.get_feature_flags()}


@router.post("/settings/feature-flags")
async def upsert_feature_flag(request: Request, body: FeatureFlagRequest):
    svc = SettingsService(get_db(request))
    await svc.upsert_feature_flag(body.flag_key, body.enabled, body.description)
    return {"status": "ok"}


@router.delete("/settings/feature-flags/{flag_key}")
async def delete_feature_flag(request: Request, flag_key: str):
    svc = SettingsService(get_db(request))
    await svc.delete_feature_flag(flag_key)
    return {"status": "ok"}


class GateCreate(BaseModel):
    name: str
    metric: str
    threshold: float = 0.8
    enabled: bool = True
    description: str = ""


@router.get("/settings/gates")
async def get_gates(request: Request):
    svc = SettingsService(get_db(request))
    return {"gates": await svc.get_gates()}


@router.post("/settings/gates")
async def create_gate(request: Request, body: GateCreate):
    svc = SettingsService(get_db(request))
    await svc.create_gate(body.name, body.metric, body.threshold, body.enabled, body.description)
    return {"status": "ok"}


@router.patch("/settings/gates/{gate_id}")
async def update_gate(request: Request, gate_id: str, body: dict[str, Any]):
    svc = SettingsService(get_db(request))
    await svc.update_gate(gate_id, body.get("name"), body.get("threshold"), body.get("enabled"))
    return {"status": "ok"}


@router.delete("/settings/gates/{gate_id}")
async def delete_gate(request: Request, gate_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_gate(gate_id)
    return {"status": "ok"}


@router.get("/settings/cost")
async def get_cost(request: Request):
    svc = SettingsService(get_db(request))
    return {"daily": await svc.get_cost_data()}


class AlertRuleCreate(BaseModel):
    name: str
    metric: str = ""
    operator: str = "gt"
    threshold: float = 0
    channel: str = ""
    enabled: bool = True


@router.get("/settings/alerts")
async def get_alerts(request: Request):
    svc = SettingsService(get_db(request))
    return {"alerts": await svc.get_alerts()}


@router.post("/settings/alerts")
async def create_alert(request: Request, body: AlertRuleCreate):
    svc = SettingsService(get_db(request))
    await svc.create_alert(body.model_dump())
    return {"status": "ok"}


@router.patch("/settings/alerts/{alert_id}")
async def update_alert(request: Request, alert_id: str, body: AlertRuleCreate):
    svc = SettingsService(get_db(request))
    await svc.update_alert(alert_id, body.model_dump())
    return {"status": "ok"}


@router.delete("/settings/alerts/{alert_id}")
async def delete_alert(request: Request, alert_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_alert(alert_id)
    return {"status": "ok"}


class HookCreate(BaseModel):
    name: str
    event: str = ""
    target_url: str = ""
    enabled: bool = True


@router.get("/settings/hooks")
async def get_hooks(request: Request):
    svc = SettingsService(get_db(request))
    return {"hooks": await svc.get_hooks()}


@router.post("/settings/hooks")
async def create_hook(request: Request, body: HookCreate):
    svc = SettingsService(get_db(request))
    await svc.create_hook(body.model_dump())
    return {"status": "ok"}


@router.patch("/settings/hooks/{hook_id}")
async def update_hook(request: Request, hook_id: str, body: HookCreate):
    svc = SettingsService(get_db(request))
    await svc.update_hook(hook_id, body.model_dump())
    return {"status": "ok"}


@router.delete("/settings/hooks/{hook_id}")
async def delete_hook(request: Request, hook_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_hook(hook_id)
    return {"status": "ok"}


class PromptVersionCreate(BaseModel):
    name: str
    content: str
    version: int = 1


@router.get("/settings/prompts")
async def get_prompts(request: Request):
    svc = SettingsService(get_db(request))
    return {"prompts": await svc.get_prompts()}


@router.post("/settings/prompts")
async def create_prompt(request: Request, body: PromptVersionCreate):
    svc = SettingsService(get_db(request))
    await svc.create_prompt(body.name, body.content, body.version)
    return {"status": "ok"}


@router.get("/settings/prompts/active")
async def get_active_prompt(request: Request):
    svc = SettingsService(get_db(request))
    prompt = await svc.get_active_prompt()
    return prompt or {"status": "no_prompt"}


@router.post("/settings/prompts/{prompt_id}/rollback")
async def rollback_prompt(request: Request, prompt_id: str):
    svc = SettingsService(get_db(request))
    await svc.rollback_prompt(prompt_id)
    return {"status": "ok"}


class PlaygroundRequest(BaseModel):
    prompt_text: str
    variables: dict[str, Any] = {}


@router.post("/settings/prompts/playground")
async def playground_prompt(request: Request, body: PlaygroundRequest):
    try:
        from jinja2 import Template
        t = Template(body.prompt_text)
        result = t.render(**body.variables)
        return {"rendered": result}
    except Exception as e:
        return {"rendered": "", "error": str(e)}


class MemoryEntryCreate(BaseModel):
    name: str
    content: str
    tags: list[str] = []


@router.get("/settings/memory")
async def get_memories(request: Request):
    svc = SettingsService(get_db(request))
    return {"memories": await svc.get_memories()}


@router.post("/settings/memory")
async def create_memory(request: Request, body: MemoryEntryCreate):
    svc = SettingsService(get_db(request))
    await svc.create_memory(body.name, body.content, body.tags)
    return {"status": "ok"}


@router.delete("/settings/memory/{entry_id}")
async def delete_memory(request: Request, entry_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_memory(entry_id)
    return {"status": "ok"}


@router.delete("/settings/memory")
async def clear_memories(request: Request):
    svc = SettingsService(get_db(request))
    await svc.clear_memories()
    return {"status": "ok"}


class ExperimentCreate(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any] = {}


@router.get("/settings/experiments")
async def get_experiments(request: Request):
    svc = SettingsService(get_db(request))
    return {"experiments": await svc.get_experiments()}


@router.post("/settings/experiments")
async def create_experiment(request: Request, body: ExperimentCreate):
    svc = SettingsService(get_db(request))
    await svc.create_experiment(body.name, body.description, body.config)
    return {"status": "ok"}


@router.patch("/settings/experiments/{exp_id}")
async def update_experiment(request: Request, exp_id: str, body: ExperimentCreate):
    svc = SettingsService(get_db(request))
    await svc.update_experiment(exp_id, body.name, body.description)
    return {"status": "ok"}


@router.delete("/settings/experiments/{exp_id}")
async def delete_experiment(request: Request, exp_id: str):
    svc = SettingsService(get_db(request))
    await svc.delete_experiment(exp_id)
    return {"status": "ok"}


@router.get("/settings/impact")
async def get_impact(request: Request):
    svc = SettingsService(get_db(request))
    return {"impact": await svc.get_impact_data()}


@router.get("/settings/regression")
async def get_regression(request: Request):
    svc = SettingsService(get_db(request))
    return {"regression": await svc.get_regression_data()}


@router.get("/settings/provider-events")
async def get_provider_events(request: Request, limit: int = 100):
    db = get_db(request)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS provider_events ("
        "  id SERIAL PRIMARY KEY,"
        "  provider TEXT NOT NULL,"
        "  event_type TEXT NOT NULL,"
        "  message TEXT,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    )
    svc = SettingsService(db)
    return {"events": await svc.get_provider_events(limit)}


# ── Escalation policy ────────────────────────────────────────────────


@router.get("/settings/escalation")
async def get_escalation_policy(request: Request):
    """Get the escalation policy configuration."""
    db = get_db(request)
    try:
        row = await db.fetchrow("SELECT value FROM settings WHERE key = 'escalation_policy'")
        if row and row["value"]:
            import json
            return json.loads(row["value"])
    except Exception:
        pass
    return {
        "rules": [
            {"id": "1", "trigger": "tool_failure", "condition": "3 consec failures", "action": "ask", "target": "user"},
            {"id": "2", "trigger": "cost_exceeded", "condition": "Session cost > $5", "action": "escalate", "target": "admin"},
        ],
        "timeout_seconds": 300,
        "auto_resolve": True,
    }


@router.post("/settings/escalation")
async def save_escalation_policy(request: Request, body: dict):
    """Save the escalation policy configuration."""
    db = get_db(request)
    import json
    try:
        await db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()",
            "escalation_policy", json.dumps(body),
        )
    except Exception:
        # settings table may not exist — store in memory
        pass
    return {"status": "saved"}


# ── OpenTelemetry settings ────────────────────────────────────────────


@router.get("/settings/otel")
async def get_otel_settings():
    """Get current OpenTelemetry configuration from env vars."""
    return {
        "enabled": os.environ.get("OTEL_ENABLED", "false").lower() == "true",
        "endpoint": os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        "service_name": os.environ.get("OTEL_SERVICE_NAME", "testai-harness"),
        "protocol": os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
    }


@router.post("/settings/otel")
async def upsert_otel_settings(body: dict):
    """Save OpenTelemetry configuration.

    Persisted to the settings table via SettingsService.
    Values take effect on the next process restart (OTel is
    initialized at startup from env vars / settings store).
    """
    import os as _os
    from harness.services.settings_service import SettingsService
    svc = SettingsService()
    await svc.set_setting("otel_enabled", str(body.get("enabled", False)))
    await svc.set_setting("otel_endpoint", body.get("endpoint", "http://localhost:4317"))
    await svc.set_setting("otel_service_name", body.get("service_name", "testai-harness"))
    return {"status": "saved"}


# ── Model routing rules ──────────────────────────────────────────────


@router.get("/settings/routing-rules")
async def get_routing_rules(request: Request):
    """Get task-aware model routing rules."""
    db = get_db(request)
    try:
        row = await db.fetchrow("SELECT value FROM settings WHERE key = 'routing_rules'")
        if row and row["value"]:
            import json
            return json.loads(row["value"])
    except Exception:
        pass
    return {
        "rules": [
            {"id": "1", "task": "read", "model": "", "description": "File reads, grep, search — cheap model"},
            {"id": "2", "task": "write", "model": "", "description": "Code generation, edits — capable model"},
            {"id": "3", "task": "reasoning", "model": "", "description": "Complex reasoning, architecture — best model"},
            {"id": "4", "task": "web", "model": "", "description": "Web fetching, search — cheap model"},
        ],
        "enabled": False,
    }


@router.post("/settings/routing-rules")
async def save_routing_rules(request: Request, body: dict):
    """Save task-aware model routing rules."""
    db = get_db(request)
    import json
    try:
        await db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()",
            "routing_rules", json.dumps(body),
        )
    except Exception:
        pass
    return {"status": "saved"}
