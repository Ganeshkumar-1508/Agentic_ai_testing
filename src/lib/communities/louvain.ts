import type { KGNode, KGEdge } from "@/lib/types/kg";
import { getNodeFile } from "@/app/(dashboard)/knowledge-graph/_components/graph-model";

export const COMMUNITY_COLORS = [
  "#34d399", "#60a5fa", "#fbbf24", "#f87171",
];

export function communityColor(index: number): string {
  return COMMUNITY_COLORS[index % COMMUNITY_COLORS.length];
}

export const COMMUNITY_COLOR_CLASSES = [
  "bg-emerald-400", "bg-blue-400", "bg-amber-400", "bg-red-400",
];

export function communityColorClass(index: number): string {
  return COMMUNITY_COLOR_CLASSES[index % COMMUNITY_COLOR_CLASSES.length];
}

export interface CommunityResult {
  nodeCommunity: Map<string, number>;
  communities: Array<{ id: number; nodes: string[]; label: string }>;
  method: "folder" | "louvain";
  count: number;
}

function detectByFolder(nodes: KGNode[]): CommunityResult {
  const groups = new Map<string, string[]>();
  for (const n of nodes) {
    const file = getNodeFile(n);
    const group = file ? file.replace(/^.*[/\\]/, "").slice(0, 2) : "root";
    const folder = file ? file.split("/").slice(0, 2).join("/") : "root";
    const label = folder;
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(n.id);
  }

  const sorted = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  const nodeCommunity = new Map<string, number>();
  const communities: CommunityResult["communities"] = [];

  sorted.forEach(([label, ids], i) => {
    communities.push({ id: i, nodes: ids, label });
    for (const id of ids) {
      nodeCommunity.set(id, i);
    }
  });

  return {
    nodeCommunity,
    communities,
    method: "folder",
    count: communities.length,
  };
}

async function detectLouvain(nodes: KGNode[], edges: KGEdge[]): Promise<CommunityResult> {
  try {
    const [{ default: Graph }, { default: louvain }] = await Promise.all([
      import("graphology") as unknown as Promise<{ default: new (args?: { type?: string }) => { order: number; size: number; addNode: (id: string) => void; addEdge: (s: string, t: string) => void } }>,
      import("graphology-communities-louvain") as Promise<{ default: (graph: unknown, opts?: { resolution?: number }) => Record<string, number> }>,
    ]);

    const graph = new Graph({ type: "directed" });
    const idSet = new Set<string>();
    for (const n of nodes) idSet.add(n.id);
    for (const e of edges) {
      if (!idSet.has(e.source)) { idSet.add(e.source); }
      if (!idSet.has(e.target)) { idSet.add(e.target); }
    }
    for (const id of idSet) graph.addNode(id);
    for (const e of edges) graph.addEdge(e.source, e.target);

    const raw = louvain(graph);
    const byIndex = new Map<number, string[]>();
    for (const [nodeId, index] of Object.entries(raw)) {
      if (!byIndex.has(index)) byIndex.set(index, []);
      byIndex.get(index)!.push(nodeId);
    }

    const sorted = [...byIndex.entries()].sort((a, b) => b[1].length - a[1].length);
    const nodeCommunity = new Map<string, number>();
    const communities: CommunityResult["communities"] = [];

    sorted.forEach(([origIndex, ids], _i) => {
      const label = ids.length > 1
        ? `C${origIndex}`
        : ids[0].includes("/") ? ids[0].split("/").slice(-2, -1)[0] ?? ids[0]
        : ids[0].slice(0, 24);
      communities.push({ id: origIndex, nodes: ids, label });
      for (const id of ids) {
        nodeCommunity.set(id, origIndex);
      }
    });

    return {
      nodeCommunity,
      communities,
      method: "louvain",
      count: communities.length,
    };
  } catch {
    return detectByFolder(nodes);
  }
}

export async function detectCommunities(
  nodes: KGNode[],
  edges: KGEdge[]
): Promise<CommunityResult> {
  if (nodes.length === 0) {
    return {
      nodeCommunity: new Map(),
      communities: [],
      method: "folder",
      count: 0,
    };
  }

  if (edges.length >= nodes.length) {
    return detectLouvain(nodes, edges);
  }

  return detectByFolder(nodes);
}

export function getCommunityName(
  nodeId: string,
  result: CommunityResult
): string {
  const idx = result.nodeCommunity.get(nodeId);
  if (idx === undefined) return "—";
  const c = result.communities.find((c) => c.id === idx);
  if (!c) return `#${idx}`;
  return c.label;
}
