"use client";

import React, { useMemo, useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  Panel,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
  type ReactFlowInstance,
  BackgroundVariant,
} from "@xyflow/react";
import {
  Search,
  Network,
  Code2,
  Info,
  Box,
  FileText,
  Layers,
  Sparkles,
  Hash,
  Tag,
  GitBranch,
  X,
  Check,
  RefreshCw,
  Loader2,
  ArrowUpRight,
  Clock3,
  CircleDot,
  Download,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { layoutGraph, type LayoutDirection } from "@/lib/layout/elk";
import { CodeViewerPanel } from "./_components/CodeViewerPanel";
import { buildKGSearchIndex, searchStats } from "@/lib/search/kg-search";
import {
  detectCommunities,
  communityColor,
  communityColorClass,
  type CommunityResult,
} from "@/lib/communities/louvain";
import { useGraphs, useGraph } from "./_components/use-kg";
import { SectionCard, StatPill, MiniFact, MetadataRow, GraphMetaBadge } from "./_components/mini-ui";
import {
  CanvasLoadingState, CanvasEmptyState, CanvasNoNodesState, CanvasErrorState,
  EmptyStage, SelectionGuidanceState, RailSkeleton,
} from "./_components/states";
import { ErrorFallback, LegendOverlay, CanvasToolbar } from "./_components/top-bar";
import {
  buildKGModel,
  KG_NODE_W,
  KG_NODE_H,
  type KGFilter,
} from "./_components/graph-model";
import {
  NODE_CATEGORY,
  NODE_TYPE_LABEL,
  getNodeTone,
  getEdgeStyle,
  uniqueLanguages,
  summarizeEdges,
} from "./_components/constants";
import type {
  GraphSummary,
  KGEdge,
  KGNode,
  KnowledgeGraph,
  PanelTab,
} from "./_components/types";
import {
  buildNodeHeuristicSummary,
  contextualPathLabel,
  deriveGraphDisplayMeta,
  formatTimestampLabel,
  graphSummaryDisplayLabel,
  getNodeDegreeMap,
  getTopConnectedNodes,
  nodeDisplayName,
  nodeSecondaryLabel,
  rankSearchResults,
  summarizeEdgeTypes,
} from "./_components/view-model";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { toPng } from "html-to-image";
import { useAgentTraversal, type AgentTraversalState } from "./_components/use-agent-traversal";
import { AskPanel } from "./_components/AskPanel";
import { TourPanel } from "./_components/TourPanel";

const ACTIVE_TAB_KEY = "testai.activeKgId";

type Direction = "TB" | "LR";
type GraphTaxonomy = "all" | "code" | "files" | "domain";
type FitMode = "overview" | "full";
type CanvasBounds = { x: number; y: number; width: number; height: number };

function getGraphWorkspaceTitle(displayMeta: ReturnType<typeof deriveGraphDisplayMeta>): string {
  return displayMeta.repoDisplayName ?? displayMeta.snapshotLabel ?? displayMeta.graphId ?? displayMeta.repoUrl ?? "Graph";
}

function countNodeTypes(nodes: KGNode[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const node of nodes) {
    const label = NODE_TYPE_LABEL[node.type] ?? node.type;
    counts[label] = (counts[label] ?? 0) + 1;
  }
  return counts;
}

function formatCount(value: number | null | undefined): string {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

function getActiveId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_TAB_KEY);
}

function setActiveId(id: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTIVE_TAB_KEY, id);
}

function graphOptionLabel(graph: GraphSummary): string {
  const base = graphSummaryDisplayLabel(graph);
  if (graph.node_count === 0) return `${base}  (empty)`;
  return base;
}

function shortText(value: string, limit = 30): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 1)}...`;
}

function taxonomyMatchesNode(node: KGNode, taxonomy: GraphTaxonomy): boolean {
  if (taxonomy === "all") return true;
  if (taxonomy === "files") return node.type === "file";
  return NODE_CATEGORY[node.type] === taxonomy;
}

function buildFilter(query: string, taxonomy: GraphTaxonomy, language: string | null): KGFilter {
  if (taxonomy === "files") {
    return {
      query,
      language,
      category: "all",
      types: new Set<KGNode["type"]>(["file"]),
    };
  }

  return {
    query,
    language,
    category: taxonomy === "all" ? "all" : taxonomy,
    types: new Set(),
  };
}

function formatEdgeTypeLabel(type: KGEdge["type"]): string {
  return type.replace(/_/g, " ");
}

function buildRelationItems(
  edges: KGEdge[],
  graph: KnowledgeGraph,
  getOtherNodeId: (edge: KGEdge) => string,
  degreeMap: Map<string, number>
) {
  return edges
    .map((edge) => {
      const nodeId = getOtherNodeId(edge);
      const node = graph.nodes.find((candidate) => candidate.id === nodeId);
      return node
        ? {
            edge,
            node,
            degree: degreeMap.get(node.id) ?? 0,
          }
        : null;
    })
    .filter(Boolean)
    .sort(
      (left, right) =>
        (right?.edge.weight ?? 0) - (left?.edge.weight ?? 0) ||
        (right?.degree ?? 0) - (left?.degree ?? 0) ||
        (left?.node.name ?? "").localeCompare(right?.node.name ?? "")
    ) as Array<{ edge: KGEdge; node: KGNode; degree: number }>;
}

function getCanvasFitOptions(nodeCount: number, mode: FitMode = "full") {
  if (mode === "overview") {
    return {
      padding: nodeCount > 260 ? 0.03 : nodeCount > 160 ? 0.04 : 0.05,
      duration: 460,
      maxZoom: nodeCount > 260 ? 0.92 : nodeCount > 160 ? 0.98 : 1.05,
    };
  }

  return {
    padding: nodeCount > 260 ? 0.065 : nodeCount > 160 ? 0.08 : 0.095,
    duration: 460,
    maxZoom: nodeCount > 260 ? 0.96 : nodeCount > 160 ? 1.02 : 1.08,
  };
}

function getNodeFrame(node: Node): CanvasBounds {
  const measured = node.measured as { width?: number; height?: number } | undefined;
  const width = Math.max(KG_NODE_W, measured?.width ?? KG_NODE_W);
  const height = Math.max(KG_NODE_H, measured?.height ?? KG_NODE_H);

  return {
    x: node.position.x,
    y: node.position.y,
    width,
    height,
  };
}

function getNodesBoundsSnapshot(nodes: Node[]): CanvasBounds | null {
  if (nodes.length === 0) return null;

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const node of nodes) {
    const frame = getNodeFrame(node);
    minX = Math.min(minX, frame.x);
    minY = Math.min(minY, frame.y);
    maxX = Math.max(maxX, frame.x + frame.width);
    maxY = Math.max(maxY, frame.y + frame.height);
  }

  return {
    x: minX,
    y: minY,
    width: Math.max(KG_NODE_W, maxX - minX),
    height: Math.max(KG_NODE_H, maxY - minY),
  };
}

function mergeBounds(...bounds: Array<CanvasBounds | null>): CanvasBounds | null {
  const available = bounds.filter(Boolean) as CanvasBounds[];
  if (available.length === 0) return null;

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const bound of available) {
    minX = Math.min(minX, bound.x);
    minY = Math.min(minY, bound.y);
    maxX = Math.max(maxX, bound.x + bound.width);
    maxY = Math.max(maxY, bound.y + bound.height);
  }

  return {
    x: minX,
    y: minY,
    width: Math.max(KG_NODE_W, maxX - minX),
    height: Math.max(KG_NODE_H, maxY - minY),
  };
}

function expandBounds(
  bounds: CanvasBounds,
  padding: { left: number; right: number; top: number; bottom: number }
): CanvasBounds {
  return {
    x: bounds.x - padding.left,
    y: bounds.y - padding.top,
    width: bounds.width + padding.left + padding.right,
    height: bounds.height + padding.top + padding.bottom,
  };
}

function getTrimmedOverviewBounds(nodes: Node[]): CanvasBounds | null {
  if (nodes.length === 0) return null;
  if (nodes.length < 18) return getNodesBoundsSnapshot(nodes);

  const trimRatio = nodes.length > 220 ? 0.16 : nodes.length > 140 ? 0.12 : 0.08;
  const centersX = nodes
    .map((node) => {
      const frame = getNodeFrame(node);
      return frame.x + frame.width / 2;
    })
    .sort((left, right) => left - right);
  const centersY = nodes
    .map((node) => {
      const frame = getNodeFrame(node);
      return frame.y + frame.height / 2;
    })
    .sort((left, right) => left - right);

  const lowIndex = Math.max(0, Math.floor((nodes.length - 1) * trimRatio));
  const highIndex = Math.max(lowIndex, Math.ceil((nodes.length - 1) * (1 - trimRatio)));
  const minCenterX = centersX[lowIndex] ?? centersX[0] ?? 0;
  const maxCenterX = centersX[highIndex] ?? centersX[centersX.length - 1] ?? minCenterX;
  const minCenterY = centersY[lowIndex] ?? centersY[0] ?? 0;
  const maxCenterY = centersY[highIndex] ?? centersY[centersY.length - 1] ?? minCenterY;

  return {
    x: minCenterX - KG_NODE_W * 0.9,
    y: minCenterY - KG_NODE_H * 0.9,
    width: Math.max(KG_NODE_W * 4, maxCenterX - minCenterX + KG_NODE_W * 1.8),
    height: Math.max(KG_NODE_H * 4, maxCenterY - minCenterY + KG_NODE_H * 1.8),
  };
}

function getNodeImportanceMetric(node: Node, key: "degree" | "visualWeight") {
  const data = node.data as { degree?: number; visualWeight?: number } | undefined;
  return key === "degree" ? data?.degree ?? 0 : data?.visualWeight ?? 0;
}

function getDefaultOverviewBounds(nodes: Node[], direction: Direction): CanvasBounds | null {
  const allBounds = getNodesBoundsSnapshot(nodes);
  if (!allBounds) return null;

  const coreCount = Math.min(72, Math.max(18, Math.round(nodes.length * 0.18)));
  const importantNodes = [...nodes]
    .sort(
      (left, right) =>
        getNodeImportanceMetric(right, "degree") - getNodeImportanceMetric(left, "degree") ||
        getNodeImportanceMetric(right, "visualWeight") - getNodeImportanceMetric(left, "visualWeight")
    )
    .slice(0, coreCount);

  const baseBounds = mergeBounds(
    getTrimmedOverviewBounds(nodes),
    getNodesBoundsSnapshot(importantNodes),
    allBounds.width < KG_NODE_W * 8 ? allBounds : null
  ) ?? allBounds;

  return expandBounds(
    baseBounds,
    direction === "LR"
      ? {
          left: KG_NODE_W * 0.95,
          right: KG_NODE_W * 2.35,
          top: KG_NODE_H * 1.15,
          bottom: KG_NODE_H * 1.5,
        }
      : {
          left: KG_NODE_W * 1.05,
          right: KG_NODE_W * 1.95,
          top: KG_NODE_H * 1.35,
          bottom: KG_NODE_H * 1.7,
        }
  );
}

function getFullCanvasBounds(nodes: Node[], direction: Direction): CanvasBounds | null {
  const allBounds = getNodesBoundsSnapshot(nodes);
  if (!allBounds) return null;

  return expandBounds(
    allBounds,
    direction === "LR"
      ? {
          left: KG_NODE_W * 0.8,
          right: KG_NODE_W * 2,
          top: KG_NODE_H * 1,
          bottom: KG_NODE_H * 1.45,
        }
      : {
          left: KG_NODE_W * 0.95,
          right: KG_NODE_W * 1.7,
          top: KG_NODE_H * 1.15,
          bottom: KG_NODE_H * 1.55,
        }
  );
}

function getSelectionFocusBounds(target: Node, direction: Direction) {
  const frame = getNodeFrame(target);
  const leftPadding = direction === "LR" ? KG_NODE_W * 1.5 : KG_NODE_W * 2;
  const rightPadding = direction === "LR" ? KG_NODE_W * 2.75 : KG_NODE_W * 2.6;
  const topPadding = direction === "LR" ? KG_NODE_H * 1.8 : KG_NODE_H * 2.2;
  const bottomPadding = direction === "LR" ? KG_NODE_H * 2 : KG_NODE_H * 2.5;

  return {
    x: frame.x - leftPadding,
    y: frame.y - topPadding,
    width: frame.width + leftPadding + rightPadding,
    height: frame.height + topPadding + bottomPadding,
  };
}



class GraphErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) return <ErrorFallback error={this.state.error} />;
    return this.props.children;
  }
}

export default function KnowledgeGraphPage() {
  const graphsQ = useGraphs();
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [taxonomy, setTaxonomy] = useState<GraphTaxonomy>("all");
  const [languageFilter, setLanguageFilter] = useState<string | null>(null);
  const [direction, setDirection] = useState<Direction>("LR");
  const [panelTab, setPanelTab] = useState<PanelTab>("details");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<{ path: string } | null>(null);
  const graphQ = useGraph(activeId);
  useEffect(() => {
    const graphs = graphsQ.data?.graphs ?? [];
    if (graphs.length === 0) return;

    const stored = getActiveId();
    const firstValid = graphs.find((g) => g.node_count > 0)?.id ?? graphs[0].id;
    // Stored id must point to a real (non-empty) graph; if the cached
    // selection is empty (e.g. half-built snapshot), fall back to the
    // first non-empty graph.  Prevents landing on a 0/0 snapshot.
    const storedIsValid =
      stored != null &&
      graphs.some((graph) => graph.id === stored && graph.node_count > 0);
    const nextId = storedIsValid ? stored : firstValid;
    if (nextId !== activeId) {
      setActiveId(nextId);
      setActiveIdState(nextId);
    }
  }, [activeId, graphsQ.data]);

  useEffect(() => {
    setQuery("");
    setTaxonomy("all");
    setLanguageFilter(null);
    setDirection("LR");
    setPanelTab("details");
    setSelectedNodeId(null);
    setViewingFile(null);
  }, [activeId]);

  const selectGraph = useCallback((id: string) => {
    setActiveId(id);
    setActiveIdState(id);
  }, []);

  const focusNode = useCallback((id: string | null) => {
    setSelectedNodeId(id);
    if (id) setPanelTab("details");
    setViewingFile(null);
  }, []);

  const activeSummary = useMemo(
    () => graphsQ.data?.graphs?.find((graph) => graph.id === activeId) ?? null,
    [activeId, graphsQ.data]
  );

  const graph = graphQ.data?.graph ?? null;
  const [communityResult, setCommunityResult] = useState<CommunityResult | null>(null);

  useEffect(() => {
    if (!graph) {
      setCommunityResult(null);
      return;
    }
    let cancelled = false;
    detectCommunities(graph.nodes, graph.edges).then((result) => {
      if (!cancelled) setCommunityResult(result);
    });
    return () => {
      cancelled = true;
    };
  }, [graph]);

  const filter = useMemo(() => buildFilter(query, taxonomy, languageFilter), [languageFilter, query, taxonomy]);
  const searchIndex = useMemo(() => (graph ? buildKGSearchIndex(graph.nodes) : null), [graph]);
  const model = useMemo(() => {
    if (!graph) return null;
    return buildKGModel(graph, filter, searchIndex, communityResult, direction);
  }, [communityResult, direction, filter, graph, searchIndex]);

  const searchPerf = useMemo(() => {
    if (!searchIndex || !query.trim()) return null;
    return searchStats(searchIndex, query);
  }, [query, searchIndex]);

  const availableLanguages = useMemo(() => (graph ? uniqueLanguages(graph.nodes) : []), [graph]);
  const nodeTypeCounts = useMemo(() => (graph ? countNodeTypes(graph.nodes) : {}), [graph]);
  const displayMeta = useMemo(() => deriveGraphDisplayMeta(graph, activeSummary), [activeSummary, graph]);
  const degreeMap = useMemo(() => (graph ? getNodeDegreeMap(graph) : new Map<string, number>()), [graph]);
  const filteredSearchIds = useMemo(() => {
    if (!graph || !query.trim()) return null;
    const matched = model?.searchMatchedAll ?? new Set<string>();
    return new Set(
      graph.nodes
        .filter((node) => matched.has(node.id))
        .filter((node) => taxonomyMatchesNode(node, taxonomy))
        .filter((node) => !languageFilter || node.language === languageFilter)
        .map((node) => node.id)
    );
  }, [graph, languageFilter, model?.searchMatchedAll, query, taxonomy]);
  const searchResults = useMemo(
    () => (graph ? rankSearchResults(graph, filteredSearchIds, query, 12) : []),
    [filteredSearchIds, graph, query]
  );

  const selectedNode = useMemo(
    () => graph?.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [graph, selectedNodeId]
  );

  const incoming = useMemo(
    () => graph?.edges.filter((edge) => edge.target === selectedNodeId) ?? [],
    [graph, selectedNodeId]
  );
  const outgoing = useMemo(
    () => graph?.edges.filter((edge) => edge.source === selectedNodeId) ?? [],
    [graph, selectedNodeId]
  );

  const traversedState = useAgentTraversal(graph);

  return (
    <div className="-m-8 flex h-[calc(100dvh-4rem)] flex-col bg-background text-foreground">
      <KnowledgeGraphTopBar
        graphs={graphsQ.data?.graphs ?? []}
        activeId={activeId}
        query={query}
        onQueryChange={setQuery}
        onSelectGraph={selectGraph}
        displayMeta={displayMeta}
        graphsLoading={graphsQ.isLoading}
        graphLoading={graphQ.isLoading && !graph}
      />

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_408px] overflow-hidden bg-zinc-950">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {activeId ? (
            <GraphSurface
              graph={graph}
              activeSummary={activeSummary}
              isLoading={graphQ.isLoading && !graph}
              isRefreshing={graphQ.isFetching && !!graph}
              isError={graphQ.isError}
              errorMessage={(graphQ.error as Error | undefined)?.message ?? null}
              onRetry={() => {
                void graphQ.refetch();
              }}
              model={model}
              query={query}
              taxonomy={taxonomy}
              onTaxonomyChange={setTaxonomy}
              languageFilter={languageFilter}
              onLanguageFilterChange={setLanguageFilter}
              availableLanguages={availableLanguages}
              direction={direction}
              onDirectionChange={setDirection}
              selectedNodeId={selectedNodeId}
              onSelectNode={focusNode}
              nodeTypeCounts={nodeTypeCounts}
              communityResult={communityResult}
              searchPerf={searchPerf}
              displayMeta={displayMeta}
              traversal={traversedState}
            />
          ) : (
            <EmptyStage
              isLoading={graphsQ.isLoading}
              hasGraphs={(graphsQ.data?.graphs?.length ?? 0) > 0}
              onSelectFirst={() => {
                const firstId = graphsQ.data?.graphs?.[0]?.id;
                if (firstId) selectGraph(firstId);
              }}
            />
          )}
        </div>

        <aside className="relative min-h-0 min-w-[408px] max-w-[408px] overflow-hidden border-l border-white/[0.08] bg-[linear-gradient(180deg,rgba(18,18,28,0.98),rgba(10,10,15,0.98))] shadow-[-24px_0_64px_rgba(0,0,0,0.34)]">
          <InfoRail
            graph={graph}
            isLoading={graphQ.isLoading && !graph}
            panelTab={panelTab}
            onTabChange={setPanelTab}
            selectedNode={selectedNode}
            selectedNodeId={selectedNodeId}
            incoming={incoming}
            outgoing={outgoing}
            communityResult={communityResult}
            searchQuery={query}
            searchResults={searchResults}
            searchPerf={searchPerf}
            displayMeta={displayMeta}
            degreeMap={degreeMap}
            onSelectNode={focusNode}
            onClearSelection={() => focusNode(null)}
            onViewFile={(path) => setViewingFile({ path })}
            traversal={traversedState}
          />
        </aside>
      </div>

      {viewingFile && activeId && (
        <CodeViewerPanel
          graphId={activeId}
          path={viewingFile.path}
          onClose={() => setViewingFile(null)}
        />
      )}
    </div>
  );
}

function KnowledgeGraphTopBar({
  graphs,
  activeId,
  query,
  onQueryChange,
  onSelectGraph,
  displayMeta,
  graphsLoading,
  graphLoading,
}: {
  graphs: GraphSummary[];
  activeId: string | null;
  query: string;
  onQueryChange: (value: string) => void;
  onSelectGraph: (id: string) => void;
  displayMeta: ReturnType<typeof deriveGraphDisplayMeta>;
  graphsLoading: boolean;
  graphLoading: boolean;
}) {
  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-white/[0.06] bg-background/85 px-5 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="text-neutral-500">Explore</span>
        <span className="text-neutral-700">/</span>
        <span className="font-semibold text-neutral-100">Knowledge Graph</span>
      </div>

      <Select value={activeId ?? undefined} onValueChange={onSelectGraph}>
        <SelectTrigger className="h-9 min-w-[230px] border-white/[0.08] bg-white/[0.03] px-3 text-[11px] text-neutral-100 shadow-none hover:bg-white/[0.05] focus:ring-emerald-400/10">
          <SelectValue placeholder={graphsLoading ? "Loading graphs..." : "Select graph"} />
        </SelectTrigger>
        <SelectContent className="border-white/[0.08] bg-card text-neutral-100">
          {[...graphs]
            .sort((a, b) => {
              // Non-empty graphs first; then by indexed_at desc; then by id.
              const aEmpty = a.node_count === 0 ? 1 : 0;
              const bEmpty = b.node_count === 0 ? 1 : 0;
              if (aEmpty !== bEmpty) return aEmpty - bEmpty;
              const ai = a.indexed_at ?? "";
              const bi = b.indexed_at ?? "";
              if (ai !== bi) return ai < bi ? 1 : -1;
              return a.id < b.id ? 1 : -1;
            })
            .map((graph) => (
              <SelectItem key={graph.id} value={graph.id}>
                {graphOptionLabel(graph)}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>

      <div className="relative min-w-[240px] flex-1 max-w-[420px]">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-600" strokeWidth={1.8} />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search nodes, files, types..."
          className="h-9 w-full rounded-xl border border-white/[0.08] bg-white/[0.03] pl-9 pr-8 text-[11px] font-mono text-neutral-200 placeholder:text-neutral-600"
        />
        {query ? (
          <button
            onClick={() => onQueryChange("")}
            className="absolute right-2.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-md text-neutral-500 transition-colors hover:bg-white/[0.06] hover:text-neutral-200"
            aria-label="Clear search"
            type="button"
          >
            <X className="h-3 w-3" strokeWidth={1.6} />
          </button>
        ) : (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-white/[0.06] bg-white/[0.03] px-1.5 py-0.5 text-[8px] font-mono text-neutral-600">
            /
          </span>
        )}
      </div>

      <div className="ml-auto flex items-center gap-2">
        {displayMeta.repoDisplayName && (
          <GraphMetaBadge icon={GitBranch} value={displayMeta.repoDisplayName} accent />
        )}
        {displayMeta.branch && <GraphMetaBadge label="branch" value={displayMeta.branch} />}
        {displayMeta.versionLabel && <GraphMetaBadge label="version" value={displayMeta.versionLabel} />}
        {displayMeta.indexedAt && (
          <GraphMetaBadge icon={Clock3} value={formatTimestampLabel(displayMeta.indexedAt) ?? displayMeta.indexedAt} />
        )}
        <button
          type="button"
          disabled
          className="hidden rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-[10px] font-semibold tracking-[0.02em] text-neutral-500 opacity-70 lg:inline-flex"
          title="Re-index runs inside the sandbox via kg_refresh tool"
        >
          {graphLoading ? (
            <>
              <Loader2 className="mr-1.5 h-3 w-3 animate-spin" strokeWidth={1.8} />
              Loading...
            </>
          ) : (
            <>
              <RefreshCw className="mr-1.5 h-3 w-3" strokeWidth={1.8} />
              Pipeline re-index
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function GraphSurface({
  graph,
  activeSummary,
  isLoading,
  isRefreshing,
  isError,
  errorMessage,
  onRetry,
  model,
  query,
  taxonomy,
  onTaxonomyChange,
  languageFilter,
  onLanguageFilterChange,
  availableLanguages,
  direction,
  onDirectionChange,
  selectedNodeId,
  onSelectNode,
  nodeTypeCounts,
  communityResult,
  searchPerf,
  displayMeta,
  traversal,
}: {
  graph: KnowledgeGraph | null;
  activeSummary: GraphSummary | null;
  isLoading: boolean;
  isRefreshing: boolean;
  isError: boolean;
  errorMessage: string | null;
  onRetry: () => void;
  model: ReturnType<typeof buildKGModel> | null;
  query: string;
  taxonomy: GraphTaxonomy;
  onTaxonomyChange: (value: GraphTaxonomy) => void;
  languageFilter: string | null;
  onLanguageFilterChange: (value: string | null) => void;
  availableLanguages: Array<[string, number]>;
  direction: Direction;
  onDirectionChange: (value: Direction) => void;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  nodeTypeCounts: Record<string, number>;
  communityResult: CommunityResult | null;
  searchPerf: { matched: number; timeMs: number; terms: number } | null;
  displayMeta: ReturnType<typeof deriveGraphDisplayMeta>;
  traversal: AgentTraversalState;
}) {
  const nodeCount = graph?.metadata?.nodeCount ?? graph?.nodes.length ?? activeSummary?.node_count ?? 0;
  const edgeCount = graph?.metadata?.edgeCount ?? graph?.edges.length ?? activeSummary?.edge_count ?? 0;
  const fileCount =
    Number(graph?.metadata?.totalFiles ?? 0) || graph?.nodes.filter((node) => node.type === "file").length || 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <GraphStatStrip
        nodeCount={nodeCount}
        edgeCount={edgeCount}
        fileCount={fileCount}
        communityCount={communityResult?.count ?? 0}
        versionLabel={displayMeta.versionLabel}
        indexedAt={displayMeta.indexedAt}
        graphId={displayMeta.graphId}
        isRefreshing={isRefreshing}
      />

      <div className="relative flex-1 overflow-hidden bg-[radial-gradient(circle_at_18%_28%,rgba(52,211,153,0.08),transparent_28%),radial-gradient(circle_at_78%_22%,rgba(96,165,250,0.06),transparent_24%),radial-gradient(circle_at_50%_82%,rgba(167,139,250,0.05),transparent_24%),#0a0a0f]">
        {graph && model ? (
          <>
            <ReactFlowProvider>
              <GraphErrorBoundary>
                <KGCanvas
                  model={model}
                  graph={graph}
                  direction={direction}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={onSelectNode}
                  traversal={traversal}
                />
              </GraphErrorBoundary>
            </ReactFlowProvider>

            <LegendOverlay
              nodeTypeCounts={nodeTypeCounts}
              communityCount={communityResult?.count ?? 0}
            />

            <CanvasToolbar
              taxonomy={taxonomy}
              onTaxonomyChange={(v: string) => onTaxonomyChange(v as GraphTaxonomy)}
              direction={direction}
              onDirectionChange={(v: string) => onDirectionChange(v as Direction)}
              availableLanguages={availableLanguages}
              languageFilter={languageFilter}
              onLanguageFilterChange={onLanguageFilterChange}
              query={query}
              matchedCount={model.totalNodes}
              totalNodes={graph.nodes.length}
              truncated={model.truncated}
              searchPerf={searchPerf}
            />
          </>
        ) : null}

        <AnimatePresence>
          {isLoading && !graph ? <CanvasLoadingState key="loading" /> : null}
          {!isLoading && !isError && !graph ? <CanvasEmptyState key="empty" /> : null}
          {!isLoading && !!graph && graph.nodes.length === 0 ? <CanvasNoNodesState key="no-nodes" /> : null}
          {isError ? <CanvasErrorState key="error" message={errorMessage} onRetry={onRetry} /> : null}
        </AnimatePresence>
      </div>
    </div>
  );
}

function GraphStatStrip({
  nodeCount,
  edgeCount,
  fileCount,
  communityCount,
  versionLabel,
  indexedAt,
  graphId,
  isRefreshing,
}: {
  nodeCount: number;
  edgeCount: number;
  fileCount: number;
  communityCount: number;
  versionLabel: string | null;
  indexedAt: string | null;
  graphId: string | null;
  isRefreshing: boolean;
}) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-white/[0.06] bg-surface/45 px-5 py-2.5 backdrop-blur-sm">
      <StatPill label="nodes" value={formatCount(nodeCount)} />
      <StatPill label="edges" value={formatCount(edgeCount)} />
      <StatPill label="files" value={formatCount(fileCount)} />
      <StatPill label="communities" value={formatCount(communityCount)} accent />

      {indexedAt && <StatPill label="indexed" value={formatTimestampLabel(indexedAt) ?? indexedAt} />}
      {graphId && <StatPill label="graph" value={shortText(graphId, 16)} />}

      <div className="ml-auto flex items-center gap-2 text-[10px] font-mono text-emerald-300">
        <motion.span
          className="h-1.5 w-1.5 rounded-full bg-emerald-400"
          animate={{ opacity: [1, 0.35, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        {versionLabel ?? "codegraph"}
        {isRefreshing ? (
          <span className="inline-flex items-center gap-1 text-neutral-500">
            <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.8} />
            refreshing
          </span>
        ) : null}
      </div>
    </div>
  );
}

function KGCanvas({
  model,
  graph,
  direction,
  selectedNodeId,
  onSelectNode,
  traversal,
}: {
  model: ReturnType<typeof buildKGModel>;
  graph: KnowledgeGraph;
  direction: Direction;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  traversal: AgentTraversalState;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(model.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(model.edges);
  const [layoutStatus, setLayoutStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [layoutKey, setLayoutKey] = useState(0);
  const [layoutRevision, setLayoutRevision] = useState(0);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<Node, Edge> | null>(null);
  const [showTraversal, setShowTraversal] = useState(true);
  const graphRef = useRef<HTMLDivElement>(null);
  const selectedContextIds = useMemo(() => {
    if (!selectedNodeId) return null;

    const contextIds = new Set<string>([selectedNodeId]);
    for (const edge of edges) {
      if (edge.source === selectedNodeId) contextIds.add(edge.target);
      if (edge.target === selectedNodeId) contextIds.add(edge.source);
    }

    return contextIds;
  }, [edges, selectedNodeId]);

  const exportPng = useCallback(async () => {
    if (!graphRef.current) return;
    try {
      const dataUrl = await toPng(graphRef.current, {
        backgroundColor: "#0a0a0f",
        pixelRatio: 2,
        filter: (el) => {
          try {
            if (el.classList?.contains?.("react-flow__minimap")) return false;
            if (el.classList?.contains?.("react-flow__controls")) return false;
          } catch {}
          return true;
        },
      });
      const link = document.createElement("a");
      link.download = `knowledge-graph-${(graph.metadata?.graphId ?? "export").slice(0, 12)}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error("[KG] Export PNG failed", err);
    }
  }, [graph]);

  const renderedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...(node.data as Record<string, unknown>),
          isContextNode: selectedContextIds?.has(node.id) ?? false,
          isDimmed: Boolean(selectedContextIds) && !selectedContextIds?.has(node.id),
          isTraversed: showTraversal && traversal.traversedNodeIds.has(node.id),
        },
      })),
    [nodes, selectedContextIds, showTraversal, traversal.traversedNodeIds]
  );

  const renderedEdges = useMemo(
    () =>
      edges.map((edge) => {
        const edgeData = (edge.data ?? {}) as {
          baseOpacity?: number;
          baseStrokeWidth?: number;
        };
        const baseOpacity = edgeData.baseOpacity ?? 0.24;
        const baseStrokeWidth = edgeData.baseStrokeWidth ?? 0.85;
        const isDirectlyConnected = selectedNodeId ? edge.source === selectedNodeId || edge.target === selectedNodeId : false;
        const isContextEdge = selectedContextIds
          ? selectedContextIds.has(edge.source) && selectedContextIds.has(edge.target)
          : true;
        const isTraversedEdge = showTraversal && traversal.traversedEdgeIds.has(`${edge.source}->${edge.target}`);

        return {
          ...edge,
          animated: isTraversedEdge,
          style: {
            ...edge.style,
            opacity: isTraversedEdge
              ? 0.75
              : selectedContextIds
                ? isDirectlyConnected
                  ? 0.82
                  : isContextEdge
                    ? Math.max(0.18, baseOpacity)
                    : 0.06
                : baseOpacity,
            strokeWidth: isTraversedEdge
              ? baseStrokeWidth + 0.5
              : selectedContextIds
                ? isDirectlyConnected
                  ? baseStrokeWidth + 0.65
                  : isContextEdge
                    ? baseStrokeWidth
                    : Math.max(0.5, baseStrokeWidth - 0.3)
                : baseStrokeWidth,
            stroke: isTraversedEdge ? "#34d399" : undefined,
          },
        };
      }),
    [edges, selectedContextIds, selectedNodeId, showTraversal, traversal.traversedEdgeIds]
  );

  const fitCanvas = useCallback(
    (mode: FitMode) => {
      if (!flowInstance) return;

      const flowNodes = flowInstance.getNodes();
      if (flowNodes.length === 0) return;

      const bounds =
        mode === "overview"
          ? getDefaultOverviewBounds(flowNodes, direction)
          : getFullCanvasBounds(flowNodes, direction);

      if (bounds) {
        void flowInstance.fitBounds(bounds, getCanvasFitOptions(flowNodes.length, mode));
        return;
      }

      void flowInstance.fitView(getCanvasFitOptions(flowNodes.length, mode));
    },
    [direction, flowInstance]
  );

  useEffect(() => {
    let cancelled = false;
    setLayoutStatus("loading");
    setNodes(model.nodes);
    setEdges(model.edges);

    layoutGraph(model.nodes, model.edges, {
      direction: direction as LayoutDirection,
      nodeWidth: KG_NODE_W,
      nodeHeight: KG_NODE_H,
      nodeNodeBetweenLayers: direction === "LR" ? 22 : 26,
      nodeNode: direction === "LR" ? 12 : 10,
      padding: 18,
      thoroughness: 3,
      edgeRouting: "SPLINES",
    })
      .then((result) => {
        if (cancelled) return;
        setNodes(result.nodes);
        setEdges(result.edges);
        setLayoutStatus("ready");
        setLayoutKey((value) => value + 1);
      })
      .catch((error) => {
        if (cancelled) return;
        console.error("[KG] layout failed", error);
        setLayoutStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [direction, layoutRevision, model, setEdges, setNodes]);

  useEffect(() => {
    if (!selectedNodeId || !flowInstance || layoutStatus !== "ready") return;
    const target = flowInstance.getNode(selectedNodeId) ?? nodes.find((node) => node.id === selectedNodeId);
    if (!target) return;

    const frame = window.requestAnimationFrame(() => {
      void flowInstance.fitBounds(getSelectionFocusBounds(target, direction), {
        duration: 420,
        padding: nodes.length > 140 ? 0.12 : 0.1,
      });
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [direction, flowInstance, layoutStatus, nodes, selectedNodeId]);

  useEffect(() => {
    if (!flowInstance || layoutStatus !== "ready" || selectedNodeId) return;

    const frame = window.requestAnimationFrame(() => {
      fitCanvas("overview");
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [fitCanvas, flowInstance, layoutStatus, selectedNodeId]);

  return (
    <div ref={graphRef} className="absolute inset-0">
      <ReactFlow
        key={layoutKey}
        nodes={renderedNodes}
        edges={renderedEdges}
        nodeTypes={NODE_TYPES}
        onInit={setFlowInstance}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        onSelectionChange={({ nodes: selectedNodes }) => {
          const nextSelectedId = selectedNodes[0]?.id ?? null;
          if (!nextSelectedId || nextSelectedId === selectedNodeId) return;
          onSelectNode(nextSelectedId);
        }}
        onPaneClick={() => onSelectNode(null)}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        selectionOnDrag={false}
        onlyRenderVisibleElements
        minZoom={0.18}
        maxZoom={2.2}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "default" }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(255,255,255,0.04)" />

        <Controls
          position="bottom-left"
          showInteractive={false}
          className="!mb-3 !ml-3 !rounded-2xl !border !border-white/[0.08] !bg-zinc-950/86 !shadow-none"
        />

        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          maskColor="rgba(10,10,15,0.72)"
          nodeColor={(reactFlowNode) => {
            try {
              const data = reactFlowNode.data as {
                node: KGNode;
                community?: number;
              };
              const community = data.community ?? -1;
              if (community >= 0) return communityColor(community);
              return getNodeTone(data.node.type).hex;
            } catch {
              return "#34d399";
            }
          }}
          style={{
            width: 136,
            height: 92,
            background: "rgba(16, 16, 24, 0.88)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 16,
            opacity: 0.72,
            marginBottom: 12,
            marginRight: 12,
          }}
        />

        <Panel position="top-left" className="!m-3 !pointer-events-none">
          <AnimatePresence>
            {layoutStatus === "loading" ? (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="rounded-xl border border-white/[0.06] bg-zinc-950/38 px-3 py-1.5 text-[10px] font-mono text-neutral-400 backdrop-blur-md"
              >
                <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 align-middle" />
                laying out graphâ€¦
              </motion.div>
            ) : null}
            {layoutStatus === "error" ? (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-1.5 text-[10px] font-mono text-rose-300 backdrop-blur-md"
              >
                layout error
              </motion.div>
            ) : null}
          </AnimatePresence>
        </Panel>
      </ReactFlow>

      <div className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-2xl border border-white/[0.08] bg-zinc-950/88 p-1.5 backdrop-blur-xl">
        <button
          type="button"
          onClick={() => fitCanvas("full")}
          className="rounded-xl border border-transparent px-3 py-1.5 text-[10px] font-medium text-neutral-300 transition-colors hover:border-white/[0.08] hover:bg-white/[0.04] hover:text-neutral-100"
        >
          Zoom to fit
        </button>
        <button
          type="button"
          onClick={() => setLayoutRevision((value) => value + 1)}
          className="rounded-xl border border-transparent px-3 py-1.5 text-[10px] font-medium text-neutral-300 transition-colors hover:border-white/[0.08] hover:bg-white/[0.04] hover:text-neutral-100"
        >
          Auto-layout
        </button>
        <div className="h-4 w-px bg-white/[0.08]" />
        <button
          type="button"
          onClick={() => setShowTraversal((v) => !v)}
          className={cn(
            "rounded-xl border px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.18em] transition-colors",
            showTraversal && traversal.events.length > 0
              ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-300"
              : "border-white/[0.06] text-neutral-500"
          )}
        >
          <span className="flex items-center gap-1.5">
            <Waypoints className="h-3 w-3" strokeWidth={1.8} />
            Traversal
            {traversal.events.length > 0 ? (
              <span className="ml-0.5 rounded-full bg-emerald-500/20 px-1.5 text-[8px]">
                {traversal.events.length}
              </span>
            ) : null}
          </span>
        </button>
        <button
          type="button"
          onClick={exportPng}
          className="rounded-xl border border-white/[0.06] px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-neutral-500 transition-colors hover:border-white/[0.1] hover:text-neutral-200"
        >
          <Download className="mr-1 inline-block h-3 w-3" strokeWidth={1.8} />
          PNG
        </button>
      </div>
    </div>
  );
}

const NODE_TYPES: NodeTypes = { kg: KGNodeView };

function KGNodeView({ data, selected }: NodeProps) {
  const nodeData = data as {
    node: KGNode;
    community: number;
    communityLabel: string | null;
    degree: number;
    showLabel: boolean;
    isSearchMatch: boolean;
    layoutDirection: Direction;
    visualWeight: number;
    isContextNode?: boolean;
    isDimmed?: boolean;
    isTraversed?: boolean;
  };
  const node = nodeData.node;
  const tone = getNodeTone(node.type);
  const label = NODE_TYPE_LABEL[node.type] ?? node.type;
  const displayName = nodeDisplayName(node);
  const hasCommunity = nodeData.community >= 0;
  const targetPosition = nodeData.layoutDirection === "LR" ? Position.Left : Position.Top;
  const sourcePosition = nodeData.layoutDirection === "LR" ? Position.Right : Position.Bottom;
  const visualDiameter = Math.max(
    node.type === "file" ? 8 : 10,
    Math.min(22, 9 + Math.round(nodeData.visualWeight * 9) + (nodeData.isSearchMatch ? 2 : 0) + (nodeData.isContextNode ? 1 : 0) + (nodeData.isTraversed ? 1 : 0))
  );

  return (
    <div className="relative flex h-[50px] w-[72px] flex-col items-center justify-start pt-1 transition-opacity duration-200" style={{ opacity: nodeData.isDimmed ? 0.3 : 1 }}>
      <Handle type="target" position={targetPosition} className="!h-1.5 !w-1.5 !border-0 !bg-white/0" />
      <Handle type="source" position={sourcePosition} className="!h-1.5 !w-1.5 !border-0 !bg-white/0" />

      <div
          className={cn(
            "relative flex items-center justify-center rounded-full border transition-all duration-200",
            tone.border,
            nodeData.isSearchMatch && "shadow-[0_0_0_4px_rgba(52,211,153,0.08)]",
            nodeData.isTraversed && "shadow-[0_0_0_4px_rgba(52,211,153,0.18)]",
            selected ? "scale-[1.08] ring-1 ring-white/35" : nodeData.isContextNode ? "scale-[1.03]" : "scale-100"
          )}
        style={{
          width: visualDiameter,
          height: visualDiameter,
          background: hasCommunity ? `${communityColor(nodeData.community)}1f` : "rgba(255,255,255,0.04)",
          boxShadow: selected ? `0 0 0 8px ${tone.hex}12` : nodeData.isTraversed ? "0 0 0 6px rgba(52,211,153,0.1)" : undefined,
        }}
      >
        <span className={cn("h-2 w-2 rounded-full", tone.dot)} />
        {nodeData.isTraversed ? (
          <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5 items-center justify-center">
            <span className="h-2 w-2 animate-ping rounded-full bg-emerald-400/40" />
            <span className="absolute h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
        ) : null}
        {hasCommunity ? (
          <span className={cn("absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border border-border", communityColorClass(nodeData.community))} />
        ) : null}
      </div>

      {nodeData.showLabel ? (
        <div className="mt-1 max-w-full text-center">
          <div className={cn("truncate px-1 text-[8px] font-medium leading-none", selected ? "text-neutral-50" : nodeData.isSearchMatch || nodeData.isContextNode ? "text-neutral-200" : nodeData.isTraversed ? "text-emerald-200" : "text-neutral-500")}>
            {displayName}
          </div>
          <div className="mt-0.5 truncate px-1 text-[6.5px] font-mono uppercase tracking-[0.18em] text-neutral-700">{label}</div>
        </div>
      ) : null}
    </div>
  );
}

function InfoRail({
  graph,
  isLoading,
  panelTab,
  onTabChange,
  selectedNode,
  selectedNodeId,
  incoming,
  outgoing,
  communityResult,
  searchQuery,
  searchResults,
  searchPerf,
  displayMeta,
  degreeMap,
  onSelectNode,
  onClearSelection,
  onViewFile,
  traversal,
}: {
  graph: KnowledgeGraph | null;
  isLoading: boolean;
  panelTab: PanelTab;
  onTabChange: (tab: PanelTab) => void;
  selectedNode: KGNode | null;
  selectedNodeId: string | null;
  incoming: KGEdge[];
  outgoing: KGEdge[];
  communityResult: CommunityResult | null;
  searchQuery: string;
  searchResults: ReturnType<typeof rankSearchResults>;
  searchPerf: { matched: number; timeMs: number; terms: number } | null;
  displayMeta: ReturnType<typeof deriveGraphDisplayMeta>;
  degreeMap: Map<string, number>;
  onSelectNode: (id: string | null) => void;
  onClearSelection: () => void;
  onViewFile: (path: string) => void;
  traversal: AgentTraversalState;
}) {
  const tabs: PanelTab[] = ["details", "overview", "communities", "ask", "tour"];
  const graphTitle = getGraphWorkspaceTitle(displayMeta);
  const headerTitle = selectedNode ? nodeDisplayName(selectedNode) : graphTitle;
  const headerEyebrow = selectedNode ? `Selected ${NODE_TYPE_LABEL[selectedNode.type] ?? selectedNode.type}` : "Persistent inspector";
  const selectedTone = selectedNode ? getNodeTone(selectedNode.type) : null;
  const selectedSummary = selectedNode ? buildNodeHeuristicSummary(selectedNode, incoming.length, outgoing.length) : null;
  const selectedFile = selectedNode ? selectedNode.filePath ?? selectedNode.file ?? null : null;
  const selectedDegree = selectedNodeId ? degreeMap.get(selectedNodeId) ?? 0 : 0;
  const headerSubtitle = selectedNode
    ? nodeSecondaryLabel(selectedNode)
    : [
        displayMeta.snapshotLabel && displayMeta.snapshotLabel !== graphTitle ? displayMeta.snapshotLabel : null,
        displayMeta.branch ? `branch ${displayMeta.branch}` : null,
        displayMeta.versionLabel,
        formatTimestampLabel(displayMeta.indexedAt),
      ]
        .filter(Boolean)
        .join(" Â· ") || displayMeta.repoUrl || displayMeta.graphId || graphTitle;

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      <div className="border-b border-white/[0.06] bg-white/[0.01] px-4 py-4">
        <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">{headerEyebrow}</div>
        <div className="mt-2 flex items-center gap-2">
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-xl border bg-white/[0.03]",
              selectedTone ? selectedTone.border : "border-white/[0.06]"
            )}
          >
            <Network className={cn("h-4 w-4", selectedTone ? selectedTone.accent : "text-emerald-300")} strokeWidth={1.6} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-neutral-100">{headerTitle}</div>
            <div className="truncate text-[10px] font-mono text-neutral-500">{headerSubtitle}</div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "rounded-full border px-2.5 py-1 text-[8px] font-mono uppercase tracking-[0.2em]",
              selectedNode
                ? selectedTone
                  ? `${selectedTone.border} ${selectedTone.bg} ${selectedTone.accent}`
                  : "border-emerald-400/20 bg-emerald-500/10 text-emerald-200"
                : "border-white/[0.06] bg-white/[0.03] text-neutral-400"
            )}
          >
            {selectedNode ? "selected node active" : "workspace overview"}
          </span>
          {selectedNode ? (
            <button
              type="button"
              onClick={onClearSelection}
              className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 text-[8px] font-mono uppercase tracking-[0.18em] text-neutral-400 transition-colors hover:border-white/[0.1] hover:bg-white/[0.05] hover:text-neutral-100"
            >
              Clear selection
            </button>
          ) : (
            <span className="rounded-full border border-white/[0.06] px-2.5 py-1 text-[8px] font-mono uppercase tracking-[0.18em] text-neutral-500">
              Click any node to inspect
            </span>
          )}
        </div>

        {!selectedNode && traversal.isRunning && traversal.events.length > 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-3 rounded-2xl border border-emerald-400/15 bg-emerald-500/8 px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-[10px] font-mono font-medium text-emerald-200">Agent traversing graph</span>
              <span className="ml-auto rounded-full border border-emerald-400/20 px-2 py-0.5 text-[8px] font-mono text-emerald-300">
                {traversal.events.length} hits
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {traversal.events.slice(0, 5).map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => onSelectNode(ev.nodeId)}
                  className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2 py-1 text-[8px] font-mono text-neutral-400 transition-colors hover:border-white/[0.1] hover:text-neutral-100"
                >
                  {ev.nodeName}
                </button>
              ))}
              {traversal.events.length > 5 ? (
                <span className="px-2 py-1 text-[8px] font-mono text-neutral-600">+{traversal.events.length - 5} more</span>
              ) : null}
            </div>
          </motion.div>
        ) : null}

        {selectedNode && selectedSummary ? (
          <motion.div
            key={`rail-focus-${selectedNode.id}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className={cn(
              "mt-3 rounded-2xl border px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]",
              selectedTone ? selectedTone.border : "border-white/[0.06]",
              "bg-white/[0.03]"
            )}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={cn("rounded-full px-2 py-1 text-[8px] font-mono uppercase tracking-[0.2em]", selectedTone ? `${selectedTone.bg} ${selectedTone.accent}` : "bg-white/[0.04] text-neutral-300")}>
                node focus
              </span>
              <span className="rounded-full border border-white/[0.06] px-2 py-1 text-[8px] font-mono uppercase tracking-[0.18em] text-neutral-400">
                {formatCount(selectedDegree)} total links
              </span>
              {selectedFile ? (
                <span className="truncate rounded-full border border-white/[0.06] px-2 py-1 text-[8px] font-mono text-neutral-500">
                  {contextualPathLabel(selectedFile, 2) ?? selectedFile}
                </span>
              ) : null}
            </div>

            <p className="mt-2 text-[10.5px] leading-5 text-neutral-300">{selectedSummary}</p>

            <div className="mt-3 grid grid-cols-3 gap-2">
              <MiniFact label="Inbound" value={formatCount(incoming.length)} />
              <MiniFact label="Outbound" value={formatCount(outgoing.length)} />
              <MiniFact label="Degree" value={formatCount(selectedDegree)} />
            </div>
          </motion.div>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center border-b border-white/[0.06] px-2">
        {tabs.map((tab) => {
          const active = tab === panelTab;
          const label = tab === "details" ? "Details" : tab === "overview" ? "Overview" : tab === "ask" ? "Ask" : tab === "tour" ? "Tour" : "Communities";
          return (
            <button
              key={tab}
              type="button"
              onClick={() => onTabChange(tab)}
              className={cn(
                "-mb-px flex-1 border-b px-2.5 py-3 text-[9px] font-semibold uppercase tracking-[0.24em] transition-colors",
                active ? "border-emerald-400 text-neutral-100" : "border-transparent text-neutral-500 hover:text-neutral-200"
              )}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading && !graph ? (
          <RailSkeleton />
        ) : !graph ? (
          <SelectionGuidanceState
            title="Select a graph to inspect"
            body="Choose a knowledge graph from the compact top-bar switcher to populate the canvas and right rail."
          />
        ) : panelTab === "details" ? (
          <DetailsPanel
            graph={graph}
            selectedNode={selectedNode}
            selectedNodeId={selectedNodeId}
            incoming={incoming}
            outgoing={outgoing}
            communityResult={communityResult}
            displayMeta={displayMeta}
            searchQuery={searchQuery}
            searchResults={searchResults}
            searchPerf={searchPerf}
            onSelectNode={onSelectNode}
            onClearSelection={onClearSelection}
            onViewFile={onViewFile}
            degreeMap={degreeMap}
          />
        ) : panelTab === "overview" ? (
          <OverviewPanel graph={graph} communityResult={communityResult} displayMeta={displayMeta} onSelectNode={onSelectNode} />
        ) : panelTab === "ask" ? (
          <AskPanel graph={graph} onFocusNode={(nodeId) => { onSelectNode(nodeId); onTabChange("details"); }} />
        ) : panelTab === "tour" ? (
          <TourPanel graph={graph} onFocusNode={(nodeId) => { onSelectNode(nodeId); onTabChange("details"); }} />
        ) : (
          <CommunitiesPanel graph={graph} communities={communityResult} onSelectNode={onSelectNode} />
        )}
      </div>
    </div>
  );
}

function DetailsPanel({
  graph,
  selectedNode,
  selectedNodeId,
  incoming,
  outgoing,
  communityResult,
  displayMeta,
  searchQuery,
  searchResults,
  searchPerf,
  onSelectNode,
  onClearSelection,
  onViewFile,
  degreeMap,
}: {
  graph: KnowledgeGraph;
  selectedNode: KGNode | null;
  selectedNodeId: string | null;
  incoming: KGEdge[];
  outgoing: KGEdge[];
  communityResult: CommunityResult | null;
  displayMeta: ReturnType<typeof deriveGraphDisplayMeta>;
  searchQuery: string;
  searchResults: ReturnType<typeof rankSearchResults>;
  searchPerf: { matched: number; timeMs: number; terms: number } | null;
  onSelectNode: (id: string | null) => void;
  onClearSelection: () => void;
  onViewFile: (path: string) => void;
  degreeMap: Map<string, number>;
}) {
  const selectedCommunityId = selectedNode ? communityResult?.nodeCommunity.get(selectedNode.id) ?? null : null;
  const selectedCommunity =
    selectedCommunityId === null ? null : communityResult?.communities.find((community) => community.id === selectedCommunityId) ?? null;
  const communityLabel = selectedCommunity?.label ?? null;

  return (
    <div className="space-y-4">
      {selectedNode ? (
        <NodeDetails
          node={selectedNode}
          incoming={incoming}
          outgoing={outgoing}
          graph={graph}
          communityMeta={
            selectedCommunity
              ? {
                  id: selectedCommunity.id,
                  label: selectedCommunity.label,
                  nodeIds: selectedCommunity.nodes,
                }
              : null
          }
          degree={degreeMap.get(selectedNode.id) ?? 0}
          onClear={onClearSelection}
          onSelectNode={onSelectNode}
          onViewFile={onViewFile}
          degreeMap={degreeMap}
        />
      ) : (
        <>
          <SelectionGuidanceState
            title="No node selected"
            body={
              searchQuery.trim()
                ? "Select a search hit above or click any node on the canvas to inspect its metadata, callers, and dependencies."
                : "Click any node on the graph to open its metadata, heuristic summary, related context, and source actions here."
            }
          />
          <ProjectSnapshotPanel graph={graph} communityResult={communityResult} displayMeta={displayMeta} onSelectNode={onSelectNode} />
        </>
      )}

      {searchQuery.trim() ? (
        <SectionCard>
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">Search results</div>
              <div className="mt-1 text-[11px] text-neutral-300">
                {formatCount(searchResults.length)} matches for <span className="font-mono text-emerald-300">â€œ{searchQuery}â€</span>
                {searchPerf ? <span className="ml-1 text-neutral-500">in {searchPerf.timeMs.toFixed(1)}ms</span> : null}
              </div>
            </div>
            {searchResults.length > 0 ? (
              <span className="rounded-full border border-white/[0.06] px-2 py-1 text-[8px] font-mono uppercase tracking-[0.18em] text-neutral-500">
                click to focus
              </span>
            ) : null}
          </div>

          {searchResults.length === 0 ? (
            <p className="text-[11px] text-neutral-500">No nodes matched the current query and filter scope.</p>
          ) : (
            <div className="space-y-1.5">
              {searchResults.map((result) => {
                const tone = getNodeTone(result.node.type);
                const selected = result.node.id === selectedNodeId;
                return (
                  <button
                    key={result.node.id}
                    type="button"
                    onClick={() => onSelectNode(result.node.id)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left transition-colors",
                      selected
                        ? "border-emerald-400/20 bg-emerald-500/10"
                        : "border-white/[0.05] bg-white/[0.02] hover:border-white/[0.09] hover:bg-white/[0.04]"
                    )}
                  >
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", tone.dot)} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[11.5px] font-medium text-neutral-100">{nodeDisplayName(result.node)}</div>
                      <div className="truncate text-[10px] font-mono text-neutral-500">{result.secondaryLabel}</div>
                    </div>
                    <span className="rounded-md border border-white/[0.06] px-1.5 py-0.5 text-[8px] font-mono uppercase tracking-[0.18em] text-neutral-400">
                      {NODE_TYPE_LABEL[result.node.type] ?? result.node.type}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </SectionCard>
      ) : null}
    </div>
  );
}

function ProjectSnapshotPanel({
  graph,
  communityResult,
  displayMeta,
  onSelectNode,
}: {
  graph: KnowledgeGraph;
  communityResult: CommunityResult | null;
  displayMeta: ReturnType<typeof deriveGraphDisplayMeta>;
  onSelectNode: (id: string | null) => void;
}) {
  const graphTitle = getGraphWorkspaceTitle(displayMeta);
  const fileCount = useMemo(() => graph.nodes.filter((node) => node.type === "file").length, [graph]);
  const topNodes = useMemo(() => getTopConnectedNodes(graph, 6), [graph]);

  return (
    <>
      <SectionCard>
        <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">Project snapshot</div>
        <div className="mt-2 text-[15px] font-semibold leading-tight text-neutral-100">{graphTitle}</div>
        <div className="mt-1 text-[10px] font-mono text-neutral-500">
          {[
            displayMeta.snapshotLabel && displayMeta.snapshotLabel !== graphTitle ? displayMeta.snapshotLabel : null,
            displayMeta.branch ? `branch ${displayMeta.branch}` : null,
            displayMeta.versionLabel,
          ]
            .filter(Boolean)
            .join(" Â· ") || displayMeta.repoUrl || displayMeta.graphId || graphTitle}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <MiniFact label="Nodes" value={formatCount(graph.nodes.length)} />
          <MiniFact label="Edges" value={formatCount(graph.edges.length)} />
          <MiniFact label="Files" value={formatCount(fileCount)} />
          <MiniFact label="Communities" value={formatCount(communityResult?.count ?? 0)} />
        </div>
      </SectionCard>

      {topNodes.length > 0 ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <Sparkles className="h-3 w-3" strokeWidth={1.8} />
            Most connected
          </div>
          <div className="space-y-1.5">
            {topNodes.map(({ node, degree }) => {
              const tone = getNodeTone(node.type);
              return (
                <button
                  key={`project-snapshot-${node.id}`}
                  type="button"
                  onClick={() => onSelectNode(node.id)}
                  className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.04]"
                >
                  <span className={cn("h-2 w-2 rounded-full", tone.dot)} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[11px] text-neutral-100">{nodeDisplayName(node)}</div>
                    <div className="truncate text-[10px] font-mono text-neutral-500">{nodeSecondaryLabel(node)}</div>
                  </div>
                  <span className="text-[10px] font-mono text-neutral-500">{formatCount(degree)}</span>
                </button>
              );
            })}
          </div>
        </SectionCard>
      ) : null}
    </>
  );
}

function NodeDetails({
  node,
  incoming,
  outgoing,
  graph,
  communityMeta,
  degree,
  onClear,
  onSelectNode,
  onViewFile,
  degreeMap,
}: {
  node: KGNode;
  incoming: KGEdge[];
  outgoing: KGEdge[];
  graph: KnowledgeGraph;
  communityMeta: { id: number; label: string; nodeIds: string[] } | null;
  degree: number;
  onClear: () => void;
  onSelectNode: (id: string | null) => void;
  onViewFile: (path: string) => void;
  degreeMap: Map<string, number>;
}) {
  const tone = getNodeTone(node.type);
  const displayName = nodeDisplayName(node);
  const file = node.filePath ?? node.file ?? "";
  const summary = buildNodeHeuristicSummary(node, incoming.length, outgoing.length);
  const relatedContext = Array.from(new Set([communityMeta?.label, node.language, ...node.tags].filter(Boolean))) as string[];
  const sameFileNodes = file
    ? graph.nodes
        .filter((candidate) => candidate.id !== node.id && (candidate.filePath ?? candidate.file ?? "") === file)
        .slice(0, 5)
    : [];
  const communityPeers = communityMeta
    ? communityMeta.nodeIds
        .map((id) => graph.nodes.find((candidate) => candidate.id === id))
        .filter((candidate): candidate is KGNode => Boolean(candidate))
        .filter((candidate) => candidate.id !== node.id)
        .slice(0, 5)
    : [];
  const inboundMix = summarizeEdgeTypes(incoming).slice(0, 4);
  const outboundMix = summarizeEdgeTypes(outgoing).slice(0, 4);
  const inboundItems = buildRelationItems(incoming, graph, (edge) => edge.source, degreeMap).slice(0, 3);
  const outboundItems = buildRelationItems(outgoing, graph, (edge) => edge.target, degreeMap).slice(0, 3);

  return (
    <motion.div
      key={node.id}
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.24 }}
      className="space-y-4"
    >
      <SectionCard>
        <div className="flex items-start gap-3">
          <span className={cn("mt-1 h-2.5 w-2.5 rounded-full", tone.dot)} />
          <div className="min-w-0 flex-1">
            <div className={cn("text-[9px] font-mono uppercase tracking-[0.24em]", tone.accent)}>
              {NODE_TYPE_LABEL[node.type] ?? node.type}
            </div>
            <div className="mt-1 text-[16px] font-semibold leading-tight text-neutral-100">{displayName}</div>
            <div className="mt-1 text-[10px] font-mono text-neutral-500">{file || nodeSecondaryLabel(node)}</div>
            {node.name !== displayName ? <div className="mt-1 text-[10px] font-mono text-neutral-600">symbol: {node.name}</div> : null}
          </div>
          <button
            type="button"
            onClick={onClear}
            className="rounded-lg p-1.5 text-neutral-500 transition-colors hover:bg-white/[0.05] hover:text-neutral-200"
            aria-label="Clear selection"
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.8} />
          </button>
        </div>

        {relatedContext.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {relatedContext.slice(0, 6).map((item) => (
              <span key={item} className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2 py-1 text-[9px] font-mono text-neutral-400">
                {item}
              </span>
            ))}
          </div>
        ) : null}

        <div className="mt-3 grid grid-cols-2 gap-2">
          <MiniFact label="Inbound" value={formatCount(incoming.length)} />
          <MiniFact label="Outbound" value={formatCount(outgoing.length)} />
          <MiniFact label="Degree" value={formatCount(degree)} />
          <MiniFact label="Community" value={communityMeta ? `C${communityMeta.id + 1}` : "â€”"} />
        </div>

        {file ? (
          <button
            type="button"
            onClick={() => onViewFile(file)}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-[11px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/14"
          >
            <Code2 className="h-3.5 w-3.5" strokeWidth={1.7} />
            View source
            <ArrowUpRight className="h-3 w-3" strokeWidth={1.8} />
          </button>
        ) : null}
      </SectionCard>

      <SectionCard>
        <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">Summary</div>
        <p className="mt-2 text-[11.5px] leading-6 text-neutral-300">{summary}</p>
      </SectionCard>

      <SectionCard>
        <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
          <Info className="h-3 w-3" strokeWidth={1.8} />
          Metadata
        </div>
        <div className="space-y-2 text-[11px] text-neutral-300">
          <MetadataRow label="Display" value={displayName} />
          {node.name !== displayName ? <MetadataRow label="Symbol" value={node.name} /> : null}
          <MetadataRow label="Type" value={NODE_TYPE_LABEL[node.type] ?? node.type} />
          <MetadataRow label="Language" value={node.language || "â€”"} />
          <MetadataRow label="Complexity" value={node.complexity ?? "â€”"} />
          <MetadataRow label="Path" value={file || contextualPathLabel(file) || "â€”"} mono />
        </div>
      </SectionCard>

      <SectionCard>
        <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
          <Layers className="h-3 w-3" strokeWidth={1.8} />
          Local call graph
        </div>
        <div className="mb-3 text-[11px] text-neutral-500">{formatCount(incoming.length)} inbound Â· {formatCount(outgoing.length)} outbound Â· centered on the selected node</div>

        <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-2">
          <div className="space-y-1.5">
            <div className="text-[8px] font-mono uppercase tracking-[0.2em] text-neutral-600">Inbound</div>
            {inboundItems.length > 0 ? (
              inboundItems.map(({ edge, node: relatedNode }) => (
                <button
                  key={`inbound-${edge.source}-${edge.target}-${edge.type}`}
                  type="button"
                  onClick={() => onSelectNode(relatedNode.id)}
                  className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-2.5 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.04]"
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: getEdgeStyle(edge.type).hex }} />
                  <span className="min-w-0 flex-1 truncate text-[10px] text-neutral-200">{nodeDisplayName(relatedNode)}</span>
                </button>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-white/[0.06] px-2.5 py-2 text-[10px] text-neutral-600">No inbound links</div>
            )}
          </div>

          <div className="mt-5 flex min-h-[92px] w-[92px] items-center justify-center rounded-3xl border border-white/[0.08] bg-white/[0.03] px-3 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div>
              <div className={cn("mx-auto h-2.5 w-2.5 rounded-full", tone.dot)} />
              <div className="mt-2 line-clamp-2 text-[10px] font-medium leading-4 text-neutral-100">{displayName}</div>
              <div className="mt-1 text-[7px] font-mono uppercase tracking-[0.18em] text-neutral-600">center node</div>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="text-[8px] font-mono uppercase tracking-[0.2em] text-neutral-600">Outbound</div>
            {outboundItems.length > 0 ? (
              outboundItems.map(({ edge, node: relatedNode }) => (
                <button
                  key={`outbound-${edge.source}-${edge.target}-${edge.type}`}
                  type="button"
                  onClick={() => onSelectNode(relatedNode.id)}
                  className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-2.5 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.04]"
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: getEdgeStyle(edge.type).hex }} />
                  <span className="min-w-0 flex-1 truncate text-[10px] text-neutral-200">{nodeDisplayName(relatedNode)}</span>
                </button>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-white/[0.06] px-2.5 py-2 text-[10px] text-neutral-600">No outbound links</div>
            )}
          </div>
        </div>

        {(inboundMix.length > 0 || outboundMix.length > 0) ? (
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <div>
              <div className="text-[8px] font-mono uppercase tracking-[0.2em] text-neutral-600">Inbound mix</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {inboundMix.map((item) => (
                  <span key={`inbound-mix-${item.type}`} className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2 py-1 text-[9px] font-mono text-neutral-400">
                    {formatEdgeTypeLabel(item.type)} Â· {formatCount(item.count)}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[8px] font-mono uppercase tracking-[0.2em] text-neutral-600">Outbound mix</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {outboundMix.map((item) => (
                  <span key={`outbound-mix-${item.type}`} className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2 py-1 text-[9px] font-mono text-neutral-400">
                    {formatEdgeTypeLabel(item.type)} Â· {formatCount(item.count)}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </SectionCard>

      {relatedContext.length > 0 ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <Tag className="h-3 w-3" strokeWidth={1.8} />
            Related context
          </div>
          <div className="flex flex-wrap gap-1.5">
            {relatedContext.map((item) => (
              <span key={item} className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2 py-1 text-[10px] font-mono text-neutral-400">
                {item}
              </span>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {(communityMeta || sameFileNodes.length > 0 || communityPeers.length > 0) ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <GitBranch className="h-3 w-3" strokeWidth={1.8} />
            Local context
          </div>

          {communityMeta ? (
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: communityColor(communityMeta.id) }} />
                <div className="text-[11px] font-medium text-neutral-100">{communityMeta.label}</div>
                <div className="ml-auto text-[9px] font-mono text-neutral-500">{formatCount(communityMeta.nodeIds.length)} nodes</div>
              </div>
            </div>
          ) : null}

          {sameFileNodes.length > 0 ? (
            <div className="mt-3">
              <div className="text-[8px] font-mono uppercase tracking-[0.2em] text-neutral-600">Same file</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {sameFileNodes.map((candidate) => (
                  <button
                    key={`file-peer-${candidate.id}`}
                    type="button"
                    onClick={() => onSelectNode(candidate.id)}
                  className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 text-[10px] font-mono text-neutral-300 transition-colors hover:border-white/[0.1] hover:bg-white/[0.05] hover:text-neutral-100"
                >
                  {nodeDisplayName(candidate)}
                </button>
              ))}
            </div>
            </div>
          ) : null}

          {communityPeers.length > 0 ? (
            <div className="mt-3">
              <div className="text-[8px] font-mono uppercase tracking-[0.2em] text-neutral-600">Community peers</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {communityPeers.map((candidate) => (
                  <button
                    key={`community-peer-${candidate.id}`}
                    type="button"
                    onClick={() => onSelectNode(candidate.id)}
                  className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 text-[10px] font-mono text-neutral-300 transition-colors hover:border-white/[0.1] hover:bg-white/[0.05] hover:text-neutral-100"
                >
                  {nodeDisplayName(candidate)}
                </button>
              ))}
            </div>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      <RelationSection
        title="Callers & inbound links"
        edges={incoming}
        graph={graph}
        getOtherNodeId={(edge) => edge.source}
        onSelectNode={onSelectNode}
        emptyMessage="No inbound relationships in the current graph."
        degreeMap={degreeMap}
      />

      <RelationSection
        title="Dependencies & outbound links"
        edges={outgoing}
        graph={graph}
        getOtherNodeId={(edge) => edge.target}
        onSelectNode={onSelectNode}
        emptyMessage="No outbound relationships in the current graph."
        degreeMap={degreeMap}
      />
    </motion.div>
  );
}

function RelationSection({
  title,
  edges,
  graph,
  getOtherNodeId,
  onSelectNode,
  emptyMessage,
  degreeMap,
}: {
  title: string;
  edges: KGEdge[];
  graph: KnowledgeGraph;
  getOtherNodeId: (edge: KGEdge) => string;
  onSelectNode: (id: string | null) => void;
  emptyMessage: string;
  degreeMap: Map<string, number>;
}) {
  const items = buildRelationItems(edges, graph, getOtherNodeId, degreeMap);

  return (
    <SectionCard>
      <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
        <Layers className="h-3 w-3" strokeWidth={1.8} />
        {title}
        <span className="text-neutral-700">Â·</span>
        <span className="text-neutral-600">{formatCount(items.length)}</span>
      </div>

      {items.length === 0 ? (
        <p className="text-[11px] text-neutral-500">{emptyMessage}</p>
      ) : (
        <div className="space-y-1.5">
          {items.slice(0, 8).map(({ edge, node }) => {
            const tone = getNodeTone(node.type);
            const style = getEdgeStyle(edge.type);
            return (
              <button
                key={`${edge.source}-${edge.target}-${edge.type}`}
                type="button"
                onClick={() => onSelectNode(node.id)}
                className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.04]"
              >
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: style.hex }} />
                <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", tone.dot)} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[11px] text-neutral-100">{nodeDisplayName(node)}</div>
                  <div className="truncate text-[10px] font-mono text-neutral-500">{nodeSecondaryLabel(node)}</div>
                </div>
                <span className="rounded-md border border-white/[0.06] px-1.5 py-0.5 text-[8px] font-mono uppercase tracking-[0.18em] text-neutral-400">
                  {formatEdgeTypeLabel(edge.type)}
                </span>
              </button>
            );
          })}
          {items.length > 8 ? (
            <div className="px-1 text-[10px] font-mono text-neutral-600">+{formatCount(items.length - 8)} more relationships</div>
          ) : null}
        </div>
      )}
    </SectionCard>
  );
}

function OverviewPanel({
  graph,
  communityResult,
  displayMeta,
  onSelectNode,
}: {
  graph: KnowledgeGraph;
  communityResult: CommunityResult | null;
  displayMeta: ReturnType<typeof deriveGraphDisplayMeta>;
  onSelectNode: (id: string | null) => void;
}) {
  const topNodes = useMemo(() => getTopConnectedNodes(graph, 6), [graph]);
  const languages = useMemo(() => uniqueLanguages(graph.nodes).slice(0, 8), [graph]);
  const nodeTypeCounts = useMemo(
    () => Object.entries(countNodeTypes(graph.nodes)).sort((left, right) => right[1] - left[1]).slice(0, 6),
    [graph]
  );
  const edgeSummary = useMemo(
    () => Object.entries(summarizeEdges(graph.edges)).sort((left, right) => right[1] - left[1]),
    [graph]
  );

  return (
    <div className="space-y-4">
      <SectionCard>
        <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">Graph overview</div>
        <div className="mt-2 text-[16px] font-semibold text-neutral-100">{getGraphWorkspaceTitle(displayMeta)}</div>
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-mono text-neutral-500">
          {displayMeta.repoUrl ? <span>{displayMeta.repoUrl}</span> : null}
          {displayMeta.branch ? <span>branch: {displayMeta.branch}</span> : null}
          {displayMeta.versionLabel ? <span>{displayMeta.versionLabel}</span> : null}
        </div>
      </SectionCard>

      <div className="grid grid-cols-2 gap-2">
        <MiniFact label="Nodes" value={formatCount(graph.nodes.length)} />
        <MiniFact label="Edges" value={formatCount(graph.edges.length)} />
        <MiniFact label="Files" value={formatCount(graph.nodes.filter((node) => node.type === "file").length)} />
        <MiniFact label="Communities" value={formatCount(communityResult?.count ?? 0)} />
      </div>

      {languages.length > 0 ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <Code2 className="h-3 w-3" strokeWidth={1.8} />
            Languages
          </div>
          <div className="flex flex-wrap gap-1.5">
            {languages.map(([language, count]) => (
              <span key={language} className="rounded-full border border-zinc-500/20 bg-zinc-500/10 px-2 py-1 text-[10px] font-mono text-zinc-300">
                {language} ({count})
              </span>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {nodeTypeCounts.length > 0 ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <Box className="h-3 w-3" strokeWidth={1.8} />
            Node mix
          </div>
          <div className="space-y-2">
            {nodeTypeCounts.map(([type, count]) => (
              <div key={type} className="flex items-center gap-2 text-[11px] text-neutral-300">
                <span className="truncate">{type}</span>
                <div className="h-px flex-1 bg-white/[0.06]" />
                <span className="font-mono text-neutral-500">{formatCount(count)}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {topNodes.length > 0 ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <Sparkles className="h-3 w-3" strokeWidth={1.8} />
            Most connected
          </div>
          <div className="space-y-1.5">
            {topNodes.map(({ node, degree }) => {
              const tone = getNodeTone(node.type);
              return (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => onSelectNode(node.id)}
                  className="flex w-full items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-left transition-colors hover:border-white/[0.09] hover:bg-white/[0.04]"
                >
                  <span className={cn("h-2 w-2 rounded-full", tone.dot)} />
                  <span className="truncate text-[11px] text-neutral-100">{nodeDisplayName(node)}</span>
                  <span className="ml-auto text-[10px] font-mono text-neutral-500">{degree}</span>
                </button>
              );
            })}
          </div>
        </SectionCard>
      ) : null}

      {edgeSummary.length > 0 ? (
        <SectionCard>
          <div className="mb-2 flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">
            <Hash className="h-3 w-3" strokeWidth={1.8} />
            Edge categories
          </div>
          <div className="space-y-2">
            {edgeSummary.map(([category, count]) => (
              <div key={category} className="flex items-center gap-2 text-[11px] text-neutral-300">
                <span className="capitalize">{category.replace(/_/g, " ")}</span>
                <div className="h-px flex-1 bg-white/[0.06]" />
                <span className="font-mono text-neutral-500">{formatCount(count)}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}

function CommunitiesPanel({
  graph,
  communities,
  onSelectNode,
}: {
  graph: KnowledgeGraph;
  communities: CommunityResult | null;
  onSelectNode: (id: string | null) => void;
}) {
  if (!communities || communities.count === 0) {
    return (
      <SelectionGuidanceState
        title="No communities detected"
        body="This graph does not yet expose enough structure for the current clustering heuristic to form community groups."
      />
    );
  }

  return (
    <div className="space-y-4">
      <SectionCard>
        <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-neutral-500">Community overview</div>
        <div className="mt-2 text-[14px] font-semibold text-neutral-100">{formatCount(communities.count)} detected communities</div>
        <div className="mt-1 text-[11px] text-neutral-500">Clustered via {communities.method}</div>
      </SectionCard>

      <div className="space-y-2">
        {communities.communities.slice(0, 12).map((community) => {
          const color = communityColor(community.id);
          const sampleNodes = community.nodes
            .slice(0, 5)
            .map((id) => graph.nodes.find((node) => node.id === id))
            .filter(Boolean) as KGNode[];

          return (
            <SectionCard key={community.id}>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                <div className="text-[12px] font-medium text-neutral-100">{community.label}</div>
                <div className="ml-auto text-[10px] font-mono text-neutral-500">{formatCount(community.nodes.length)} nodes</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {sampleNodes.map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelectNode(node.id)}
                    className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-1 text-[10px] font-mono text-neutral-300 transition-colors hover:border-white/[0.1] hover:bg-white/[0.05] hover:text-neutral-100"
                  >
                    {nodeDisplayName(node)}
                  </button>
                ))}
              </div>
            </SectionCard>
          );
        })}
      </div>
    </div>
  );
}

