# Candidate 18: Centralize configuration management — 113+ ad-hoc `os.environ` reads across 40+ files

**Strength**: Strong | **Category**: configuration architecture / cross-cutting concern

---

## Research sources (10)

### Agent harness configuration patterns

1. **OpenCode** — Single `opencode.json` configuration file. Structured schema with providers, agents, shell, MCP servers, LSP. One file, one read point, validated at startup. https://github.com/opencode-ai/opencode

2. **Hermes Agent** — `~/.hermes/config.yaml` with structured YAML configuration. `hermes_cli/config.py` loads and validates everything into typed dataclasses. No ad-hoc `os.getenv()` calls. https://github.com/NousResearch/hermes-agent

3. **OpenHands** — Config object with `.env` loading + typed settings. One way to read config. https://github.com/All-Hands-AI/OpenHands

4. **Pantheon (r3moteBee)** — Single `backend/api/env.py` for all environment config. One file. https://github.com/r3moteBee/pantheon

5. **Microsoft Agentic Harness** — `appsettings.json` for .NET configuration. Structured, typed, validated. https://github.com/mckruz/microsoft-agentic-harness

6. **12 Factor App — Config principle** — "Store config in the environment" but read it through a single well-defined point, not scattered ad-hoc. "Code of conduct for apps." https://12factor.net/config

7. **12 Factor Agents (HumanLayer)** — "Explicit prompts, state ownership, and clean pause-resume behavior." Configuration should be explicit and centralized, not implicit in 40+ files. https://www.humanlayer.dev/blog/12-factor-agents

8. **paddo.dev** — "The product abstracts the harness." A product that abstracts the harness needs a single configuration surface, not 113 scattered env var reads. https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

9. **Codebase audit — 113 `os.environ`/`os.getenv` calls across 40+ files** (see below)

10. **CONTEXT.md — env_loader** — The domain model defines `.env` file loading, but the code reads env vars directly at import time, bypassing the loader.

---

## Codebase evidence

### 113 ad-hoc environment variable reads

Every module reads its own config from `os.environ` directly:

| File | Reads |
|---|---|
| `backends/local.py` | `TESTAI_BASH_PATH`, `TESTAI_SHELL_INIT_FILES`, `TESTAI_AUTO_SOURCE_BASHRC`, `SHELL`, `ProgramFiles`, `LOCALAPPDATA` |
| `backends/docker.py` | `TESTAI_DOCKER_BINARY` |
| `subagent.py` | `SUBAGENT_RETRY_*` (3 vars), `TESTAI_SPAWN_*` (4 vars), `TESTAI_MAX_SPAWN_DEPTH` |
| `trace.py` | `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_*` (4 vars), `OTEL_SERVICE_NAME`, `OTEL_SERVICE_VERSION` |
| `coordinator_spawn.py` | `DEFAULT_MODEL`, `TESTAI_KANBAN_BOARD` |
| `llm.py` | `DEFAULT_MODEL` |
| `env_loader.py` | Manages `.env` files |
| `db_helpers.py` | `DATABASE_URL` |
| `osv_check.py` | `OSV_ENDPOINT` |
| ... 30+ more files | Various `TESTAI_*`, `ARTIFACT_*`, `HERMES_*`, `GIT*` vars |

**~40 distinct environment variables** read across **40+ files**, all via `os.environ.get("VAR")` at module level. No validation, no defaults documentation, no env var registry, no single access point.

### The config gap

Every other production harness centralizes configuration:

| Harness | Config mechanism | Files |
|---|---|---|
| OpenCode | `opencode.json` | 1 |
| Hermes Agent | `~/.hermes/config.yaml` | 1 + loader |
| OpenHands | Config object | 1 |
| Pantheon | `env.py` | 1 |
| **This project** | **Ad-hoc `os.environ`** | **40+** |

### The contraction

Define a `Settings` dataclass or Pydantic model that reads ALL env vars in one place:

```python
@dataclass
class Settings:
    testai_home: str = "/app/.testai"
    database_url: str = "postgres://postgres:postgres@localhost:5432/testai"
    default_model: str = "deepseek-v4-flash"
    otel_enabled: bool = False
    testai_docker_binary: str = ""
    testai_bash_path: str = ""
    testai_spawn_rate_limit: int = 10
    ...
```

Every module imports `settings.testai_home` instead of `os.environ.get("TESTAI_HOME", ...)`. 40+ ad-hoc reads → one `Settings` object. Validated at startup. Documented in one place. Testable.
