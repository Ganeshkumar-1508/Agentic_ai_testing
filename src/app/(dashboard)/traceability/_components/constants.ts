import type { Priority, ReqStatus, TestStatus, TestType, GapType, GraphNodeKind, GraphEdgeKind } from "./types";

export const PRIORITY_TONE: Record<Priority, { dot: string; text: string; label: string }> = {
  high: { dot: "bg-rose-400", text: "text-rose-300", label: "High" },
  medium: { dot: "bg-amber-400", text: "text-amber-300", label: "Medium" },
  low: { dot: "bg-sky-400", text: "text-sky-300", label: "Low" },
};

export const REQ_STATUS_TONE: Record<ReqStatus, { dot: string; text: string; label: string }> = {
  active: { dot: "bg-emerald-400", text: "text-emerald-300", label: "Active" },
  archived: { dot: "bg-zinc-500", text: "text-zinc-400", label: "Archived" },
  draft: { dot: "bg-amber-400", text: "text-amber-300", label: "Draft" },
};

export const TEST_STATUS_TONE: Record<TestStatus, { dot: string; text: string; bg: string; label: string }> = {
  passed: { dot: "bg-emerald-400", text: "text-emerald-300", bg: "bg-emerald-500/15", label: "Passed" },
  failed: { dot: "bg-rose-400", text: "text-rose-300", bg: "bg-rose-500/15", label: "Failed" },
  pending: { dot: "bg-zinc-500", text: "text-zinc-400", bg: "bg-white/[0.04]", label: "Pending" },
  skipped: { dot: "bg-zinc-600", text: "text-zinc-500", bg: "bg-white/[0.03]", label: "Skipped" },
  running: { dot: "bg-sky-400", text: "text-sky-300", bg: "bg-sky-500/15", label: "Running" },
};

export const TEST_TYPE_LABEL: Record<TestType, string> = {
  functional: "Functional",
  api: "API",
  boundary: "Boundary",
  negative: "Negative",
  edge_case: "Edge case",
  security: "Security",
  performance: "Performance",
  ui: "UI",
};

export const GAP_LABEL: Record<GapType, string> = {
  no_tests: "No tests",
  failing_tests: "Failing tests",
  none: "Covered",
};

export const NODE_KIND_TONE: Record<GraphNodeKind, {
  border: string;
  bg: string;
  text: string;
  accent: string;
  ring: string;
}> = {
  requirement: {
    border: "border-indigo-400/40",
    bg: "bg-indigo-500/[0.12]",
    text: "text-indigo-200",
    accent: "text-indigo-300",
    ring: "ring-indigo-400/30",
  },
  test: {
    border: "border-emerald-400/40",
    bg: "bg-emerald-500/[0.12]",
    text: "text-emerald-200",
    accent: "text-emerald-300",
    ring: "ring-emerald-400/30",
  },
  defect: {
    border: "border-rose-400/40",
    bg: "bg-rose-500/[0.12]",
    text: "text-rose-200",
    accent: "text-rose-300",
    ring: "ring-rose-400/30",
  },
  gap: {
    border: "border-dashed border-rose-400/40",
    bg: "bg-rose-500/[0.06]",
    text: "text-rose-300/80",
    accent: "text-rose-300",
    ring: "ring-rose-400/20",
  },
};

export const EDGE_KIND_STYLE: Record<GraphEdgeKind, { stroke: string; dasharray?: string; width: number }> = {
  verifies: { stroke: "#34d399", width: 1.5 },
  fails: { stroke: "#fb7185", width: 1.5 },
  gap: { stroke: "#fb7185", dasharray: "4 3", width: 1 },
};
