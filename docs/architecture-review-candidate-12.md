# Candidate 12: Consolidate 3+ storage backends behind a unified data access layer

**Strength**: Worth exploring | **Category**: data architecture / persistence

---

## Research sources (10)

### Agent harness storage patterns

1. **Hermes Agent** — Single SQLite database (`~/.hermes/state.db`) for session metadata, full message history, and model configuration. One storage backend, one `hermes_state.py` access module. https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage

2. **Pantheon (r3moteBee)** — Single `data/` directory with SQLite DBs, ChromaDB, workspaces. One storage directory, one access pattern. Data directory is clearly separated from source code. https://github.com/r3moteBee/pantheon

3. **OpenCode** — SQLite via `internal/db` module. Single database for all persistence. One access module, one migration path. https://github.com/opencode-ai/opencode

4. **paddo.dev — "agents need external memory"** — "The core insight: agents need external memory to work on real projects. The harness is the bridge between stateless AI and stateful work." One storage abstraction, not multiple ad-hoc backends. https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

5. **SQLAlchemy ORM pattern** — Define models, use the unit of work pattern, let the ORM handle query generation. This codebase defines `Base` in `persistence/base.py` but no models inherit from it. https://docs.sqlalchemy.org/en/20/orm/

6. **Repository pattern (Martin Fowler)** — "Mediates between the domain and data mapping layers using a collection-like interface for accessing domain objects." This codebase has no repository layer — services call `db.fetch()` directly. https://martinfowler.com/eaaCatalog/repository.html

7. **Migration-driven schema management** — Alembic migrations track schema changes. This codebase has `persistence/migrations/` but the schema is also implicitly defined by raw SQL in 30+ service files.

8. **CQRS pattern** — Command/query separation. This codebase mixes reads and writes in the same service methods with no separation.

9. **Codebase audit — ORM defined but unused, 30+ raw SQL service files** (see below)

10. **CONTEXT.md — Database** — "PostgreSQL as the single data store" is stated, but code also uses SQLite (harness_data.db), file storage (sandbox snapshots, JSON configs), and in-memory stores. The stated single data store is not the actual single data store.

---

## Codebase evidence

### The ORM that exists but isn't used

```
persistence/base.py — defines SQLAlchemy DeclarativeBase (10 lines)
persistence/migrations/ — Alembic migration directory
```

But search for `from harness.persistence.base import Base` or SQLAlchemy model definitions: **zero ORM models found**. Every service uses raw SQL via `db.fetch()` / `db.execute()`.

### 3+ storage backends in use

| Backend | What's stored | Access pattern |
|---|---|---|
| **PostgreSQL** | Sessions, messages, jobs, providers, results, configs | Raw SQL via asyncpg (30+ service files) |
| **SQLite** | `harness_data.db` (referenced in docker-compose.yml) | Raw SQL via aiosqlite |
| **File system** | Sandbox snapshots, `.testai/` config, JSON files, coverage reports | `open()`, `json.load()` |
| **In-memory** | SSE queues, event bus subscriptions, caches | Python dicts, lists |
| **Docker volumes** | Sandbox workspaces (`testai-ws-*`) | Docker CLI |

### The pattern duplication

Each service that accesses the database duplicates:

| Concern | services/settings_service.py | services/cost_service.py | Orphaned module (C4) |
|---|---|---|---|
| Query pattern | `await db.fetch(...)` | `await db.fetch(...)` | `await db.fetch(...)` |
| Error handling | try/except per method | try/except per method | try/except per method |
| JSON serialization | `json.dumps()` inline | — | `json.dumps()` inline |
| Table names | Hardcoded string | Hardcoded string | Hardcoded string |

30+ files all write the same `await db.fetch("SELECT ...", $1, $2)` pattern with no shared data access layer, no type safety, no query building, no migration-aware schema resolution.

### The contraction

Define ORM models for the 12 core tables (providers, mcp_configs, sessions, messages, jobs, test_results, flaky_tests, coverage_reports, budgets, webhook_configs, integration_configs, pipeline_runs). Create a `DataAccess` class that wraps common query patterns with type-safe methods. Service files call `DataAccess.get_providers()` instead of `await db.fetch("SELECT ...")`.

This eliminates 30+ duplicate `await db.fetch(...)` patterns, adds type safety, makes the schema explicit (instead of implicit in raw SQL strings), and enables query reuse across the application.
