# Candidate 15: Reorganise the fragmented memory system around the domain model's L0/L1/L2 tier architecture

**Strength**: Worth exploring | **Category**: memory architecture / domain model gap

---

## Research sources (10)

### Agent harness memory patterns

1. **DeerFlow** — "Long-Term Memory: builds a persistent memory of your profile, preferences, and accumulated knowledge across sessions. Memory updates skip duplicate fact entries at apply time." One coherent memory concept with dedup built in. https://github.com/bytedance/deer-flow

2. **Letta (MemGPT)** — OS-like memory management with RAM/disk analogy. Three tiers: working context (RAM), archival storage (disk), recall (search). Clear tier separation matching L0/L1/L2. https://www.letta.com/blog/letta-v1-agent

3. **Mem0** — Hybrid storage (Postgres + vector). Three operations: ADD, UPDATE, DELETE. Explicit memory tier separation. Up to 26% accuracy gains over flat memory. https://github.com/mem0ai/mem0

4. **Antropic — Effective Harnesses** — External artifacts as memory: progress files (L2 curated lessons), feature lists, git history (L0 raw artifacts), session startup protocol (L1 indexed facts). Three tiers, externalized. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

5. **Pantheon (r3moteBee)** — "Five-Tier Memory: working (in-conversation), episodic (SQLite chat logs), semantic (ChromaDB embeddings), graph (concepts and relationships), archival." Five explicit tiers, implemented. https://github.com/r3moteBee/pantheon

6. **Smolagents (HuggingFace)** — `agent.memory` is a core concept attached to the agent. Memory = chat messages, not separate subsystems. One unified interface. https://github.com/huggingface/smolagents

7. **Hermes Agent** — `~/.hermes/state.db` SQLite for all session data. One database, one access pattern, one memory concept. No fragmentation. https://github.com/NousResearch/hermes-agent

8. **Awesome Harness Engineering — Memory section** — Lists 10+ established memory patterns: Letta (tiers), Mem0 (ADD/UPDATE/DELETE), Zep (temporal), Memory Blocks (discrete units). This project follows none of them. https://github.com/Jiaaqiliu/Awesome-Harness-Engineering

9. **CONTEXT.md — memory tool** — "read and write cross-run facts. Three tiers: L0 raw artifacts, L1 indexed facts, L2 curated lessons." The domain model defines the tier architecture. The implementation ignores it.

10. **Codebase audit — 10+ memory files, empty `__init__.py`, no tier separation** (see below)

---

## Codebase evidence

### The memory ecosystem: 10+ files, no unified interface

| File | What it does | Tier (per CONTEXT.md) |
|---|---|---|
| `memory/store.py` (74 lines) | `PersistentStore` — key-value for interactions, skills | Mixed L0/L1 — no separation |
| `memory/agent_memory_store.py` (14 sym) | Agent-specific memory | L1 — but extends the flat store |
| `memory/database.py` (17 sym) | DB abstraction | Infrastructure — not memory |
| `memory/db_context.py` (6 sym) | DB context | Infrastructure |
| `memory/session.py` (8 sym) | Session state | L0 — but separate from store.py |
| `memory/settings_store.py` (10 sym) | Settings persistence | Not memory — config |
| `__init__.py` (0 lines) | **Empty** — no unified exports | — |
| `checkpoint.py` (238 lines) | Crash recovery checkpoints | L0 — but in its own file at root |
| `agent/reflexion_memory.py` (26 sym) | Agent self-improvement | L2 — but separate from memory/ |
| `l2_reflection.py` (11 sym) | L2 reflection | L2 — at root, not in memory/ |
| `services/memory_monitor.py` (19 sym) | Memory monitoring | Infrastructure |

### The domain model vs reality

CONTEXT.md says:
> **memory** — read and write cross-run facts. Three tiers: L0 raw artifacts, L1 indexed facts, L2 curated lessons.

Implementation: an empty `__init__.py`, a flat key-value `PersistentStore`, a checkpoint system at root, a reflexion memory in `agent/`, an L2 reflection at root, and a memory monitor in `services/`. No tier separation, no unified interface, no consistent access pattern.

Pantheon implements 5 explicit tiers. Letta implements 3 tiers matching L0/L1/L2. Mem0 has 3 operations (ADD/UPDATE/DELETE) across tiers. This project has the tier vocabulary in the domain model but no tier separation in code.

### The contraction

Reorganise `memory/` around the CONTEXT.md tier model:
- `memory/l0_raw/` — artifact storage, checkpoints, session logs
- `memory/l1_facts/` — indexed facts, vector store, key-value
- `memory/l2_lessons/` — curated lessons, reflexions, L2 reflections
- `memory/__init__.py` — exports a unified `Memory` interface with `.store()`, `.recall()`, `.forget()` matching Mem0's ADD/UPDATE/DELETE pattern

This makes the domain model's tier architecture real in code. `PersistentStore` gets split into L0 (session logs) and L1 (indexed facts). `checkpoint.py` moves to `memory/l0_raw/`. `reflexion_memory.py` and `l2_reflection.py` move to `memory/l2_lessons/`.
