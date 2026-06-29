/**
 * Knowledge graph types — matches the Understand-Anything schema
 * (https://github.com/Lum1104/Understand-Anything).
 *
 * Our backend stores a slightly trimmed shape:
 *   - `metadata` block at root (canonical uses `project`)
 *   - nodes use `file` instead of `filePath`
 *   - nodes include a `language` field
 *   - `complexity`, `languageNotes`, `layers`, `tour` are optional and may be absent
 */

export type NodeType =
  // Code (6)
  | "file" | "function" | "class" | "module" | "concept" | "component"
  // Non-code (8)
  | "config" | "document" | "service" | "table" | "endpoint" | "pipeline" | "schema" | "resource"
  // Domain/knowledge (8)
  | "domain" | "flow" | "step" | "article" | "entity" | "topic" | "claim" | "source";

export type NodeCategory = "code" | "noncode" | "domain";

export type EdgeType =
  // Structural (6)
  | "imports" | "exports" | "contains" | "inherits" | "implements" | "references"
  // Behavioral (4)
  | "calls" | "subscribes" | "publishes" | "middleware"
  // Data flow (4)
  | "reads_from" | "writes_to" | "transforms" | "validates"
  // Dependencies (3)
  | "depends_on" | "tested_by" | "configures"
  // Semantic (2)
  | "related" | "similar_to"
  // Infrastructure (4)
  | "deploys" | "serves" | "provisions" | "triggers"
  // Schema/Data (4)
  | "migrates" | "documents" | "routes" | "defines_schema";

export type EdgeCategory =
  | "structural" | "behavioral" | "data" | "dependencies" | "semantic" | "infrastructure" | "schema";

export type Direction = "forward" | "backward" | "bidirectional";

export type Complexity = "simple" | "moderate" | "complex";

export interface KGNode {
  id: string;
  type: NodeType;
  name: string;
  /** Canonical: `filePath`; our backend: `file` */
  file?: string;
  filePath?: string;
  summary: string;
  tags: string[];
  complexity?: Complexity;
  language?: string;
  languageNotes?: string;
}

export interface KGEdge {
  source: string;
  target: string;
  type: EdgeType;
  direction: Direction;
  weight: number;
}

export interface KGLayer {
  id: string;
  name: string;
  description: string;
  nodeIds: string[];
}

export interface KGTourStep {
  order: number;
  title: string;
  description: string;
  nodeIds: string[];
  languageLesson?: string;
}

export interface KGProject {
  name: string;
  description: string;
  languages: string[];
  frameworks: string[];
  analyzedAt: string;
  gitCommitHash: string;
  repoUrl?: string;
  language?: string;
}

export interface KGGraphMetadata extends Omit<Partial<KGProject>, "repoUrl" | "analyzedAt"> {
  generator?: string;
  totalFiles?: number;
  repoUrl?: string | null;
  repo_url?: string | null;
  repositoryDisplayName?: string | null;
  branch?: string | null;
  graphId?: string;
  snapshotId?: string;
  snapshotLabel?: string;
  versionLabel?: string | null;
  schemaVersion?: number | null;
  generatedAt?: string | null;
  indexedAt?: string | null;
  analyzedAt?: string | null;
  nodeCount?: number;
  edgeCount?: number;
  [key: string]: unknown;
}

export interface KnowledgeGraph {
  version?: string;
  project?: KGProject;
  metadata?: KGGraphMetadata;
  nodes: KGNode[];
  edges: KGEdge[];
  layers?: KGLayer[];
  tour?: KGTourStep[];
}

export interface GraphSummary {
  id: string;
  volume: string;
  node_count: number;
  edge_count?: number;
  repo_url: string;
  repository_display_name?: string | null;
  branch?: string | null;
  version_label?: string | null;
  indexed_at?: string | null;
  snapshot_id?: string;
  snapshot_label?: string;
  language: string;
}

export interface GraphListResponse {
  graphs: GraphSummary[];
}

export interface GraphDetailResponse {
  graph: KnowledgeGraph;
}

export interface FileContentResponse {
  graph_id: string;
  path: string;
  language: string;
  content: string | null;
  lines: number;
  size_bytes: number;
  truncated: boolean;
  source: "local" | "missing" | "github";
  source_url: string | null;
}

// ─── Panel types (Ask / Tour / Communities) ──────────────────────

export interface AskMessage {
  id: string;
  type: "question" | "answer";
  text: string;
  timestamp: number;
}

export interface CommunityInfo {
  id: number;
  label: string;
  nodeCount: number;
  color: string;
  topFiles: string[];
}

export interface GraphStats {
  nodes: number;
  edges: number;
  communities: number;
  languages: string[];
}

export type PanelTab = "details" | "overview" | "communities" | "ask" | "tour";
