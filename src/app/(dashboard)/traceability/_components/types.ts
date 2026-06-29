export type Priority = "high" | "medium" | "low";
export type ReqStatus = "active" | "archived" | "draft";
export type TestStatus = "passed" | "failed" | "pending" | "skipped" | "running";
export type TestType = "functional" | "api" | "boundary" | "negative" | "edge_case" | "security" | "performance" | "ui";
export type GapType = "no_tests" | "failing_tests" | "none";

export type Requirement = {
  id: string;
  title: string;
  description?: string | null;
  priority: Priority;
  status: ReqStatus;
  source?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type TestCase = {
  id: string;
  name: string;
  status: TestStatus;
  test_type?: TestType | null;
  code_language?: string | null;
  requirement_id?: string | null;
  linked_at?: string | null;
};

export type CoverageGap = {
  requirement_id: string;
  title: string;
  test_count: number;
  passed_count: number;
  has_gap: boolean;
  gap_type: GapType;
};

export type Defect = {
  defect_id: string;
  defect_url?: string | null;
  test_name?: string | null;
  requirement_id?: string | null;
  status?: string | null;
};

export type RiskScore = {
  requirement_id: string;
  title: string;
  priority: Priority;
  coverage_pct: number;
  risk_score: number;
};

export type MatrixRow = {
  requirement_id: string;
  title: string;
  priority: Priority;
  tests: Array<{
    id: string;
    name: string;
    status: TestStatus;
    test_type?: TestType | null;
    linked_at?: string | null;
  }>;
  test_count: number;
  passed_count: number;
};

export type ViewMode = "graph" | "matrix" | "table";
export type LayoutDirection = "TB" | "LR";

export type GraphNodeKind = "requirement" | "test" | "defect" | "gap";

export type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  label: string;
  status?: TestStatus | ReqStatus;
  priority?: Priority;
  meta?: Record<string, unknown>;
};

export type GraphEdgeKind = "verifies" | "fails" | "gap";

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  kind: GraphEdgeKind;
};

export type GraphModel = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};
