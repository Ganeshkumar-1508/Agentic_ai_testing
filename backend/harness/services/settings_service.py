"""Settings service — all DB queries and business logic for the settings domain.

Follows the OpenHands service layer pattern: router handles HTTP, service handles
data access and business rules. Keeps routers thin and testable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from harness.memory.database import Database


class SettingsService:
    """Data access for all settings/* resources.

    One instance per request. Accepts a Database (asyncpg connection pool)
    so it can be used both from API routers and from background tasks.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Providers ──────────────────────────────────────────────

    async def get_providers(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT provider, base_url, model, api_mode, enabled, options FROM providers ORDER BY provider"
        )
        return [dict(r) for r in rows]

    async def upsert_provider(self, provider: str, base_url: str, model: str, enabled: bool, options: dict | None) -> None:
        await self.db.execute(
            "INSERT INTO providers (provider, base_url, model, enabled, options) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (provider) DO UPDATE SET base_url=$2, model=$3, enabled=$4, options=$5",
            provider, base_url or "", model or "", enabled, json.dumps(options or {}),
        )

    async def delete_provider(self, provider: str) -> None:
        await self.db.execute("DELETE FROM providers WHERE provider = $1", provider)

    # ── MCP ────────────────────────────────────────────────────

    async def get_mcp_servers(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM mcp_configs ORDER BY name")
        return [dict(r) for r in rows]

    async def upsert_mcp_server(self, server_id: str | None, name: str, enabled: bool, config: str | None, server_url: str | None) -> None:
        if server_id:
            await self.db.execute(
                "UPDATE mcp_configs SET name=$1, display_name=$1, enabled=$2, config=$3, server_url=$4 WHERE id=$5",
                name, enabled, config or "", server_url or "", server_id,
            )
        else:
            await self.db.execute(
                "INSERT INTO mcp_configs (name, display_name, enabled, config, server_url) VALUES ($1, $1, $2, $3, $4)",
                name, enabled, config or "", server_url or "",
            )

    async def delete_mcp_server(self, server_id: str) -> None:
        await self.db.execute("DELETE FROM mcp_configs WHERE id = $1", server_id)

    # ── Budgets ────────────────────────────────────────────────

    async def get_budgets(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM budgets ORDER BY scope, name")
        return [dict(r) for r in rows]

    async def upsert_budget(self, scope: str, name: str, soft_usd: float, hard_usd: float, enabled: bool) -> None:
        await self.db.execute(
            "INSERT INTO budgets (scope, name, soft_usd, hard_usd, enabled) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (scope, name) DO UPDATE SET soft_usd=$3, hard_usd=$4, enabled=$5",
            scope, name, soft_usd, hard_usd, enabled,
        )

    async def delete_budget(self, budget_id: str) -> None:
        await self.db.execute("DELETE FROM budgets WHERE id = $1", budget_id)

    # ── Webhooks ───────────────────────────────────────────────

    async def get_webhooks(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM webhook_channels ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_webhook(self, name: str, url: str, type_: str, events: list[str], enabled: bool, prompt: str = "", tier: int = 2, skills: list[str] | None = None) -> None:
        await self.db.execute(
            "INSERT INTO webhook_channels (name, url, type, events, enabled, prompt, tier, skills) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)",
            name, url, type_, json.dumps(events), enabled, prompt, tier, json.dumps(skills or []),
        )

    async def update_webhook(self, webhook_id: str, name: str | None = None, url: str | None = None, enabled: bool | None = None, prompt: str | None = None, tier: int | None = None, skills: list[str] | None = None) -> None:
        sets: list[str] = []
        vals: list[Any] = []
        idx = 0
        if name is not None:
            idx += 1; sets.append(f"name=${idx}"); vals.append(name)
        if url is not None:
            idx += 1; sets.append(f"url=${idx}"); vals.append(url)
        if enabled is not None:
            idx += 1; sets.append(f"enabled=${idx}"); vals.append(enabled)
        if prompt is not None:
            idx += 1; sets.append(f"prompt=${idx}"); vals.append(prompt)
        if tier is not None:
            idx += 1; sets.append(f"tier=${idx}"); vals.append(tier)
        if skills is not None:
            idx += 1; sets.append(f"skills=${idx}"); vals.append(json.dumps(skills))
        if sets:
            idx += 1; vals.append(webhook_id)
            await self.db.execute(
                f"UPDATE webhook_channels SET {', '.join(sets)} WHERE id=${idx}", *vals
            )

    async def delete_webhook(self, webhook_id: str) -> None:
        await self.db.execute("DELETE FROM webhook_channels WHERE id = $1", webhook_id)

    # ── API Keys ───────────────────────────────────────────────

    async def get_api_keys(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT id, label, prefix, created_at, last_used_at FROM api_keys ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_api_key(self, label: str, prefix: str, key_hash: str) -> None:
        await self.db.execute(
            "INSERT INTO api_keys (label, prefix, key_hash) VALUES ($1, $2, $3)",
            label, prefix, key_hash,
        )

    async def delete_api_key(self, key_id: str) -> None:
        await self.db.execute("DELETE FROM api_keys WHERE id = $1", key_id)

    # ── Pipeline Config ────────────────────────────────────────

    async def get_pipeline_config(self) -> dict[str, str]:
        row = await self.db.fetchrow("SELECT config FROM pipeline_config ORDER BY created_at DESC LIMIT 1")
        if row:
            return json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
        return {}

    async def upsert_pipeline_config(self, config: dict[str, str]) -> None:
        await self.db.execute(
            "INSERT INTO pipeline_config (config) VALUES ($1)", json.dumps(config),
        )

    # ── Platforms (delivery) ───────────────────────────────────

    async def get_platforms(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM notification_delivery ORDER BY platform")
        return [dict(r) for r in rows]

    async def upsert_platform(self, platform: str, config: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO notification_delivery (platform, config) VALUES ($1, $2) "
            "ON CONFLICT (platform) DO UPDATE SET config=$2",
            platform, json.dumps(config),
        )

    async def delete_platform(self, platform: str) -> None:
        await self.db.execute("DELETE FROM notification_delivery WHERE platform = $1", platform)

    # ── Environment Variables ──────────────────────────────────

    async def get_env_vars(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM env_vars ORDER BY key")
        return [dict(r) for r in rows]

    async def upsert_env_var(self, key: str, value: str, is_secret: bool, description: str) -> None:
        await self.db.execute(
            "INSERT INTO env_vars (key, value, is_secret, description) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (key) DO UPDATE SET value=$2, is_secret=$3, description=$4",
            key, value, is_secret, description or "",
        )

    async def delete_env_var(self, var_id: str) -> None:
        await self.db.execute("DELETE FROM env_vars WHERE id = $1", var_id)

    # ── Notification Preferences ───────────────────────────────

    async def get_notification_prefs(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM notification_preferences ORDER BY channel")
        return [dict(r) for r in rows]

    async def upsert_notification_pref(self, channel: str, enabled: bool, events: list[str]) -> None:
        await self.db.execute(
            "INSERT INTO notification_preferences (channel, enabled, events) VALUES ($1, $2, $3) "
            "ON CONFLICT (channel) DO UPDATE SET enabled=$2, events=$3",
            channel, enabled, json.dumps(events),
        )

    async def delete_notification_pref(self, pref_id: str) -> None:
        await self.db.execute("DELETE FROM notification_preferences WHERE id = $1", pref_id)

    # ── Saved Filters ──────────────────────────────────────────

    async def get_saved_filters(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM saved_filters ORDER BY name")
        return [dict(r) for r in rows]

    async def upsert_saved_filter(self, name: str, filter_data: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO saved_filters (name, filter_data) VALUES ($1, $2) "
            "ON CONFLICT (name) DO UPDATE SET filter_data=$2",
            name, json.dumps(filter_data),
        )

    async def delete_saved_filter(self, filter_id: str) -> None:
        await self.db.execute("DELETE FROM saved_filters WHERE id = $1", filter_id)

    # ── Feature Flags ──────────────────────────────────────────

    async def get_feature_flags(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM feature_flags ORDER BY key")
        return [dict(r) for r in rows]

    async def upsert_feature_flag(self, flag_key: str, enabled: bool, description: str) -> None:
        await self.db.execute(
            "INSERT INTO feature_flags (key, label, enabled, description) VALUES ($1, $1, $2, $3) "
            "ON CONFLICT (key) DO UPDATE SET label=$1, enabled=$2, description=$3",
            flag_key, enabled, description or "",
        )

    async def delete_feature_flag(self, flag_key: str) -> None:
        await self.db.execute("DELETE FROM feature_flags WHERE key = $1", flag_key)

    # ── Quality Gates ──────────────────────────────────────────

    async def get_gates(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM quality_gates ORDER BY name")
        return [dict(r) for r in rows]

    async def create_gate(self, name: str, metric: str, threshold: float, enabled: bool, description: str) -> None:
        await self.db.execute(
            "INSERT INTO quality_gates (name, metric, fail_threshold, warn_threshold, enabled, description) VALUES ($1, $2, $3, $3, $4, $5)",
            name, metric, threshold, enabled, description or "",
        )

    async def update_gate(self, gate_id: str, name: str | None = None, threshold: float | None = None, enabled: bool | None = None) -> None:
        sets: list[str] = []
        vals: list[Any] = []
        idx = 1
        if name is not None:
            sets.append(f"name=${idx}")
            vals.append(name)
            idx += 1
        if threshold is not None:
            sets.append(f"fail_threshold=${idx}")
            vals.append(threshold)
            idx += 1
        if enabled is not None:
            sets.append(f"enabled=${idx}")
            vals.append(enabled)
            idx += 1
        if sets:
            vals.append(gate_id)
            await self.db.execute(f"UPDATE quality_gates SET {', '.join(sets)} WHERE id=${idx}", *vals)

    async def delete_gate(self, gate_id: str) -> None:
        await self.db.execute("DELETE FROM quality_gates WHERE id = $1", gate_id)

    # ── Cost ───────────────────────────────────────────────────

    async def get_cost_data(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT DATE(timestamp) as day, SUM(estimated_cost_usd) as cost, "
            "SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens "
            "FROM token_usage GROUP BY day ORDER BY day DESC LIMIT 90"
        )
        result = []
        for r in rows:
            d = dict(r)
            d["cost"] = float(d.get("cost", 0))
            result.append(d)
        return result

    # ── Alerts ─────────────────────────────────────────────────

    async def get_alerts(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM alert_rules ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_alert(self, rule: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO alert_rules (name, condition_type, condition_value, condition_direction, action_type, action_config, enabled) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            rule.get("name", ""), rule.get("metric", ""),
            float(rule.get("threshold", 0)), rule.get("operator", "gt"),
            rule.get("channel", ""), json.dumps(rule.get("action_config", {})),
            rule.get("enabled", True),
        )

    async def update_alert(self, alert_id: str, rule: dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE alert_rules SET name=$1, condition_type=$2, condition_value=$3, condition_direction=$4, action_type=$5, action_config=$6, enabled=$7 WHERE id=$8",
            rule.get("name", ""), rule.get("metric", ""),
            float(rule.get("threshold", 0)), rule.get("operator", "gt"),
            rule.get("channel", ""), json.dumps(rule.get("action_config", {})),
            rule.get("enabled", True), alert_id,
        )

    async def delete_alert(self, alert_id: str) -> None:
        await self.db.execute("DELETE FROM alert_rules WHERE id = $1", alert_id)

    # ── Hooks (pipeline lifecycle) ─────────────────────────────

    async def get_hooks(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM pipeline_hooks ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_hook(self, hook: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO pipeline_hooks (name, event, target_url, enabled) VALUES ($1, $2, $3, $4)",
            hook.get("name", ""), hook.get("event", ""), hook.get("target_url", ""), hook.get("enabled", True),
        )

    async def update_hook(self, hook_id: str, hook: dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE pipeline_hooks SET name=$1, event=$2, target_url=$3, enabled=$4 WHERE id=$5",
            hook.get("name", ""), hook.get("event", ""), hook.get("target_url", ""), hook.get("enabled", True), hook_id,
        )

    async def delete_hook(self, hook_id: str) -> None:
        await self.db.execute("DELETE FROM pipeline_hooks WHERE id = $1", hook_id)

    # ── Prompts ────────────────────────────────────────────────

    async def get_prompts(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM prompt_versions ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_prompt(self, name: str, content: str, version: int) -> None:
        await self.db.execute(
            "INSERT INTO prompt_versions (name, content, version) VALUES ($1, $2, $3)",
            name, content, version,
        )

    async def get_active_prompt(self) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT * FROM prompt_versions ORDER BY created_at DESC LIMIT 1"
        )
        return dict(row) if row else None

    async def rollback_prompt(self, prompt_id: str) -> None:
        row = await self.db.fetchrow("SELECT * FROM prompt_versions WHERE id = $1", prompt_id)
        if row:
            await self.db.execute(
                "INSERT INTO prompt_versions (name, content, version) VALUES ($1, $2, $3)",
                row["name"], row["content"], row["version"] + 1,
            )

    # ── Memory (settings/agent memories, not reflexion) ────────

    async def get_memories(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM agent_memories ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_memory(self, name: str, content: str, tags: list[str] | None) -> None:
        await self.db.execute(
            "INSERT INTO agent_memories (name, content, tags) VALUES ($1, $2, $3)",
            name, content, json.dumps(tags or []),
        )

    async def delete_memory(self, entry_id: str) -> None:
        await self.db.execute("DELETE FROM agent_memories WHERE id = $1", entry_id)

    async def clear_memories(self) -> None:
        await self.db.execute("DELETE FROM agent_memories")

    # ── Experiments ────────────────────────────────────────────

    async def get_experiments(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM experiments ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def create_experiment(self, name: str, description: str, config: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO experiments (name, description, control_config) VALUES ($1, $2, $3)",
            name, description or "", json.dumps(config),
        )

    async def update_experiment(self, exp_id: str, name: str | None = None, description: str | None = None, enabled: bool | None = None) -> None:
        sets: list[str] = []
        vals: list[Any] = []
        idx = 1
        if name is not None:
            sets.append(f"name=${idx}"); vals.append(name); idx += 1
        if description is not None:
            sets.append(f"description=${idx}"); vals.append(description); idx += 1
        if enabled is not None:
            sets.append(f"enabled=${idx}"); vals.append(enabled); idx += 1
        if sets:
            vals.append(exp_id)
            await self.db.execute(f"UPDATE experiments SET {', '.join(sets)} WHERE id=${idx}", *vals)

    async def delete_experiment(self, exp_id: str) -> None:
        await self.db.execute("DELETE FROM experiments WHERE id = $1", exp_id)

    # ── Impact ─────────────────────────────────────────────────

    async def get_impact_data(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM test_impact ORDER BY analyzed_at DESC LIMIT 50")
        return [dict(r) for r in rows]

    # ── Regression ─────────────────────────────────────────────

    async def get_regression_data(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM regression_data ORDER BY detected_at DESC LIMIT 50")
        return [dict(r) for r in rows]

    # ── Provider Events (failover history) ─────────────────────

    async def get_provider_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM provider_events ORDER BY created_at DESC LIMIT $1", limit,
        )
        return [dict(r) for r in rows]

    # ── Delivery Log ───────────────────────────────────────────

    async def get_delivery_log(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM delivery_log ORDER BY created_at DESC LIMIT $1", limit,
        )
        return [dict(r) for r in rows]
