import type { ElkNode, ElkExtendedEdge, LayoutOptions } from "elkjs/lib/elk.bundled.js";
import type { Node, Edge, Position } from "@xyflow/react";

let elkInstance: import("elkjs/lib/elk.bundled.js").ELK | null = null;
let elkLoading: Promise<import("elkjs/lib/elk.bundled.js").ELK> | null = null;

async function loadElk(): Promise<import("elkjs/lib/elk.bundled.js").ELK> {
  if (elkInstance) return elkInstance;
  if (elkLoading) return elkLoading;
  elkLoading = (async () => {
    const mod = await import("elkjs/lib/elk.bundled.js");
    const ELK = mod.default;
    elkInstance = new ELK();
    return elkInstance;
  })();
  return elkLoading;
}

export type LayoutDirection = "LR" | "TB" | "RIGHT" | "DOWN";
export type LayoutAlgorithm = "layered" | "force" | "mrtree" | "stress" | "radial";

export interface ElkLayoutOptions {
  direction?: LayoutDirection;
  algorithm?: LayoutAlgorithm;
  nodeWidth?: number;
  nodeHeight?: number;
  nodeNodeBetweenLayers?: number;
  nodeNode?: number;
  padding?: number;
  thoroughness?: number;
  edgeRouting?: "ORTHOGONAL" | "POLYLINE" | "SPLINES";
}

const DEFAULT_OPTIONS = {
  algorithm: "layered" as LayoutAlgorithm,
  nodeWidth: 200,
  nodeHeight: 64,
  nodeNodeBetweenLayers: 60,
  nodeNode: 50,
  padding: 24,
  thoroughness: 7,
  edgeRouting: "POLYLINE" as const,
};

function toElkDirection(d: LayoutDirection): "RIGHT" | "DOWN" {
  return d === "LR" || d === "RIGHT" ? "RIGHT" : "DOWN";
}

function toPosition(d: LayoutDirection): { source: Position; target: Position } {
  return d === "LR" || d === "RIGHT"
    ? { source: "right" as Position, target: "left" as Position }
    : { source: "bottom" as Position, target: "top" as Position };
}

export interface LayoutResult {
  nodes: Node[];
  edges: Edge[];
}

export async function layoutGraph(
  nodes: Node[],
  edges: Edge[],
  options: ElkLayoutOptions = {}
): Promise<LayoutResult> {
  if (nodes.length === 0) return { nodes, edges };

  const cfg = { ...DEFAULT_OPTIONS, ...options };
  const dir = options.direction ?? "LR";
  const elkDir = toElkDirection(dir);
  const positions = toPosition(dir);

  const elk = await loadElk();

  const elkGraph: ElkNode = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": cfg.algorithm,
      "elk.direction": elkDir,
      "elk.layered.spacing.nodeNodeBetweenLayers": String(cfg.nodeNodeBetweenLayers),
      "elk.spacing.nodeNode": String(cfg.nodeNode),
      "elk.spacing.edgeNode": "20",
      "elk.spacing.edgeEdge": "15",
      "elk.padding": `[top=${cfg.padding},left=${cfg.padding},bottom=${cfg.padding},right=${cfg.padding}]`,
      "elk.layered.thoroughness": String(cfg.thoroughness),
      "elk.edgeRouting": cfg.edgeRouting,
    } as LayoutOptions,
    children: nodes.map((n) => ({
      id: n.id,
      width: (n.measured?.width as number) ?? (n.width as number) ?? cfg.nodeWidth,
      height: (n.measured?.height as number) ?? (n.height as number) ?? cfg.nodeHeight,
    })),
    edges: edges.map(
      (e) =>
        ({
          id: e.id,
          sources: [e.source],
          targets: [e.target],
        }) as ElkExtendedEdge
    ),
  };

  const result = await elk.layout(elkGraph);
  const children = result.children ?? [];
  const posById = new Map<string, { x: number; y: number }>();
  for (const c of children) {
    posById.set(c.id, {
      x: (c.x ?? 0) - (c.width ?? cfg.nodeWidth) / 2,
      y: (c.y ?? 0) - (c.height ?? cfg.nodeHeight) / 2,
    });
  }

  const layouted: Node[] = nodes.map((n) => ({
    ...n,
    position: posById.get(n.id) ?? n.position ?? { x: 0, y: 0 },
    sourcePosition: positions.source,
    targetPosition: positions.target,
  }));

  return { nodes: layouted, edges };
}

export interface UseLayoutState {
  status: "idle" | "loading" | "ready" | "error";
  nodes: Node[];
  error?: string;
}
