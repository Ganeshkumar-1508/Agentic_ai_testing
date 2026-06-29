import type { Node, Edge } from "@xyflow/react";
import type { KnowledgeGraph, KGNode, NodeType } from "./types";
import { getEdgeStyle, NODE_CATEGORY } from "./constants";
import { searchKGIndex, type KGSearchDoc } from "@/lib/search/kg-search";
import type MiniSearch from "minisearch";
import type { CommunityResult } from "@/lib/communities/louvain";

const MAX_RENDER_NODES = 560;
export const KG_NODE_W = 72;
export const KG_NODE_H = 50;

function buildRenderSubset(prioritized: KGNode[], maxNodes: number): KGNode[] {
  if (prioritized.length <= maxNodes) return prioritized;

  const coreCount = Math.min(prioritized.length, Math.max(180, Math.round(maxNodes * 0.42)));
  const subset = prioritized.slice(0, coreCount);
  const used = new Set(subset.map((node) => node.id));
  const tail = prioritized.slice(coreCount);
  const slotsRemaining = Math.max(0, maxNodes - subset.length);

  if (slotsRemaining === 0 || tail.length === 0) {
    return subset.slice(0, maxNodes);
  }

  const step = tail.length / slotsRemaining;
  for (let index = 0; index < slotsRemaining; index += 1) {
    const candidate = tail[Math.min(tail.length - 1, Math.floor(index * step))];
    if (!candidate || used.has(candidate.id)) continue;
    subset.push(candidate);
    used.add(candidate.id);
  }

  if (subset.length < maxNodes) {
    for (const candidate of tail) {
      if (used.has(candidate.id)) continue;
      subset.push(candidate);
      used.add(candidate.id);
      if (subset.length >= maxNodes) break;
    }
  }

  return subset.slice(0, maxNodes);
}

export interface KGFilter {
  query: string;
  types: Set<NodeType>;
  language: string | null;
  category: "all" | "code" | "noncode" | "domain";
}

export const EMPTY_FILTER: KGFilter = {
  query: "",
  types: new Set(),
  language: null,
  category: "all",
};

export interface KGGraphModel {
  nodes: Node[];
  edges: Edge[];
  totalNodes: number;
  truncated: boolean;
  matchedNodeIds: Set<string>;
  searchMatchedAll: Set<string> | null;
}

export function buildKGModel(
  graph: KnowledgeGraph,
  filter: KGFilter,
  searchIndex: MiniSearch<KGSearchDoc> | null = null,
  communities: CommunityResult | null = null,
  direction: "TB" | "LR" = "LR"
): KGGraphModel {
  const q = filter.query.trim();
  const queryMatched: Set<string> | null = q
    ? searchIndex
      ? searchKGIndex(searchIndex, q)
      : new Set(
          graph.nodes
            .filter((n) => {
              const hay = [n.name, n.summary, n.file ?? n.filePath ?? "", ...(n.tags ?? [])]
                .join(" ")
                .toLowerCase();
              return hay.includes(q.toLowerCase());
            })
            .map((n) => n.id)
        )
    : null;

  const degreeMap = new Map<string, number>();
  for (const edge of graph.edges) {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) ?? 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) ?? 0) + 1);
  }

  const matched: KGNode[] = graph.nodes.filter((n) => {
    if (filter.types.size > 0 && !filter.types.has(n.type)) return false;
    if (filter.language && n.language !== filter.language) return false;
    if (queryMatched && !queryMatched.has(n.id)) return false;
    if (
      filter.category !== "all" &&
      NODE_CATEGORY[n.type] !== filter.category
    )
      return false;
    return true;
  });

  const prioritized = [...matched].sort((left, right) => {
    const leftSearch = queryMatched?.has(left.id) ? 1 : 0;
    const rightSearch = queryMatched?.has(right.id) ? 1 : 0;
    const leftDegree = degreeMap.get(left.id) ?? 0;
    const rightDegree = degreeMap.get(right.id) ?? 0;

    return rightSearch - leftSearch || rightDegree - leftDegree || left.name.localeCompare(right.name);
  });

  const totalNodes = prioritized.length;
  const truncated = totalNodes > MAX_RENDER_NODES;
  const subset = truncated ? buildRenderSubset(prioritized, MAX_RENDER_NODES) : prioritized;
  const idSet = new Set(subset.map((n) => n.id));
  const labelShare = subset.length > 460 ? 0.05 : subset.length > 320 ? 0.075 : 0.11;
  const labelCutoff = Math.min(subset.length, Math.max(10, Math.ceil(subset.length * labelShare)));
  const labelIds = new Set(subset.slice(0, labelCutoff).map((n) => n.id));
  const denseGraph = totalNodes > 180 || graph.edges.length > 320;

  const xfNodes: Node[] = subset.map((n) => {
    const ci = communities?.nodeCommunity.get(n.id) ?? -1;
    const cm = communities?.communities.find((c) => c.id === ci);
    const cl = cm?.label ?? (ci >= 0 ? `#${ci}` : null);
    const degree = degreeMap.get(n.id) ?? 0;
    const showLabel =
      queryMatched?.has(n.id) === true ||
      labelIds.has(n.id) ||
      degree >= (subset.length > 460 ? 15 : subset.length > 320 ? 12 : 8);
    const visualWeight = Math.min(1, Math.log2(degree + 1) / 3.2);

    return {
      id: n.id,
      type: "kg",
      position: { x: 0, y: 0 },
      data: {
        node: n,
        community: ci,
        communityLabel: cl,
        communityMethod: communities?.method ?? null,
        degree,
        showLabel,
        isSearchMatch: queryMatched?.has(n.id) === true,
        layoutDirection: direction,
        visualWeight,
      },
    };
  });

  const xfEdges: Edge[] = graph.edges
    .filter((e) => idSet.has(e.source) && idSet.has(e.target))
    .map((e) => {
      const style = getEdgeStyle(e.type);
      return {
        id: `${e.source}__${e.target}__${e.type}`,
        source: e.source,
        target: e.target,
        type: "default",
        style: {
          stroke: style.hex,
          strokeWidth: Math.max(0.7, style.width - 0.65),
          opacity: denseGraph ? 0.14 : 0.24,
          ...(style.dasharray ? { strokeDasharray: style.dasharray } : {}),
        },
        data: {
          baseOpacity: denseGraph ? 0.14 : 0.24,
          baseStrokeWidth: Math.max(0.7, style.width - 0.65),
        },
        animated: totalNodes < 80 && (e.type === "calls" || e.type === "subscribes" || e.type === "publishes"),
      };
    });

  return {
    nodes: xfNodes,
    edges: xfEdges,
    totalNodes,
    truncated,
    matchedNodeIds: idSet,
    searchMatchedAll: queryMatched,
  };
}

export function getNodeFile(node: KGNode): string {
  return node.filePath ?? node.file ?? "";
}
