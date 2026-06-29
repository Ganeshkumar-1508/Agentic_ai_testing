"""TestAI slash commands.

Each command is defined as a SlashCommand instance and registered
with register(). Follows Claude Code's pattern:
  - local: side effect, returns text. Model never sees it.
  - prompt: generates content for the model (via kwargs).

All handler functions are defined first, then commands are registered
at the bottom so definition order doesn't matter.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.chat.slash_base import SlashCommand, register, list_all

logger = logging.getLogger(__name__)


# ── Handler: /help ───────────────────────────────────────────────────

def _handle_help(args: str = "", **kw: Any) -> str:
    cmds = list_all()
    lines = ["## Slash Commands\n"]
    for c in cmds:
        alias_str = f" ({', '.join(c['aliases'])})" if c['aliases'] else ""
        flavor_mark = "⚡" if c['flavor'] == "prompt" else " "
        lines.append(f"- {flavor_mark} **/{c['name']}**{alias_str} — {c['description']}")
    return "\n".join(lines)


# ── Handler: /status ─────────────────────────────────────────────────

async def _handle_status(args: str = "", **kw: Any) -> str:
    session_id = kw.get("session_id", "")
    parts = ["## Status\n"]
    if session_id:
        parts.append(f"- **Session**: `{session_id[:12]}...`")
    try:
        from harness.api.state import get_agent
        agent = get_agent()
        if agent:
            summary = agent.get_activity_summary()
            parts.append(f"- **Agent**: {'running' if summary.get('current_tool') else 'idle'}")
            parts.append(f"- **API calls**: {summary.get('api_call_count', 0)}")
            parts.append(f"- **Max iterations**: {summary.get('max_iterations', 0)}")
    except Exception:
        parts.append("- **Agent**: unavailable")
    return "\n".join(parts)


# ── Handler: /models ─────────────────────────────────────────────────

async def _handle_models(args: str = "", **kw: Any) -> str:
    try:
        from harness.api.state import get_llm
        llm = get_llm()
        if llm is None:
            return "LLM router not initialized."
        status = llm.get_status()
        if not status:
            return "No providers configured."
        lines = ["## Configured Providers\n"]
        for p in status:
            icon = "✅" if p.get("has_key") else "❌"
            lines.append(f"- {icon} **{p.get('provider', '?')}** — {p.get('model', 'no model')}")
            if p.get("base_url"):
                lines.append(f"  `{p['base_url']}`")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /memory ─────────────────────────────────────────────────

async def _handle_memory(args: str = "", **kw: Any) -> str:
    session_id = kw.get("session_id", "")
    if not session_id:
        return "No active session."
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db is None:
            return "Database not available."
        row = await db.fetchrow(
            "SELECT COUNT(*) as cnt FROM stream_events WHERE session_id = $1",
            session_id,
        )
        msg_count = row["cnt"] if row else 0
        tok_row = await db.fetchrow(
            "SELECT total_tokens, total_cost FROM sessions WHERE id = $1",
            session_id,
        )
        tokens = tok_row["total_tokens"] if tok_row else 0
        cost = tok_row["total_cost"] if tok_row else 0.0
        return (
            f"## Memory\n"
            f"- **Messages**: {msg_count:,}\n"
            f"- **Tokens**: {tokens:,}\n"
            f"- **Cost**: ${cost:.4f}"
        )
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /cost (prompt flavor) ───────────────────────────────────

async def _handle_cost(args: str = "", **kw: Any) -> str:
    session_id = kw.get("session_id", "")
    if not session_id:
        return "No active session."
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db is None:
            return "Database not available."
        row = await db.fetchrow(
            "SELECT total_tokens, total_cost FROM sessions WHERE id = $1",
            session_id,
        )
        if not row:
            return "No cost data for this session."
        usage = await db.fetch(
            "SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(estimated_cost_usd) as cost "
            "FROM token_usage WHERE session_id = $1 GROUP BY model",
            session_id,
        )
        lines = [f"## Cost Breakdown\n"]
        lines.append(f"**Total**: ${float(row['total_cost'] or 0):.4f} ({row['total_tokens'] or 0} tokens)\n")
        if usage:
            lines.append("| Model | Input | Output | Cost |")
            lines.append("|-------|-------|--------|------|")
            for u in usage:
                lines.append(f"| {u['model'] or '?'} | {u['inp'] or 0:,} | {u['out'] or 0:,} | ${float(u['cost'] or 0):.4f} |")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /sessions (browse past sessions) ────────────────────────

async def _handle_sessions(args: str = "", **kw: Any) -> str:
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db is None:
            return "Database not available."
        rows = await db.fetch(
            "SELECT id, goal, status, created_at, total_tokens "
            "FROM sessions ORDER BY created_at DESC LIMIT 10"
        )
        if not rows:
            return "No past sessions."
        lines = ["## Recent Sessions\n"]
        for r in rows:
            sid = r['id'][:12] if r['id'] else '?'
            goal = (r['goal'] or 'No goal')[:60]
            tokens = r['total_tokens'] or 0
            lines.append(f"- `{sid}` {goal} [{r['status']}] ({tokens:,} tokens)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /skills (list available skills) ─────────────────────────

def _handle_skills(args: str = "", **kw: Any) -> str:
    try:
        from harness.tools.skill_tools import _scan_skills
        skills = _scan_skills()
        if not skills:
            return "No skills found."
        lines = ["## Available Skills\n"]
        for s in skills:
            lines.append(f"- **{s['name']}** v{s.get('version', '?')} — {s.get('description', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /tools (list available tools) ───────────────────────────

def _handle_tools(args: str = "", **kw: Any) -> str:
    try:
        from harness.tools.registry import registry
        registry.discover_tools()
        entries = registry.list_entries()
        if not entries:
            return "No tools registered."
        # Group by toolset
        by_toolset: dict[str, list[str]] = {}
        for e in entries:
            ts = e.toolset or "other"
            by_toolset.setdefault(ts, []).append(e.name)
        lines = ["## Available Tools\n"]
        for ts in sorted(by_toolset):
            tools = sorted(by_toolset[ts])
            lines.append(f"\n**{ts}** ({len(tools)} tools):")
            # Show first 10 tools per toolset
            for t in tools[:10]:
                lines.append(f"  - `{t}`")
            if len(tools) > 10:
                lines.append(f"  ... and {len(tools) - 10} more")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /retry (retry last message) ─────────────────────────────

async def _handle_retry(args: str = "", **kw: Any) -> str:
    return "Retry not yet implemented in the web chat. Please re-submit your message."


# ── Handler: /model (switch model) ───────────────────────────────────

async def _handle_model(args: str = "", **kw: Any) -> str:
    if not args:
        return "Usage: /model <model-name>. Use /models to see available models."
    return f"Model switching not yet implemented in web chat. Requested: {args}. Use Settings → LLM Providers to change the default model."


# ── Handler: /usage (token usage and limits) ─────────────────────────

async def _handle_usage(args: str = "", **kw: Any) -> str:
    session_id = kw.get("session_id", "")
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db is None:
            return "Database not available."
        lines = ["## Usage\n"]
        if session_id:
            row = await db.fetchrow(
                "SELECT total_tokens, total_cost FROM sessions WHERE id = $1",
                session_id,
            )
            if row:
                lines.append(f"**This session**: {row['total_tokens']:,} tokens, ${float(row['total_cost'] or 0):.4f}")
        # Provider health
        try:
            from harness.api.state import get_llm
            llm = get_llm()
            if llm:
                health = llm.get_provider_health()
                if health:
                    lines.append(f"\n**Provider Health**: {len(health)} models tracked")
                    for model, h in list(health.items())[:5]:
                        calls = h.get('calls', 0)
                        if calls:
                            sr = h.get('successes', 0) / calls * 100
                            lines.append(f"  - {model}: {sr:.0f}% success ({calls} calls)")
        except Exception:
            pass
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /config (show current config summary) ───────────────────

def _handle_config(args: str = "", **kw: Any) -> str:
    try:
        from harness.tools.toolsets import resolve_toolsets
        lines = ["## Configuration\n"]
        # Provider count
        from harness.providers import list_providers
        providers = list_providers()
        lines.append(f"- **Providers**: {len(providers)} available")
        # Tool count
        from harness.tools.registry import registry
        registry.discover_tools()
        entries = registry.list_entries()
        lines.append(f"- **Tools**: {len(entries)} registered")
        # Toolsets
        from harness.tools.toolsets import TOOLSETS
        lines.append(f"- **Toolsets**: {len(TOOLSETS)} defined")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /version ────────────────────────────────────────────────

def _handle_version(args: str = "", **kw: Any) -> str:
    return "TestAI Harness v0.4 — 116 tools, 42 providers, 10 slash commands"


# ── Handler: /plugins (list plugins) ─────────────────────────────────

def _handle_plugins(args: str = "", **kw: Any) -> str:
    try:
        from harness._hook_system import get_hook_registry, VALID_HOOKS
        reg = get_hook_registry()
        lines = ["## Plugins & Hooks\n"]
        from harness.hook.phases import ALL_EVENTS
        lines.append(f"- **Pipeline events**: {len(ALL_EVENTS)} lifecycle events")
        lines.append(f"- **Plugin hooks**: {len(VALID_HOOKS)} hook points")
        from harness.hook.registry import get_registry as get_pipeline_registry
        pipeline = get_pipeline_registry()
        handlers = pipeline.list_handlers()
        if handlers:
            by_event: dict[str, int] = {}
            for h in handlers:
                ev = h.get('event', '?')
                by_event[ev] = by_event.get(ev, 0) + 1
            lines.append(f"- **Active handlers**: {len(handlers)} across {len(by_event)} events")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Handler: /kanban (list kanban boards) ────────────────────────────

async def _handle_kanban(args: str = "", **kw: Any) -> str:
    try:
        from harness.memory.db_context import get_db
        db = get_db()
        if db is None:
            return "Database not available."
        rows = await db.fetch(
            "SELECT id, name, status, created_at FROM kanban_boards "
            "ORDER BY created_at DESC LIMIT 10"
        )
        if not rows:
            return "No kanban boards found."
        lines = ["## Kanban Boards\n"]
        for r in rows:
            lines.append(f"- **{r.get('name', r['id'][:12])}** [{r['status']}]")
        return "\n".join(lines)
    except Exception:
        return "No kanban boards found."


# ── Handler: /compress (manual compression) ──────────────────────────

async def _handle_compress(args: str = "", **kw: Any) -> str:
    return "Manual compression is automatic — the system compresses context when token thresholds are exceeded. Use /status to see current token usage."


# ── Register all commands ────────────────────────────────────────────

register(SlashCommand("help", "Show available slash commands", aliases=("h",)).handler(_handle_help))
register(SlashCommand("status", "Show current session and agent status", aliases=("s", "st")).handler(_handle_status))
register(SlashCommand("models", "Show available LLM models and providers").handler(_handle_models))
register(SlashCommand("model", "Switch the active model").handler(_handle_model))
register(SlashCommand("memory", "Show agent memory usage for this session", aliases=("mem",)).handler(_handle_memory))
register(SlashCommand("cost", "Show detailed cost breakdown for this session", aliases=("pricing",), flavor="prompt").handler(_handle_cost))
register(SlashCommand("usage", "Show token usage and provider health").handler(_handle_usage))
register(SlashCommand("sessions", "Browse past sessions", aliases=("history", "past")).handler(_handle_sessions))
register(SlashCommand("skills", "List available skills").handler(_handle_skills))
register(SlashCommand("tools", "List available tools and their counts").handler(_handle_tools))
register(SlashCommand("plugins", "List registered hook plugins").handler(_handle_plugins))
register(SlashCommand("retry", "Retry the last message").handler(_handle_retry))
register(SlashCommand("config", "Show system configuration summary").handler(_handle_config))
register(SlashCommand("version", "Show TestAI harness version", aliases=("v",)).handler(_handle_version))
register(SlashCommand("kanban", "List active kanban boards").handler(_handle_kanban))
register(SlashCommand("compress", "Trigger manual context compression").handler(_handle_compress))


__all__ = ["register", "SlashCommand"]
