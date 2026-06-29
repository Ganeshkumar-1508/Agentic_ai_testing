import type {
  NodeType,
  NodeCategory,
  EdgeType,
  EdgeCategory,
  KGNode,
  KGEdge,
} from "./types";

// ─── Design tokens ───────────────────────────────────────────────
export const SPRING = {
  gentle: { type: "spring" as const, stiffness: 80, damping: 16 },
  snappy: { type: "spring" as const, stiffness: 200, damping: 18 },
  overshoot: { type: "spring" as const, stiffness: 140, damping: 8 },
} as const;

export const MICRO = {
  pulse: "pulse-dot 1.5s ease-in-out infinite",
  float: "float-node 3s ease-in-out infinite",
  shimmer: "shimmer 1.5s linear infinite",
  breathe: "breathe 4s ease-in-out infinite",
} as const;

// ─── Community palette (8 colors, no purple — per LILA BAN) ────
export const COMMUNITY_COLORS = [
  { dot: "bg-emerald-400", hex: "#34d399", label: "API Layer" },
  { dot: "bg-sky-400",    hex: "#38bdf8", label: "Service Layer" },
  { dot: "bg-amber-400",  hex: "#fbbf24", label: "Data Layer" },
  { dot: "bg-rose-400",   hex: "#fb7185", label: "UI Layer" },
  { dot: "bg-teal-400",   hex: "#2dd4bf", label: "Infrastructure" },
  { dot: "bg-blue-400",   hex: "#60a5fa", label: "Shared Types" },
  { dot: "bg-orange-400", hex: "#fb923c", label: "Config" },
  { dot: "bg-pink-400",   hex: "#f472b6", label: "Testing" },
] as const;

export const NODE_CATEGORY: Record<NodeType, NodeCategory> = {
  file: "code", function: "code", class: "code", module: "code", concept: "code", component: "code",
  config: "noncode", document: "noncode", service: "noncode", table: "noncode",
  endpoint: "noncode", pipeline: "noncode", schema: "noncode", resource: "noncode",
  domain: "domain", flow: "domain", step: "domain", article: "domain",
  entity: "domain", topic: "domain", claim: "domain", source: "domain",
};

export const NODE_CATEGORY_LABEL: Record<NodeCategory, string> = {
  code: "Code",
  noncode: "Non-code",
  domain: "Domain",
};

export const NODE_TYPE_LABEL: Partial<Record<NodeType, string>> = {
  file: "File", function: "Function", class: "Class", module: "Module", concept: "Concept", component: "Component",
  config: "Config", document: "Document", service: "Service", table: "Table",
  endpoint: "Endpoint", pipeline: "Pipeline", schema: "Schema", resource: "Resource",
  domain: "Domain", flow: "Flow", step: "Step", article: "Article",
  entity: "Entity", topic: "Topic", claim: "Claim", source: "Source",
};

const CATEGORY_TONE: Record<NodeCategory, { dot: string; border: string; bg: string; text: string; accent: string; ring: string; hex: string }> = {
  code:    { dot: "bg-sky-400",    border: "border-sky-400/40",    bg: "bg-sky-500/[0.12]",    text: "text-sky-200",    accent: "text-sky-300",    ring: "ring-sky-400/30",    hex: "#38bdf8" },
  noncode: { dot: "bg-emerald-400",border: "border-emerald-400/40",bg: "bg-emerald-500/[0.12]",text: "text-emerald-200",accent: "text-emerald-300",ring: "ring-emerald-400/30",hex: "#34d399" },
  domain:  { dot: "bg-violet-400", border: "border-violet-400/40", bg: "bg-violet-500/[0.12]", text: "text-violet-200", accent: "text-violet-300", ring: "ring-violet-400/30", hex: "#a78bfa" },
};

export function getNodeTone(type: NodeType) {
  return CATEGORY_TONE[NODE_CATEGORY[type]] ?? CATEGORY_TONE.code;
}

// ─── Edge styling ────────────────────────────────────────────────
export const EDGE_CATEGORY: Record<EdgeType, EdgeCategory> = {
  imports: "structural", exports: "structural", contains: "structural", inherits: "structural",
  implements: "structural", references: "structural",
  calls: "behavioral", subscribes: "behavioral", publishes: "behavioral", middleware: "behavioral",
  reads_from: "data", writes_to: "data", transforms: "data", validates: "data",
  depends_on: "dependencies", tested_by: "dependencies", configures: "dependencies",
  related: "semantic", similar_to: "semantic",
  deploys: "infrastructure", serves: "infrastructure", provisions: "infrastructure", triggers: "infrastructure",
  migrates: "schema", documents: "schema", routes: "schema", defines_schema: "schema",
};

export const EDGE_CATEGORY_LABEL: Record<EdgeCategory, string> = {
  structural: "Structural", behavioral: "Behavioral", data: "Data flow",
  dependencies: "Dependencies", semantic: "Semantic", infrastructure: "Infrastructure", schema: "Schema/Data",
};

export const EDGE_TONE: Record<EdgeCategory, { hex: string; dasharray?: string; width: number }> = {
  structural:     { hex: "#34d399", width: 1.5 },
  behavioral:     { hex: "#38bdf8", width: 1.5 },
  data:           { hex: "#fbbf24", width: 1.5 },
  dependencies:   { hex: "#fb7185", width: 1.5 },
  semantic:       { hex: "#a78bfa", width: 1, dasharray: "3 3" },
  infrastructure: { hex: "#2dd4ee", width: 1.5 },
  schema:         { hex: "#e879f9", width: 1.5 },
};

export function getEdgeStyle(type: EdgeType) {
  return EDGE_TONE[EDGE_CATEGORY[type]] ?? EDGE_TONE.semantic;
}

export function getEdgeCategoryStyle(cat: EdgeCategory) {
  return EDGE_TONE[cat] ?? EDGE_TONE.semantic;
}

export const EDGE_WEIGHT_DEFAULT: Record<EdgeType, number> = {
  contains: 1.0, inherits: 0.9, implements: 0.9, references: 0.9,
  calls: 0.8, exports: 0.8, defines_schema: 0.8,
  imports: 0.7, deploys: 0.7, migrates: 0.7,
  depends_on: 0.6, configures: 0.6, triggers: 0.6,
  tested_by: 0.5, documents: 0.5, provisions: 0.5, serves: 0.5, routes: 0.5,
  subscribes: 0.5, publishes: 0.5, middleware: 0.5,
  reads_from: 0.5, writes_to: 0.5, transforms: 0.5, validates: 0.5,
  related: 0.5, similar_to: 0.5,
} as Record<EdgeType, number>;

// ─── Helpers ─────────────────────────────────────────────────────
export function countByCategory<T extends string>(
  items: Array<{ type: T }>, map: Record<T, string>
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const item of items) { const k = map[item.type]; out[k] = (out[k] ?? 0) + 1; }
  return out;
}

export function uniqueLanguages(nodes: KGNode[]): Array<[string, number]> {
  const m = new Map<string, number>();
  for (const n of nodes) { if (n.language) m.set(n.language, (m.get(n.language) ?? 0) + 1); }
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
}

export function uniqueTags(nodes: KGNode[]): Array<[string, number]> {
  const m = new Map<string, number>();
  for (const n of nodes) { for (const t of n.tags ?? []) m.set(t, (m.get(t) ?? 0) + 1); }
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]).slice(0, 20);
}

export function summarizeEdges(edges: KGEdge[]): Record<EdgeCategory, number> {
  const out: Record<EdgeCategory, number> = {
    structural: 0, behavioral: 0, data: 0, dependencies: 0, semantic: 0, infrastructure: 0, schema: 0,
  };
  for (const e of edges) { const cat = EDGE_CATEGORY[e.type]; if (cat) out[cat] += 1; }
  return out;
}
