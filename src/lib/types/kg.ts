export type NodeType =
  | "file" | "function" | "class" | "module" | "concept" | "component"
  | "config" | "document" | "service" | "table" | "endpoint" | "pipeline" | "schema" | "resource"
  | "domain" | "flow" | "step" | "article" | "entity" | "topic" | "claim" | "source";

export type EdgeType =
  | "imports" | "exports" | "contains" | "inherits" | "implements" | "references"
  | "calls" | "subscribes" | "publishes" | "middleware"
  | "reads_from" | "writes_to" | "transforms" | "validates"
  | "depends_on" | "tested_by" | "configures"
  | "related" | "similar_to"
  | "deploys" | "serves" | "provisions" | "triggers"
  | "migrates" | "documents" | "routes" | "defines_schema";

export type Direction = "forward" | "backward" | "bidirectional";
export type Complexity = "simple" | "moderate" | "complex";

export interface KGNode {
  id: string;
  type: NodeType;
  name: string;
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
