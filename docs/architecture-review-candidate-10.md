# Candidate 10: Split the 2,295-line Knowledge Graph monolith into composable page modules

**Strength**: Strong | **Category**: component architecture / monolith decomposition

---

## Research sources (10)

### Agent harness graph visualization patterns

1. **a0 Agent Harness Web UI** — Single Dashboard component (118 lines HTML + Alpine.js store). The entire harness UI is 3 files. No file exceeds 200 lines in the UI layer. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

2. **Harness Engineering Knowledge Graph** — Interactive graph of 883 entities and 1,590 relationships. Rendered as an embeddable widget, not a 2,000+ line monolith page. https://harness-engineering.ai/

3. **OpenTelemetry Trace Visualization** — One span model → multiple view components (waterfall, list, graph). Each view is a separate component under 300 lines. No monolithic trace viewer. https://opentelemetry.io/docs/specs/semconv/gen-ai/

4. **ReactFlow Best Practices** — "Separate node components, edge components, and layout logic from page state management." The recommended pattern: `<ReactFlow>` wrapper gets a data provider, node types are separate components, layout is a utility. https://reactflow.dev/learn

5. **Microsoft Agentic Harness** — One dashboard, multiple panels. Each panel is a separate component under 200 lines. https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

6. **Codebase audit — Knowledge Graph page vs other pages** (see below)

7. **paddo.dev — Agent Harnesses: DIY to Product** — "Visual progress tracking: timeline views, status indicators, screenshot captures." Visual components are separate, composable, not monolithic. https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

8. **Candidate 3 precedent** — The Chat page (709 lines) was identified as overloaded in Candidate 3 and the solution was extracting 3 hooks. The KG page is 3.2× larger than the Chat page.

9. **CONTEXT.md — Knowledge Graph** — "Knowledge graph with node/edge counts." A tool in the harness, not a monolithic page module.

10. **Codebase audit — 8 panel sub-components already extracted** (see below)

---

## Codebase evidence

### The 2,295-line monolith vs all other pages

| Page | Lines | Issue |
|---|---|---|
| **knowledge-graph/page.tsx** | **2,295** | 3.2× larger than the next largest |
| sessions/page.tsx | 751 | Explored in Candidate 2 |
| kanban/page.tsx | 765 | Standalone |
| history/[runId]/page.tsx | 793 | Standalone |
| chat/page.tsx | 709 | Addressed in Candidate 3 |
| pipeline/page.tsx | 567 | Standalone |
| dashboard/page.tsx | 445 | Standalone |
| activity/page.tsx | 364 | Standalone |
| settings/page.tsx | 372 | Tab coordinator |

### What the KG page does (all inline, 2,295 lines)
- ReactFlow graph canvas (nodes, edges, zoom, pan, layout)
- 6 custom node types rendered inline
- Custom edge rendering with labels
- Graph search + filtering
- Detail panel (node/edge metadata, file content)
- Overview panel (stats, languages, node counts)
- Communities panel (detected clusters)
- Ask panel (Q&A over the graph)
- Tour panel (guided walkthrough)
- Layer selector and graph management
- Code viewer panel
- Import/export/download buttons
- State management (selected node, view mode, search)

### The sub-components already extracted (8 files)
| Component | Lines | Purpose |
|---|---|---|
| `AskPanel.tsx` | 218 | Q&A interface |
| `CodeViewer.tsx` | 164 | Code display |
| `CodeViewerPanel.tsx` | 131 | Code viewer wrapper |
| `mini-ui.tsx` | 39 | Mini graph overlay |
| `states.tsx` | 123 | Loading/empty/error |
| `top-bar.tsx` | 111 | Graph toolbar |
| `TourPanel.tsx` | 173 | Guided walkthrough |
| `view-model.ts` | ~200 | Data transformation |

**8 extracted files: ~1,159 lines — vs 2,295 remaining in the monolith.** The extraction is roughly 1/3 done.

### The fix
Extract 4 more modules from the monolith:
- `graph-canvas.tsx` — ReactFlow setup, node/edge rendering, layout management (~400 lines)
- `graph-panels.tsx` — Detail panel, overview panel, communities panel selector (~400 lines)
- `use-graph-data.ts` — Data fetching, search indexing, community detection hook (~300 lines)
- `graph-page.tsx` — Slim coordinator (~100 lines, down from 2,295)
