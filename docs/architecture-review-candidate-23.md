# Candidate 23: Build an ingestion pipeline with source adapters (missing from Pantheon comparison)

**Strength**: New feature | **Category**: missing capability / content ingestion

---

## Research sources (10)

### Agent harness ingestion patterns

1. **Pantheon (r3moteBee)** — 28 built-in source adapters: YouTube, blogs, PDFs, websites, GitHub, etc. Dedicated `backend/sources/` directory with `SOURCE_ADAPTERS.md` guide for new adapters. Scheduled ingestion feeds via APScheduler. https://github.com/r3moteBee/pantheon

2. **Pantheon ingestion flow** — URL → source adapter → structured artifacts + graph nodes → memory. Each adapter fetches, parses, and extracts entities/relationships. Adapters are pluggable — one file per source type.

3. **Hermes Agent** — `web_search` + `web_extract` + `read_file` tools for ad-hoc content access. No systematic ingestion pipeline. Content is fetched per-query, not pre-ingested.

4. **OpenHands** — Agents fetch content on-demand via web tools. No pre-ingestion pipeline.

5. **Claude Code / Codex** — CLI-based, no ingestion pipeline. Content is fetched per-session.

6. **TestAI codebase — existing tools** — `WebFetchTool`, `WebSearchTool`, `WebExtractTool` for on-demand fetching. `web_fetch` in CONTEXT.md Tool Catalog. No systematic multi-source ingestion.

7. **Knowledge Graph integration** — Pantheon's ingestion feeds directly into the knowledge graph. This project's KG is built from code via `codegraph`, not from web content.

8. **Scheduled processing** — This project has `cron/` and `scheduler/` modules that could trigger periodic ingestion. Pantheon uses APScheduler for daily feed processing.

9. **CONTEXT.md — Tool Catalog** — `web_fetch` exists as a tool but there's no concept of "ingest a URL → extract → store → index."

10. **Codebase audit — no sources/ directory, no adapter base class, no ingestion pipeline** (see below)

---

## Codebase evidence

### What exists vs what's missing

| Capability | Current project | Pantheon |
|---|---|---|
| Fetch URL content | ✅ `WebFetchTool` + `WebSearchTool` | Same + built-in adapters |
| Source-type detection | ❌ No dispatch by source type | ✅ 28 adapters (YouTube, PDF, blog, GitHub, etc.) |
| Structured extraction | ❌ Raw text only | ✅ Per-adapter extraction logic |
| Artifact generation | ✅ `ArtifactSaveTool` | ✅ Built into pipeline |
| Graph node generation | ❌ No content→graph mapping | ✅ Entities + relationships from content |
| Scheduled ingestion | ❌ No periodic feed processing | ✅ APScheduler daily feeds |
| Adapter registry | ❌ No adapter base class | ✅ `SourceAdapter` ABC + registry |
| Frontend management | ❌ No ingestion UI | ✅ Dashboard page for ingestion status |

### Current code that partially overlaps

| File | Purpose | Gap |
|---|---|---|
| `tools/web_tools.py` | `WebFetchTool` — fetches URL content | Returns raw text, no structured extraction |
| `tools/web_extract_tool.py` | Web extraction | Single-purpose, not source-type aware |
| `cron/` + `scheduler/` | Scheduled job infrastructure | No ingestion-specific jobs |
| `memory/store.py` | `PersistentStore` key-value storage | No content→entity→graph pipeline |
| `artifacts_api.py` | Artifact management | No ingestion provenance |

### The contraction

Add a `sources/` directory following Pantheon's pattern:

```
backend/harness/sources/
├── __init__.py          # SourceAdapter ABC + registry
├── adapters/
│   ├── youtube.py       # YouTube transcript + metadata
│   ├── webpage.py       # General webpage → markdown
│   ├── pdf.py           # PDF text + metadata extraction
│   ├── github.py        # GitHub repo → file listing + README
│   └── blog.py          # RSS/Atom feed → articles
├── pipeline.py          # URL → detect source → run adapter → store artifacts + graph nodes
└── scheduler.py         # Cron-triggered daily ingestion feeds
```

This enables: "paste a URL → detect source type → extract structured content → store in memory → index in knowledge graph." Turns the agent's on-demand web fetching into systematic, scheduled content accumulation.
