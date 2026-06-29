# Candidate 24: Add a `MemoryProvider` ABC for pluggable memory backends (missing from Hermes comparison)

**Strength**: New feature | **Category**: missing capability / memory architecture

---

## Research sources (10)

### Agent harness memory provider patterns

1. **Hermes Agent — `plugins/memory/<name>/`** — Pluggable memory backends behind a `MemoryProvider` ABC. Built-in providers: honcho, mem0, supermemory, byterover, hindsight, holographic, openviking, retaindb. Each implements `sync_turn()`, `prefetch()`, `shutdown()`, `post_setup()`. https://github.com/NousResearch/hermes-agent (in `reference/hermes-agent/agent/memory_provider.py`)

2. **Hermes AGENTS.md — Memory providers** — "Each provider implements the MemoryProvider ABC and is orchestrated by `agent/memory_manager.py`." Memory is a pluggable concern, not hardcoded to PostgreSQL. https://github.com/NousResearch/hermes-agent (in `reference/hermes-agent/AGENTS.md`)

3. **Pantheon — Five-tier memory** — Working (conversation), episodic (SQLite chat logs), semantic (ChromaDB embeddings), graph (concepts/relationships), archival. All five tiers are explicit. https://github.com/r3moteBee/pantheon

4. **Mem0** — Hybrid storage (Postgres + vector). Three operations: ADD, UPDATE, DELETE. Up to 26% accuracy gains. Standalone pluggable backend. https://github.com/mem0ai/mem0

5. **Letta (MemGPT)** — OS-like memory management with RAM/disk analogy. Three tiers: working context (RAM), archival storage (disk), recall (search). https://www.letta.com/blog/letta-v1-agent

6. **Zep** — Temporal memory with vector search. Pluggable backend for agent memory. https://github.com/getzep/zep

7. **Databricks Agent Memory** — Built-in memory for Databricks agent framework. Stateful agents with persistent memory. https://docs.databricks.com/aws/en/generative-ai/agent-framework/stateful-agents

8. **CONTEXT.md — memory tool** — "Three tiers: L0 raw artifacts, L1 indexed facts, L2 curated lessons." The domain model defines the tier architecture but the implementation has no pluggable backend interface.

9. **Codebase audit — memory primitives exist, no pluggable backend interface** (see below)

10. **CONTEXT.md — Agent Communication** — Internal agents communicate through shared backend. Memory should be pluggable to support different storage backends.

---

## Codebase evidence

### What exists vs what's missing

| Current memory files | Purpose | Missing for pluggability |
|---|---|---|
| `memory/store.py` (74 lines) | `PersistentStore` — key-value | Hardcoded to PostgreSQL, no ABC |
| `memory/agent_memory_store.py` | Agent-specific facts | No `MemoryProvider` interface |
| `memory/session.py` | `SessionMemory` | No abstract base class |
| `memory/database.py` | DB access | Coupled to asyncpg |
| `agent/reflexion_memory.py` | `ReflexionMemory` | Standalone, not behind an ABC |

### Hermes pattern vs this project

```python
# Hermes — pluggable via MemoryProvider ABC
class MemoryProvider(ABC):
    async def sync_turn(self, turn_messages: list) -> None: ...
    async def prefetch(self, query: str) -> list: ...
    async def shutdown(self) -> None: ...

class Mem0Provider(MemoryProvider): ...    # Plugged in
class HonchoProvider(MemoryProvider): ...  # Plugged in
class SQLiteProvider(MemoryProvider): ...  # Built-in default

# Orchestrated by MemoryManager
manager = MemoryManager()
manager.register_provider("mem0", Mem0Provider(...))
manager.register_provider("sqlite", SQLiteProvider(...))
```

```python
# This project — hardcoded
store = PersistentStore(db)  # Always PostgreSQL
memory = SessionMemory(db)   # Always same DB
reflexion = ReflexionMemory() # Standalone, no interface
```

### The contraction

Define a `MemoryProvider` ABC:
```python
class MemoryProvider(ABC):
    async def store(self, key: str, value: Any, tier: MemoryTier) -> None: ...
    async def recall(self, query: str, tier: MemoryTier) -> list: ...
    async def forget(self, key: str) -> None: ...
```

Implement built-in providers: `PostgresMemoryProvider` (existing), `SQLiteMemoryProvider` (for lightweight deployments), `ChromaDBMemoryProvider` (for semantic search). Allow third-party providers via `plugins/memory/<name>/` following the Hermes pattern. The `PersistentStore` becomes a default provider, not the only option.
