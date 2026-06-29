# Backend Infrastructure Research

**Date:** 2026-06-14  
**Sources:** Hermes Agent providers system, OpenClaude descriptor architecture, OpenHarness query engine, htek.dev harness comparison

---

## 1. Provider Descriptors (Needs Clarification)

### Current State
`backend/harness/providers/` exists but has procedural if/else chains. Adding a new provider requires editing Python code.

### Hermes Pattern (Recommended)
Declarative `ProviderProfile` dataclasses (20-60 lines each) stored in `~/.hermes/providers/`:

```python
@dataclass
class ProviderProfile:
    name: str               # "anthropic", "openai", "deepseek"
    api_format: str         # "anthropic" | "openai" | "bedrock"
    base_url: str | None    # default endpoint
    auth_type: str          # "api_key" | "oauth" | "bedrock"
    env_var: str            # env var name for API key
    models: list[ModelSpec] # available models with context windows
    fallbacks: list[str]    # fallback provider chain
```

### What it enables
- New providers = new DB row, no code changes
- Frontend can list/configure providers from API
- Transport layer reads config not if/else
- Fallback model chains per provider

### Implementation (4-6 hours)
1. Create `ProviderDescriptor` Pydantic model
2. Store in `provider_configs` table (already exists)
3. Add `GET/POST /api/settings/providers` endpoints (1 partial exists)
4. Build provider config UI in Settings page
5. Migrate LLMRouter to read from DB

---

## 2. Reactive Compaction

### Current State
`backend/harness/context_compressor/` exists but isn't wired into the agent loop.

### Industry Pattern (OpenHarness + Claude Code)
Four-layer strategy:
1. **Micro-compact** (free, before each turn if >70% context used)
2. **Auto-compact** (cheap LLM summary when approaching limit)
3. **Session memory** (persistent cross-session)
4. **Reactive compact** (on API error)

### Key: Error Detection
OpenHarness detects `prompt_too_long` with 18 error patterns across providers:
```python
ERROR_PATTERNS = [
    "context_length_exceeded", "max_tokens", "too many tokens",
    "maximum context length", "input too long", ...
]
```

### Implementation (3-4 hours)
1. Wire `context_compressor` into `agent.py` agent loop
2. Add pre-emptive micro-compact before each turn
3. Add reactive compact on context overflow error
4. Add compaction metrics to dashboard

---

## 3. JSONL Session Recording

### Current State
No session recording. Sessions are stored as chat_messages in Postgres.

### Industry Pattern (Hermes + Claude Code)
JSONL (newline-delimited JSON) files in `~/.hermes/sessions/`:
```
{"type": "session_start", "session_id": "...", "timestamp": "..."}
{"type": "user_message", "content": "...", "timestamp": "..."}
{"type": "assistant_message", "content": "...", "timestamp": "..."}
{"type": "tool_call", "name": "read_file", "arguments": {...}, "timestamp": "..."}
{"type": "tool_result", "name": "read_file", "result": "...", "timestamp": "..."}
{"type": "session_end", "session_id": "...", "timestamp": "..."}
```

### Benefits
- Fine-tuning data (ShareGPT format)
- Debugging and replay
- Separated failed vs successful runs
- 30-day auto-rotation

---

## 4. Backend API Status

| Feature | Backend Exists | API Exists | UI Exists | Effort |
|---------|---------------|------------|-----------|--------|
| Provider descriptors | Partial (`providers/` dir) | Partial (`/api/settings/providers`) | No | 4-6h |
| Reactive compaction | Yes (`context_compressor/`) | No | No | 3-4h |
| JSONL recording | No | No | No | 2-3h |
| Saved filters | DB table exists | No | No | 2h |
| Hook config | Yes (`hooks/` dir) | No | No | 3h |
| Plugin manager | Yes (`plugins/` dir) | No | No | 3h |
| Cron UI | Yes (`scheduler/` dir) | Partial (`/api/cron`) | No | 2h |
| Notifications | Yes (`notify_api.py`) | Partial | No | 1h |
| Live terminal | No | No | No | 6h |
