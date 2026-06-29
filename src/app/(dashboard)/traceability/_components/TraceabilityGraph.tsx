"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useEdgesState,
  useNodesState,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
  BackgroundVariant,
  Panel,
} from "@xyflow/react";
import { layoutGraph, type LayoutDirection as ElkLayoutDirection } from "@/lib/layout/elk";
import { Beaker, GitBranch, Bug, AlertCircle, Maximize2, Minimize2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphModel, GraphNode, LayoutDirection, TestStatus, ReqStatus } from "./types";
import { NODE_KIND_TONE, EDGE_KIND_STYLE, TEST_STATUS_TONE, REQ_STATUS_TONE, PRIORITY_TONE } from "./constants";

const NODE_W = 220;
const NODE_H = 88;

function TraceNode({ data, selected }: NodeProps) {
  const d = data as unknown as { node: GraphNode };
  const node = d.node;
  const tone = NODE_KIND_TONE[node.kind];

  const Icon = node.kind === "requirement" ? GitBranch : node.kind === "test" ? Beaker : node.kind === "defect" ? Bug : AlertCircle;

  let statusTone: { dot: string; text: string } | null = null;
  if (node.kind === "test" && node.status) {
    const s = TEST_STATUS_TONE[node.status as TestStatus];
    if (s) statusTone = { dot: s.dot, text: s.text };
  } else if (node.kind === "requirement" && node.status) {
    const s = REQ_STATUS_TONE[node.status as ReqStatus];
    if (s) statusTone = { dot: s.dot, text: s.text };
  }

  const priority = node.priority ? PRIORITY_TONE[node.priority] : null;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] as const }}
      className={cn(
        "rounded-xl border p-3 backdrop-blur-sm transition-all cursor-pointer",
        tone.bg,
        tone.border,
        selected && `ring-2 ${tone.ring}`
      )}
      style={{ width: NODE_W, minHeight: NODE_H }}
    >
      <Handle type="target" position={Position.Top} className="!bg-white/20 !border-0 !w-2 !h-2" />
      <div className="flex items-start gap-2.5">
        <div
          className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
            tone.bg,
            tone.accent
          )}
        >
          <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className={cn("text-[12.5px] font-medium leading-tight line-clamp-2", tone.text)}>
            {node.label}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
            {statusTone && (
              <span className="flex items-center gap-1 text-[9.5px] font-mono uppercase tracking-wider">
                <span className={cn("w-1 h-1 rounded-full", statusTone.dot)} />
                <span className={statusTone.text}>{node.status}</span>
              </span>
            )}
            {priority && (
              <span className="flex items-center gap-1 text-[9.5px] font-mono uppercase tracking-wider">
                <span className={cn("w-1 h-1 rounded-full", priority.dot)} />
                <span className={priority.text}>{priority.label}</span>
              </span>
            )}
            {node.kind === "gap" && (
              <span className="text-[9.5px] font-mono text-amber-300/70">no tests</span>
            )}
            {node.kind === "defect" && (
              <span className="text-[9.5px] font-mono text-rose-300/70 uppercase tracking-wider">open</span>
            )}
          </div>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-white/20 !border-0 !w-2 !h-2" />
    </motion.div>
  );
}

const nodeTypes: NodeTypes = { trace: TraceNode };

export function TraceabilityGraph({
  model,
  direction,
  onSelect,
  onReset,
}: {
  model: GraphModel;
  direction: LayoutDirection;
  onSelect: (nodeId: string) => void;
  onReset?: () => void;
}) {
  const [layoutKey, setLayoutKey] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [layoutStatus, setLayoutStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");

  const initialNodes: Node[] = useMemo(
    () =>
      model.nodes.map((n) => ({
        id: n.id,
        type: "trace",
        position: { x: 0, y: 0 },
        data: { node: n },
        draggable: true,
        selectable: true,
      })),
    [model]
  );

  const initialEdges: Edge[] = useMemo(
    () =>
      model.edges.map((e) => {
        const style = EDGE_KIND_STYLE[e.kind];
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          animated: e.kind === "fails",
          style: {
            stroke: style.stroke,
            strokeWidth: style.width,
            strokeDasharray: style.dasharray,
          },
        };
      }),
    [model]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    let cancelled = false;
    setLayoutStatus("loading");
    setNodes(initialNodes);
    setEdges(initialEdges);
    layoutGraph(initialNodes, initialEdges, {
      direction: direction as ElkLayoutDirection,
      nodeWidth: NODE_W,
      nodeHeight: NODE_H,
      nodeNode: 50,
      nodeNodeBetweenLayers: 80,
    })
      .then((result) => {
        if (cancelled) return;
        setNodes(result.nodes);
        setEdges(result.edges);
        setLayoutKey((k) => k + 1);
        setLayoutStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[Traceability] layout failed", err);
        setLayoutStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [direction, model, initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onSelect(node.id);
    },
    [onSelect]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className={cn(
        "bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow overflow-hidden relative",
        isFullscreen ? "fixed inset-4 z-50" : "min-h-[640px]"
      )}
    >
      <div className="absolute top-3 right-3 z-10 flex items-center gap-1.5">
        <GraphButton
          icon={isFullscreen ? Minimize2 : Maximize2}
          onClick={() => setIsFullscreen((f) => !f)}
          label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
        />
        <GraphButton icon={RefreshCw} onClick={onReset ?? (() => setLayoutKey((k) => k + 1))} label="Reset layout" />
      </div>

      <div className="absolute top-3 left-3 z-10 flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-black/40 backdrop-blur border border-white/[0.06]">
        <span className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">Legend</span>
        <div className="flex items-center gap-2.5 text-[10px] font-mono">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-sm bg-zinc-400" />
            <span className="text-zinc-300">req</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-sm bg-emerald-400" />
            <span className="text-emerald-300">test</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-sm bg-rose-400" />
            <span className="text-rose-300">defect</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-sm border border-dashed border-rose-400" />
            <span className="text-rose-300/70">gap</span>
          </span>
        </div>
      </div>

      <AnimatePresence>
        {layoutStatus === "loading" && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/60 backdrop-blur border border-white/[0.06] text-[10.5px] font-mono text-neutral-400"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            laying out with ELK…
          </motion.div>
        )}
        {layoutStatus === "error" && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 px-2.5 py-1 rounded-md bg-rose-500/15 border border-rose-400/30 text-[10.5px] font-mono text-rose-300"
          >
            layout error
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {model.nodes.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <div className="text-center">
              <div className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider">
                No nodes to render
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="w-full h-full" style={{ minHeight: isFullscreen ? undefined : 640 }}>
        <ReactFlowProvider>
          <ReactFlow
            key={layoutKey}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1.2, minZoom: 0.3 }}
            minZoom={0.2}
            maxZoom={1.5}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: "smoothstep" }}
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1a1a2e" />
            <Controls
              showInteractive={false}
              className="!bg-white/[0.03] !border !border-white/[0.06] !rounded-lg [&>button]:!bg-transparent [&>button]:!border-white/[0.06] [&>button]:!text-neutral-400 [&>button:hover]:!bg-white/[0.04] [&>button:hover]:!text-neutral-200"
            />
            <MiniMap
              pannable
              zoomable
              maskColor="rgba(10, 10, 15, 0.85)"
              nodeColor={(n) => {
                const d = n.data as { node: GraphNode };
                return d.node.kind === "requirement"
                  ? "#a1a1aa"
                  : d.node.kind === "test"
                    ? "#34d399"
                    : d.node.kind === "defect"
                      ? "#fb7185"
                      : "#fb7185";
              }}
              style={{
                background: "rgba(18, 18, 28, 0.6)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 8,
              }}
            />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </motion.div>
  );
}

function GraphButton({
  icon: Icon,
  onClick,
  label,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className="w-7 h-7 flex items-center justify-center rounded-md bg-white/[0.03] border border-white/[0.06] text-neutral-500 hover:text-neutral-200 hover:border-white/[0.1] transition-colors"
    >
      <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
    </button>
  );
}
