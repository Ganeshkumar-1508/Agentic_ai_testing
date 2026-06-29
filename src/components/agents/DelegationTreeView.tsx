"use client";

import { useCallback, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRight,
  ChevronDown,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  GitBranch,
  AlertTriangle,
  PauseCircle,
  PlayCircle,
  DollarSign,
  Wrench,
  Sparkles,
} from "lucide-react";
import { useEventSource } from "@/lib/hooks/use-event-source";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

const TREE_EVENT_TYPES = [
  "session.started",
  "session.completed",
  "session.failed",
  "subagent.spawned",
  "subagent.completed",
  "subagent.failed",
] as const;

interface ToolCallDetail {
  id: number;
  event_type: string;
  event_data: Record<string, unknown>;
  created_at: string;
}

interface TreeNode {
  id: string;
  sessionId: string;
  parentId: string | null;
  goal: string;
  depth: number;
  role: "leaf" | "orchestrator";
  status: "running" | "completed" | "failed" | "cancelled";
  toolCalls: { name: string; status: string }[];
  toolCallDetails?: ToolCallDetail[];
  costUsd?: number;
  model?: string;
  result?: string;
  error?: string;
  startedAt?: number;
  children: TreeNode[];
}

interface DelegationTreeViewProps {
  sessionId: string;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

const springConfig = { type: "spring" as const, stiffness: 280, damping: 24, mass: 0.4 };

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04, delayChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: -6 },
  show: { opacity: 1, y: 0, transition: springConfig },
};

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    failed: "bg-red-500/10 text-red-400 border-red-500/20",
    cancelled: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  };
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium border", colors[status] || colors.running)}>
      {status}
    </span>
  );
}

function TreeNodeEdgeLine({ depth, isLast }: { depth: number; isLast: boolean }) {
  if (depth === 0) return null;
  return (
    <div className="absolute left-0 top-0 bottom-0" style={{ left: `${depth * 20 - 12}px` }}>
      <div className="absolute left-[7px] top-0 bottom-0 w-px bg-zinc-800/50" />
      <div className={cn(
        "absolute left-[7px] w-px bg-zinc-800/50",
        isLast ? "h-4 top-0" : "h-full top-0"
      )} />
      <div className="absolute left-[7px] top-4 w-[10px] h-px bg-zinc-800/50" />
    </div>
  );
}

export function DelegationTreeView({ sessionId }: DelegationTreeViewProps) {
  const [treeData, setTreeData] = useState<TreeNode | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [paused, setPaused] = useState(false);
  const [expandedMap, setExpandedMap] = useState<Record<string, "result" | "error" | null>>({});

  const toggleCollapse = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const collapseAll = () => {
    if (!treeData) return;
    const ids = new Set<string>();
    const collect = (n: TreeNode) => {
      if (n.children.length > 0) {
        ids.add(n.id);
        n.children.forEach(collect);
      }
    };
    collect(treeData);
    ids.delete(treeData.id);
    setCollapsed(ids);
  };

  const expandAll = () => {
    setCollapsed(new Set());
  };

  const toggleExpand = (id: string, kind: "result" | "error") => {
    setExpandedMap((prev) => ({
      ...prev,
      [id]: prev[id] === kind ? null : kind,
    }));
  };

  useEventSource({
    url: sessionId ? `/api/delegate/${sessionId}/stream` : null,
    eventTypes: TREE_EVENT_TYPES,
    onEvent: (type, rawData) => {
      const data = (rawData ?? {}) as Record<string, unknown>;

      switch (type) {
        case "session.started":
          setTreeData({
            id: (data.session_id as string) ?? sessionId,
            sessionId: (data.session_id as string) ?? sessionId,
            parentId: null,
            goal: (data.goal as string) || "Delegation",
            depth: 0,
            role: "orchestrator",
            status: "running",
            toolCalls: [],
            children: [],
            startedAt: Date.now(),
          });
          break;

        case "session.completed":
          setTreeData((prev) => prev ? { ...prev, status: "completed" as const } : null);
          break;

        case "session.failed":
          setTreeData((prev) => prev ? { ...prev, status: "failed" as const } : null);
          break;

        case "subagent.spawned": {
          const newNode: TreeNode = {
            id: (data.subagent_id as string) || `node-${Date.now()}`,
            sessionId: sessionId,
            parentId: (data.parent_id as string) || sessionId,
            goal: (data.goal as string) || "Subtask",
            depth: (data.depth as number) ?? 1,
            role: (data.role as "leaf" | "orchestrator") || "leaf",
            status: "running",
            toolCalls: [],
            model: data.model as string | undefined,
            children: [],
            startedAt: ((data.started_at as number) ?? Date.now()) * 1000,
          };
          addNodeToTree(newNode);
          break;
        }

        case "subagent.completed":
          if (data.subagent_id) {
            updateNodeStatus(
              data.subagent_id as string, "completed",
              (data.output_preview as string) || (data.preview as string),
              data.duration_sec as number | undefined,
              data.tool_calls_count as number | undefined,
              data.cost_usd as number | undefined,
            );
          }
          break;

        case "subagent.failed":
          if (data.subagent_id) {
            updateNodeStatus(data.subagent_id as string, "failed", data.preview as string);
          }
          break;
      }
    },
  });

  const addNodeToTree = (newNode: TreeNode) => {
    setTreeData((prev) => {
      if (!prev) return newNode;
      const updated = structuredClone(prev);
      const parent = findNode(updated, newNode.parentId || updated.id);
      if (parent) {
        parent.children.push(newNode);
      }
      return updated;
    });
  };

  const updateNodeStatus = (nodeId: string, status: TreeNode["status"], preview?: string, durationSec?: number, toolCount?: number, costUsd?: number) => {
    setTreeData((prev) => {
      if (!prev) return null;
      const updated = structuredClone(prev);
      const node = findNode(updated, nodeId);
      if (node) {
        node.status = status;
        if (preview) {
          if (status === "failed") node.error = preview;
          else node.result = preview;
        }
        if (durationSec && node.startedAt) {
          node.startedAt = Date.now() - durationSec * 1000;
        }
        if (toolCount !== undefined && toolCount > 0) {
          node.toolCalls = Array.from({ length: toolCount }, (_, i) => ({
            name: "tool",
            status: "done" as const,
          }));
        }
        if (costUsd !== undefined) {
          node.costUsd = costUsd;
        }
      }
      return updated;
    });
  };

  const findNode = (node: TreeNode, id: string): TreeNode | null => {
    if (node.id === id) return node;
    for (const child of node.children) {
      const found = findNode(child, id);
      if (found) return found;
    }
    return null;
  };

  const [expandedToolCallNode, setExpandedToolCallNode] = useState<string | null>(null);
  const [toolCallLoading, setToolCallLoading] = useState<string | null>(null);

  const handleToolCallExpand = async (nodeId: string, node: TreeNode) => {
    if (expandedToolCallNode === nodeId) {
      setExpandedToolCallNode(null);
      return;
    }
    if (node.toolCallDetails) {
      setExpandedToolCallNode(nodeId);
      return;
    }
    setToolCallLoading(nodeId);
    try {
      const data = await api.get<{ tool_calls: ToolCallDetail[] }>(
        `/api/delegate/${sessionId}/tool-calls?subagent_id=${nodeId}`
      );
      setTreeData((prev) => {
        if (!prev) return null;
        const updated = structuredClone(prev);
        const n = findNode(updated, nodeId);
        if (n) n.toolCallDetails = data.tool_calls || [];
        return updated;
      });
      setExpandedToolCallNode(nodeId);
    } catch {
      // ignore
    }
    setToolCallLoading(null);
  };

  const handleResume = async () => {
    try {
      await api.post(`/api/delegate/${sessionId}/resume`);
      setPaused(false);
    } catch {
      // ignore
    }
  };

  const rootStatus = treeData?.status;

  const renderNode = (node: TreeNode, level: number, isLast: boolean) => {
    const isCollapsed = collapsed.has(node.id);
    const indent = level * 20;
    const isRunning = node.status === "running";
    const elapsed = node.startedAt && isRunning
      ? Math.floor((Date.now() - node.startedAt) / 1000)
      : null;

    const statusIcon = isRunning ? (
      <Loader2 size={13} className="animate-spin text-blue-400" strokeWidth={2} />
    ) : node.status === "completed" ? (
      <CheckCircle2 size={13} className="text-emerald-400" strokeWidth={1.5} />
    ) : node.status === "failed" ? (
      <XCircle size={13} className="text-red-400" strokeWidth={1.5} />
    ) : (
      <Clock size={13} className="text-zinc-500" strokeWidth={1.5} />
    );

    const expandedKind = expandedMap[node.id];
    const hasResult = node.result || node.error;

    return (
      <motion.div
        key={node.id}
        variants={itemVariants}
        layout
        className="relative"
      >
        {/* Connector line for non-root nodes */}
        {level > 0 && (
          <div
            className="absolute top-0 bottom-0"
            style={{ left: `${indent + 6 - 20}px` }}
          >
            <div className="absolute left-[3px] top-0 bottom-0 w-px bg-zinc-800/40" />
            <div className="absolute left-[3px] top-[14px] w-[10px] h-px bg-zinc-800/40" />
          </div>
        )}

        <div className="relative">
          <div
            className={cn(
              "group flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm transition-all cursor-pointer",
              "hover:bg-zinc-800/20 active:scale-[0.99]",
            )}
            style={{ paddingLeft: `${indent + 10}px` }}
            onClick={() => node.children.length > 0 && toggleCollapse(node.id)}
          >
            {node.children.length > 0 ? (
              <motion.span
                animate={{ rotate: isCollapsed ? 0 : 90 }}
                transition={springConfig}
                className="shrink-0"
              >
                <ChevronRight size={11} className="text-zinc-600" strokeWidth={2} />
              </motion.span>
            ) : (
              <span className="w-3 shrink-0" />
            )}

            {statusIcon}

            <span className="flex items-center gap-1.5 min-w-0 flex-1">
              <span className="truncate text-zinc-300 text-[13px]">{node.goal}</span>
              {node.role === "orchestrator" && (
                <span className="shrink-0 text-[9px] px-1 py-0.5 rounded bg-amber-500/10 text-amber-400/70 font-mono">ctl</span>
              )}
              {node.model && (
                <code className="shrink-0 text-[9px] px-1 py-0.5 rounded bg-zinc-800/50 text-zinc-500 font-mono">{node.model}</code>
              )}
            </span>

            <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
              {node.toolCalls.length > 0 && (
                <button
                  onClick={(e) => { e.stopPropagation(); handleToolCallExpand(node.id, node); }}
                  className="text-[10px] text-zinc-600 font-mono hover:text-zinc-400 transition-colors"
                >
                  {toolCallLoading === node.id ? (
                    <Loader2 size={10} className="animate-spin" strokeWidth={2} />
                  ) : (
                    <span className="underline decoration-zinc-800 underline-offset-2">{node.toolCalls.length} tools</span>
                  )}
                </button>
              )}

              {node.costUsd !== undefined && node.costUsd > 0 && (
                <span className="text-[10px] text-zinc-700 font-mono flex items-center gap-0.5">
                  <DollarSign size={8} strokeWidth={1.5} />${node.costUsd.toFixed(4)}
                </span>
              )}

              {!isRunning && node.startedAt && (
                <span className="text-[10px] text-zinc-700 font-mono">
                  {formatDuration(((Date.now() - node.startedAt) / 1000))}
                </span>
              )}

              {elapsed !== null && (
                <span className="text-[10px] text-blue-400/50 font-mono" title="Elapsed">
                  {formatDuration(elapsed)}
                </span>
              )}
            </div>
          </div>

          {/* Expandable sections */}
          <AnimatePresence>
            {expandedToolCallNode === node.id && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={springConfig}
                style={{ paddingLeft: `${indent + 28}px` }}
                className="overflow-hidden"
              >
                {node.toolCallDetails && node.toolCallDetails.length > 0 ? (
                  <div className="my-1 rounded-lg border border-zinc-800/30 bg-zinc-900/40 p-2.5 space-y-1 max-h-[200px] overflow-y-auto">
                    <div className="text-[9px] text-zinc-600 font-mono uppercase tracking-wider mb-1.5 flex items-center gap-1">
                      <Wrench size={9} strokeWidth={1.5} />
                      tool calls
                    </div>
                    {node.toolCallDetails.map((tc, i) => (
                      <motion.div
                        key={tc.id}
                        initial={{ opacity: 0, x: -4 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.02 }}
                        className="flex items-start gap-1.5 py-0.5 text-[10px]"
                      >
                        <span className={cn(
                          "shrink-0 font-mono",
                          tc.event_type.includes("Started") || tc.event_type.includes("start")
                            ? "text-amber-400/60"
                            : (tc.event_data as Record<string, unknown>)?.success === false || (tc.event_data as Record<string, unknown>)?.is_error === true
                              ? "text-red-400/60"
                              : "text-emerald-400/60"
                        )}>
                          {tc.event_type.includes("Started") || tc.event_type.includes("start") ? "\u2192" : "\u2713"}
                        </span>
                        <span className="shrink-0 font-mono text-zinc-500">
                          {(tc.event_data?.tool_name as string) || (tc.event_data?.name as string) || "?"}
                        </span>
                        <span className="truncate text-zinc-600">
                          {tc.event_type.includes("Completed") || tc.event_type.includes("end") || tc.event_type.includes("result")
                            ? String((tc.event_data?.output_preview as string) || (tc.event_data?.result as string) || "").slice(0, 100)
                            : String((tc.event_data?.tool_input as string) || (tc.event_data?.input as string) || "").slice(0, 100)
                          }
                        </span>
                      </motion.div>
                    ))}
                  </div>
                ) : (
                  <div className="text-[10px] text-zinc-700 font-mono py-1">no tool call data</div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Result/error toggle */}
          {hasResult && (
            <div style={{ paddingLeft: `${indent + 28}px` }} className="mt-0.5">
              <button
                onClick={() => toggleExpand(node.id, node.error ? "error" : "result")}
                className={cn(
                  "text-[10px] font-mono transition-colors",
                  node.error ? "text-red-400/60 hover:text-red-400" : "text-zinc-600 hover:text-zinc-400"
                )}
              >
                {expandedKind === (node.error ? "error" : "result") ? "hide" : node.error ? "show error" : "show result"}
              </button>
              <AnimatePresence>
                {expandedKind === (node.error ? "error" : "result") && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={springConfig}
                    className={cn(
                      "mt-1 text-[11px] font-mono rounded-lg px-3 py-2 border overflow-hidden",
                      node.error
                        ? "bg-red-500/5 border-red-500/20 text-red-400"
                        : "bg-zinc-900/40 border-zinc-800/30 text-zinc-500"
                    )}
                  >
                    <span className="whitespace-pre-wrap line-clamp-6">
                      {node.error || node.result}
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </div>

        <AnimatePresence>
          {!isCollapsed && node.children.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={springConfig}
              className="overflow-hidden"
            >
              <motion.div variants={containerVariants} initial="hidden" animate="show">
                {node.children.map((child, i) => (
                  <div key={child.id} className="relative">
                    {renderNode(child, level + 1, i === node.children.length - 1)}
                  </div>
                ))}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    );
  };

  const nodeCount = useMemo(() => {
    if (!treeData) return 0;
    let count = 0;
    const walk = (n: TreeNode) => { count++; n.children.forEach(walk); };
    walk(treeData);
    return count;
  }, [treeData]);

  return (
    <div className="rounded-xl border border-zinc-800/40 bg-gradient-to-b from-zinc-900/30 to-zinc-950/30 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800/30 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-lg bg-zinc-800/40 flex items-center justify-center">
            <GitBranch size={13} className="text-zinc-400" strokeWidth={1.5} />
          </div>
          <span className="text-xs font-medium text-zinc-300">Delegation</span>
          {treeData && <StatusBadge status={rootStatus || "running"} />}
          {nodeCount > 0 && (
            <span className="text-[10px] text-zinc-700 font-mono">{nodeCount} nodes</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={collapseAll}
            className="text-[9px] px-2 py-1 rounded-md bg-zinc-800/40 text-zinc-500 hover:text-zinc-300 border border-zinc-700/30 transition-all active:scale-[0.97]">
            Collapse
          </button>
          <button onClick={expandAll}
            className="text-[9px] px-2 py-1 rounded-md bg-zinc-800/40 text-zinc-500 hover:text-zinc-300 border border-zinc-700/30 transition-all active:scale-[0.97]">
            Expand
          </button>
          {treeData?.status === "running" && (
            <>
              <div className="w-px h-4 bg-zinc-800/50 mx-1" />
              {paused ? (
                <button onClick={handleResume}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-emerald-400 transition-all hover:bg-emerald-500/10 active:scale-[0.98]">
                  <PlayCircle size={11} strokeWidth={1.5} />
                  Resume
                </button>
              ) : (
                <button onClick={async () => { await api.post(`/api/delegate/${sessionId}/pause`); setPaused(true); }}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-amber-400 transition-all hover:bg-amber-500/10 active:scale-[0.98]">
                  <PauseCircle size={11} strokeWidth={1.5} />
                  Pause
                </button>
              )}
              <button onClick={async () => { if (confirm("Cancel entire delegation tree?")) { await api.post(`/api/delegate/${sessionId}/cancel`); } }}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-red-400 transition-all hover:bg-red-500/10 active:scale-[0.98]">
                <XCircle size={11} strokeWidth={1.5} />
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-3">
        {!treeData ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-10 gap-2"
          >
            <div className="w-10 h-10 rounded-2xl bg-zinc-800/30 flex items-center justify-center">
              <GitBranch size={18} className="text-zinc-700" strokeWidth={1} />
            </div>
            <p className="text-xs text-zinc-600 font-mono">waiting for delegation</p>
            <p className="text-[10px] text-zinc-700">Subagents appear here as they spawn</p>
          </motion.div>
        ) : rootStatus === "completed" && nodeCount === 1 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-8 gap-2"
          >
            <CheckCircle2 size={20} className="text-zinc-700" strokeWidth={1} />
            <p className="text-xs text-zinc-600 font-mono">completed with no subagents</p>
          </motion.div>
        ) : (
          <motion.div variants={containerVariants} initial="hidden" animate="show">
            {renderNode(treeData, 0, true)}
          </motion.div>
        )}
      </div>
    </div>
  );
}
