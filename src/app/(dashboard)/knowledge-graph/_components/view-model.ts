import { NODE_CATEGORY, NODE_CATEGORY_LABEL, NODE_TYPE_LABEL } from "./constants";
import type { GraphSummary, KGEdge, KGNode, KnowledgeGraph } from "./types";

const WEAK_GRAPH_LABELS = new Set([
  "unnamed graph",
  "unknown graph",
  "untitled graph",
  "untitled",
  "knowledge graph",
  "codegraph",
  "graph snapshot",
  "snapshot",
]);

const GENERIC_ROOT_SEGMENTS = new Set([
  "src",
  "app",
  "lib",
  "backend",
  "frontend",
  "server",
  "client",
  "api",
  "components",
  "pages",
  "routes",
  "packages",
  "modules",
  "services",
  "tests",
  "test",
  "docs",
]);

const IGNORED_GRAPH_ROOT_SEGMENTS = new Set([
  ".git",
  ".github",
  ".next",
  ".openclaude",
  ".pytest_cache",
  ".roo",
  ".testai",
  "__pycache__",
  "build",
  "coverage",
  "dist",
  "node_modules",
]);

const GENERIC_FILE_NODE_NAMES = new Set([
  "__init__.py",
  "index.js",
  "index.jsx",
  "index.ts",
  "index.tsx",
  "layout.tsx",
  "page.tsx",
  "readme.md",
  "route.js",
  "route.ts",
  "route.tsx",
  "skill.md",
]);

function cleanString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function cleanDisplayLabel(value: unknown): string | null {
  const cleaned = cleanString(value);
  if (!cleaned) return null;
  return WEAK_GRAPH_LABELS.has(cleaned.toLowerCase()) ? null : cleaned;
}

function splitPathSegments(path: string): string[] {
  return path.split(/[\\/]+/).filter(Boolean);
}

function deriveGraphPathLabel(graph: KnowledgeGraph | null | undefined): string | null {
  if (!graph) return null;

  const counts = new Map<string, number>();

  for (const node of graph.nodes) {
    const file = cleanString(node.filePath) ?? cleanString(node.file);
    if (!file) continue;

    const segments = splitPathSegments(file);
    if (segments.length === 0) continue;

    const [first, second] = segments;
    const firstLower = first?.toLowerCase() ?? "";
    const secondLower = second?.toLowerCase() ?? "";
    if (!first || IGNORED_GRAPH_ROOT_SEGMENTS.has(firstLower)) continue;

    let candidate: string | null = null;
    if (!GENERIC_ROOT_SEGMENTS.has(firstLower)) {
      candidate = first;
    } else if (second && !GENERIC_ROOT_SEGMENTS.has(secondLower) && !IGNORED_GRAPH_ROOT_SEGMENTS.has(secondLower)) {
      candidate = second;
    } else if (second && !IGNORED_GRAPH_ROOT_SEGMENTS.has(secondLower)) {
      candidate = `${first}/${second}`;
    } else {
      candidate = first;
    }

    const cleaned = cleanDisplayLabel(candidate);
    if (!cleaned) continue;

    counts.set(cleaned, (counts.get(cleaned) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0]?.[0] ?? null;
}

export function contextualPathLabel(path: string | null | undefined, segmentCount = 2): string | null {
  const cleaned = cleanString(path);
  if (!cleaned) return null;
  const segments = splitPathSegments(cleaned);
  if (segments.length === 0) return cleaned;
  return segments.slice(-Math.max(1, segmentCount)).join("/");
}

export function repoDisplayNameFromUrl(url: string | null | undefined): string | null {
  const cleaned = cleanString(url);
  if (!cleaned) return null;
  const normalized = cleaned.replace(/\.git$/, "").replace(/\/$/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length >= 2) return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
  return normalized;
}

export function graphSummaryDisplayLabel(summary: GraphSummary): string {
  return (
    cleanDisplayLabel(summary.repository_display_name) ??
    repoDisplayNameFromUrl(summary.repo_url) ??
    cleanDisplayLabel(summary.snapshot_label) ??
    cleanDisplayLabel(summary.volume) ??
    cleanDisplayLabel(summary.id) ??
    cleanString(summary.repo_url) ??
    "Graph"
  );
}

export function formatTimestampLabel(value: string | null | undefined): string | null {
  const clean = cleanString(value);
  if (!clean) return null;
  const date = new Date(clean);
  if (Number.isNaN(date.getTime())) return clean;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export function deriveGraphDisplayMeta(graph: KnowledgeGraph | null, summary: GraphSummary | null) {
  const metadata = graph?.metadata ?? {};
  const pathLabel = deriveGraphPathLabel(graph);
  const summaryId = cleanDisplayLabel(summary?.id) ?? cleanString(summary?.id);
  const metadataGraphId = cleanDisplayLabel(metadata.graphId) ?? cleanString(metadata.graphId);
  const metadataSnapshotLabel = cleanDisplayLabel(metadata.snapshotLabel) ?? cleanString(metadata.snapshotLabel);
  const summarySnapshotLabel = cleanDisplayLabel(summary?.snapshot_label) ?? cleanString(summary?.snapshot_label);
  const repoUrl =
    cleanString(metadata.repoUrl) ??
    cleanString(metadata.repo_url) ??
    cleanString(graph?.project?.repoUrl) ??
    cleanString(summary?.repo_url);
  const repoDisplayName =
    cleanDisplayLabel(metadata.repositoryDisplayName) ??
    cleanDisplayLabel(summary?.repository_display_name) ??
    repoDisplayNameFromUrl(repoUrl) ??
    cleanDisplayLabel(graph?.project?.name) ??
    pathLabel ??
    cleanDisplayLabel(metadata.name) ??
    metadataSnapshotLabel ??
    summarySnapshotLabel ??
    metadataGraphId ??
    summaryId ??
    cleanString(repoUrl);
  const branch = cleanString(metadata.branch) ?? cleanString(summary?.branch);
  const versionLabel = cleanString(metadata.versionLabel) ?? cleanString(graph?.version) ?? cleanString(summary?.version_label);
  const indexedAt = cleanString(metadata.indexedAt) ?? cleanString(metadata.analyzedAt) ?? cleanString(summary?.indexed_at);
  const snapshotLabel =
    cleanDisplayLabel(metadata.snapshotLabel) ??
    cleanDisplayLabel(summary?.snapshot_label) ??
    cleanDisplayLabel(metadata.snapshotId) ??
    cleanDisplayLabel(summary?.snapshot_id) ??
    pathLabel ??
    cleanDisplayLabel(summary?.volume) ??
    metadataGraphId ??
    summaryId ??
    cleanString(repoUrl);
  const graphId = cleanString(metadata.graphId) ?? cleanString(summary?.id) ?? cleanString(repoUrl);
  const languageLabel = cleanString(graph?.project?.language) ?? cleanString(summary?.language);

  return {
    repoUrl,
    repoDisplayName,
    branch,
    versionLabel,
    indexedAt,
    snapshotLabel,
    graphId,
    languageLabel,
  };
}

export function getNodeDegreeMap(graph: KnowledgeGraph): Map<string, number> {
  const degreeMap = new Map<string, number>();
  for (const edge of graph.edges) {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) ?? 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) ?? 0) + 1);
  }
  return degreeMap;
}

export function getTopConnectedNodes(graph: KnowledgeGraph, limit = 6) {
  const degreeMap = getNodeDegreeMap(graph);
  return graph.nodes
    .map((node) => ({ node, degree: degreeMap.get(node.id) ?? 0 }))
    .filter((entry) => entry.degree > 0)
    .sort((left, right) => right.degree - left.degree || left.node.name.localeCompare(right.node.name))
    .slice(0, limit);
}

export function nodeDisplayName(node: KGNode): string {
  const explicitName = cleanString(node.name);
  const file = cleanString(node.filePath) ?? cleanString(node.file);

  if (!file) return explicitName ?? "Untitled node";

  const contextualFileLabel = contextualPathLabel(file, 2) ?? file;
  const basename = splitPathSegments(file).at(-1)?.toLowerCase() ?? null;
  const explicitLower = explicitName?.toLowerCase() ?? null;
  const shouldPromotePathContext =
    node.type === "file" &&
    explicitLower === basename &&
    basename !== null &&
    (GENERIC_FILE_NODE_NAMES.has(basename) || splitPathSegments(file).length > 1);

  if (!explicitName) return contextualFileLabel;
  if (shouldPromotePathContext) return contextualFileLabel;
  return explicitName;
}

export function nodeSecondaryLabel(node: KGNode): string {
  const file = cleanString(node.filePath) ?? cleanString(node.file);
  const displayName = nodeDisplayName(node).toLowerCase();

  if (file && displayName !== file.toLowerCase()) return file;
  return node.language ?? (NODE_TYPE_LABEL[node.type] ?? node.type);
}

export function buildNodeHeuristicSummary(node: KGNode, incomingCount: number, outgoingCount: number): string {
  const existing = cleanString(node.summary);
  if (existing) return existing;

  const displayName = nodeDisplayName(node);
  const typeLabel = (NODE_TYPE_LABEL[node.type] ?? node.type).toLowerCase();
  const categoryLabel = NODE_CATEGORY_LABEL[NODE_CATEGORY[node.type]].toLowerCase();
  const file = cleanString(node.filePath) ?? cleanString(node.file);
  const language = cleanString(node.language);
  const relationshipSummary = `${incomingCount} inbound and ${outgoingCount} outbound relationship${incomingCount + outgoingCount === 1 ? "" : "s"}`;

  return [
    `${NODE_TYPE_LABEL[node.type] ?? node.type} ${displayName} is currently represented as a ${categoryLabel} node.`,
    file ? `It maps back to ${file}.` : null,
    language ? `Primary language: ${language}.` : null,
    `The current graph shows ${relationshipSummary}.`,
    node.tags.length > 0 ? `Context tags: ${node.tags.join(", ")}.` : null,
    `Use the source action for the concrete implementation behind this ${typeLabel}.`,
  ]
    .filter(Boolean)
    .join(" ");
}

export function rankSearchResults(
  graph: KnowledgeGraph,
  matchedIds: Set<string> | null,
  query: string,
  limit = 12
) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!matchedIds || !normalizedQuery) return [];

  const degreeMap = getNodeDegreeMap(graph);

  return graph.nodes
    .filter((node) => matchedIds.has(node.id))
    .map((node) => {
      const name = node.name.toLowerCase();
      const secondary = nodeSecondaryLabel(node).toLowerCase();
      const startsWith = name.startsWith(normalizedQuery) ? 3 : 0;
      const exact = name === normalizedQuery ? 4 : 0;
      const inFile = secondary.includes(normalizedQuery) ? 1 : 0;
      const degree = degreeMap.get(node.id) ?? 0;
      return {
        node,
        degree,
        secondaryLabel: nodeSecondaryLabel(node),
        score: exact + startsWith + inFile + Math.min(degree, 12) / 100,
      };
    })
    .sort((left, right) => right.score - left.score || right.degree - left.degree || left.node.name.localeCompare(right.node.name))
    .slice(0, limit);
}

export function summarizeEdgeTypes(edges: KGEdge[]) {
  const counts = new Map<KGEdge["type"], number>();
  for (const edge of edges) {
    counts.set(edge.type, (counts.get(edge.type) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([type, count]) => ({ type, count }))
    .sort((left, right) => right.count - left.count || left.type.localeCompare(right.type));
}
