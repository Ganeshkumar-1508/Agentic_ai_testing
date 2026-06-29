import type { GraphModel, GraphNode, GraphEdge, Requirement, MatrixRow, Defect, CoverageGap } from "./types";

export function buildGraphModel(
  requirements: Requirement[],
  matrix: MatrixRow[],
  defects: Defect[],
  gaps: CoverageGap[]
): GraphModel {
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];

  for (const req of requirements) {
    nodes.set(`req:${req.id}`, {
      id: `req:${req.id}`,
      kind: "requirement",
      label: req.title,
      status: req.status,
      priority: req.priority,
      meta: { ...req },
    });
  }

  for (const row of matrix) {
    for (const t of row.tests) {
      const tid = `test:${t.id}`;
      if (!nodes.has(tid)) {
        nodes.set(tid, {
          id: tid,
          kind: "test",
          label: t.name,
          status: t.status,
          meta: { test_type: t.test_type, requirement_id: row.requirement_id },
        });
      }
      edges.push({
        id: `e:${row.requirement_id}:${t.id}`,
        source: `req:${row.requirement_id}`,
        target: tid,
        kind: t.status === "failed" ? "fails" : "verifies",
      });
    }
  }

  for (const def of defects) {
    if (!def.test_name) continue;
    const did = `defect:${def.defect_id}`;
    nodes.set(did, {
      id: did,
      kind: "defect",
      label: def.defect_id,
      meta: { ...def },
    });
    edges.push({
      id: `e-def:${def.defect_id}`,
      source: `test:${def.test_name}`,
      target: did,
      kind: "fails",
    });
  }

  for (const gap of gaps) {
    if (!gap.has_gap) continue;
    const gid = `gap:${gap.requirement_id}`;
    if (nodes.has(gid)) continue;
    nodes.set(gid, {
      id: gid,
      kind: "gap",
      label: gap.gap_type === "no_tests" ? "No tests" : "Failing tests",
      meta: { requirement_id: gap.requirement_id, test_count: gap.test_count, passed_count: gap.passed_count },
    });
    edges.push({
      id: `e-gap:${gap.requirement_id}`,
      source: `req:${gap.requirement_id}`,
      target: gid,
      kind: "gap",
    });
  }

  return { nodes: Array.from(nodes.values()), edges };
}
