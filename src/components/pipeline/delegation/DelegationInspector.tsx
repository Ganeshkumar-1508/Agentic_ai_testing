"use client";

import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRightIcon, CrossCircledIcon, CheckCircledIcon,
  DownloadIcon, ExternalLinkIcon,
  PlayIcon, ResetIcon, ListBulletIcon, TimerIcon,
} from "@radix-ui/react-icons";
import { cn } from "@/lib/utils";
import { api, BASE_URL } from "@/lib/api/api-client";

interface AgentNode {
  id: string;
  label: string;
  depth: number;
  goal?: string;
  status: "running" | "completed" | "failed" | "pending";
  children?: AgentNode[];
  toolCalls?: ToolCall[];
}

interface ToolCall {
  name: string;
  duration: number;
  status: "success" | "failure";
  detail?: string;
}

interface LogEvent {
  ts: string;
  type: "agent" | "exec" | "pass" | "fail" | "tool" | "warn";
  message: string;
  source?: string;
}

const STATUS_COLORS = { running: "text-amber-400", completed: "text-emerald-400", failed: "text-red-400", pending: "text-zinc-600" };
const STATUS_BG = { running: "bg-amber-400/10 border-amber-400/20 text-amber-400", completed: "bg-emerald-400/10 border-emerald-400/20 text-emerald-400", failed: "bg-red-400/10 border-red-400/20 text-red-400", pending: "bg-zinc-800 text-zinc-600 border-zinc-700" };
const EVENT_COLORS = { agent: "text-emerald-400", exec: "text-zinc-400", pass: "text-emerald-400", fail: "text-red-400", tool: "text-zinc-500", warn: "text-amber-400" };

function formatDuration(s: number) {
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  return `${s.toFixed(1)}s`;
}

function StatusDot({ status }: { status: string }) {
  return <span className={`w-1.5 h-1.5 rounded-full ${status === "running" ? "bg-amber-400 animate-pulse" : status === "completed" ? "bg-emerald-400" : status === "failed" ? "bg-red-400" : "bg-zinc-600"}`} />;
}

function EventIcon({ type }: { type: string }) {
  switch (type) {
    case "agent": return <PlayIcon className="w-3 h-3 text-emerald-400" />;
    case "exec": return <PlayIcon className="w-3 h-3 text-zinc-400" />;
    case "pass": return <CheckCircledIcon className="w-3 h-3 text-emerald-400" />;
    case "fail": return <CrossCircledIcon className="w-3 h-3 text-red-400" />;
    case "tool": return <PlayIcon className="w-3 h-3 text-zinc-500" />;
    case "warn": return <ResetIcon className="w-3 h-3 text-amber-400" />;
    default: return <PlayIcon className="w-3 h-3 text-zinc-500" />;
  }
}

function TreeNode({ node, selectedId, onSelect, depth }: { node: AgentNode; selectedId: string | null; onSelect: (id: string) => void; depth: number }) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedId === node.id;

  return (
    <div>
      <motion.div
        layout
        onClick={() => { onSelect(node.id); if (hasChildren) setExpanded(!expanded); }}
        className={cn("flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-all", isSelected ? "bg-emerald-400/6 border border-emerald-400/15" : "hover:bg-zinc-800/30 border border-transparent")}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        {hasChildren ? (
          <motion.div animate={{ rotate: expanded ? 90 : 0 }} transition={{ type: "spring", stiffness: 100, damping: 20 }}>
            <svg className="w-3 h-3 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" /></svg>
          </motion.div>
        ) : <span className="w-3" />}
        <StatusDot status={node.status} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-200 truncate font-medium">{node.label}</span>
            {node.goal && <span className="text-[9px] text-zinc-600 truncate hidden lg:inline">{node.goal}</span>}
          </div>
        </div>
        {node.toolCalls && <span className="text-[9px] text-zinc-600 font-mono">{node.toolCalls.length} calls</span>}
        <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${STATUS_BG[node.status]}`}>{node.status}</span>
      </motion.div>
      <AnimatePresence>
        {expanded && hasChildren && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ type: "spring", stiffness: 100, damping: 20 }}>
            {node.children!.map((child) => (
              <TreeNode key={child.id} node={child} selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TimelineBars({ calls }: { calls: ToolCall[] }) {
  const total = calls.reduce((s, c) => s + c.duration, 0);
  let offset = 0;
  return (
    <div className="space-y-1.5 mb-4 pb-4 border-b border-zinc-800/50">
      {calls.map((c, i) => {
        const pct = total > 0 ? (c.duration / total) * 100 : 0;
        const leftPct = total > 0 ? (offset / total) * 100 : 0;
        offset += c.duration;
        return (
          <div key={i} className="flex items-center gap-2">
            <span className="text-[9px] font-mono text-zinc-700 w-10 text-right shrink-0">{formatDuration(offset - c.duration)}</span>
            <div className="flex-1 h-6 rounded-lg bg-zinc-800/20 relative overflow-hidden">
              <motion.div
                initial={{ width: 0 }} animate={{ width: `${pct}%` }}
                transition={{ type: "spring", stiffness: 60, damping: 20, delay: i * 0.08 }}
                className={`h-full rounded-lg ${c.status === "success" ? "bg-emerald-400/15 border border-emerald-400/15" : "bg-red-400/15 border border-red-400/15"}`}
              />
              <span className="absolute inset-0 flex items-center px-2 text-[9px] font-mono text-zinc-500">{c.name}</span>
              <span className={`absolute right-2 top-0 bottom-0 flex items-center text-[9px] font-mono ${c.status === "success" ? "text-emerald-400" : "text-red-400"}`}>{formatDuration(c.duration)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function DelegationInspector({ sessionId }: { sessionId?: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"tree" | "flat">("tree");
  const [tree, setTree] = useState<AgentNode | null>(null);
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) { setLoading(false); return; }
    setLoading(true);
    Promise.all([
      api.get<any>(`/api/delegate/${sessionId}`).catch(() => null),
      fetch(`${BASE_URL}/api/delegate/${sessionId}/stream`, { headers: { Accept: "text/event-stream" } }).then(r => r.ok ? r.text() : "").catch(() => ""),
    ]).then(([sessionData, _stream]) => {
      if (sessionData) {
        const node: AgentNode = {
          id: sessionData.session_id || sessionId,
          label: sessionData.goal || "Session",
          depth: 0,
          goal: sessionData.goal,
          status: sessionData.status === "completed" ? "completed" : sessionData.status === "failed" ? "failed" : "running",
          children: (sessionData.subagents || []).map((s: any, i: number) => ({
            id: s.id || `sub-${i}`,
            label: s.goal || s.role || `Subagent ${i}`,
            depth: 1,
            goal: s.goal,
            status: s.status === "completed" ? "completed" : s.status === "failed" ? "failed" : "running",
          })),
        };
        setTree(node);
        setSelectedId(node.id);
      }
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    const fetchEvents = () => {
      api.get<{ events?: any[] }>("/api/ops/swarm/delegate-events?limit=30")
        .then(d => {
          const evs: LogEvent[] = (d.events || []).map((e: any) => ({
            ts: e.created_at ? new Date(e.created_at).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "",
            type: (e.event_type || "").includes("fail") ? "fail" : (e.event_type || "").includes("tool") ? "tool" : (e.event_type || "").includes("thinking") ? "agent" : "exec",
            message: e.event_data?.message || e.event_data?.preview || e.event_type || "event",
            source: e.agent_id || "",
          }));
          setEvents(evs);
        })
        .catch(() => {});
    };
    fetchEvents();
    const interval = setInterval(fetchEvents, 10000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const selectedNode = useMemo(() => {
    if (!tree || !selectedId) return null;
    function find(n: AgentNode): AgentNode | null {
      if (n.id === selectedId) return n;
      for (const c of n.children || []) { const f = find(c); if (f) return f; }
      return null;
    }
    return find(tree);
  }, [tree, selectedId]);

  const filteredEvents = useMemo(() => {
    if (!selectedNode) return events;
    return events.filter((e) => {
      if (filterType !== "all" && e.type !== filterType) return false;
      return e.source === selectedNode.id || e.source === tree?.id;
    });
  }, [selectedNode, filterType, events, tree]);

  const agentCount = useMemo(() => {
    let count = 0;
    const countNodes = (n: AgentNode) => { count++; (n.children || []).forEach(countNodes); };
    if (tree) countNodes(tree);
    return count;
  }, [tree]);

  const maxDepth = useMemo(() => {
    let max = 0;
    const findDepth = (n: AgentNode, d: number) => { max = Math.max(max, d); (n.children || []).forEach(c => findDepth(c, d + 1)); };
    if (tree) findDepth(tree, 0);
    return max;
  }, [tree]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-zinc-800/60 bg-zinc-950 overflow-hidden">
        <div className="p-6 text-center text-[11px] text-zinc-600">Loading delegation tree...</div>
      </div>
    );
  }

  if (!tree) {
    return (
      <div className="rounded-2xl border border-zinc-800/60 bg-zinc-950 overflow-hidden">
        <div className="p-8 text-center text-[11px] text-zinc-600">No active delegation tree. Start a pipeline to see the agent hierarchy.</div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-950 overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800/60 bg-zinc-900/50">
        <div className="flex items-center gap-1.5">
          <ListBulletIcon className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-[0.08em]">Delegation Inspector</span>
        </div>
        <div className="flex border border-zinc-800 rounded-lg overflow-hidden text-[10px] font-mono ml-auto">
          <button onClick={() => setViewMode("flat")} className={`px-2.5 py-1 ${viewMode === "flat" ? "bg-zinc-800 text-zinc-300" : "text-zinc-600 hover:text-zinc-400"}`}>flat</button>
          <button onClick={() => setViewMode("tree")} className={`px-2.5 py-1 ${viewMode === "tree" ? "bg-zinc-800 text-zinc-300" : "text-zinc-600 hover:text-zinc-400"}`}>tree</button>
        </div>
        <span className="text-[10px] text-zinc-700 font-mono">{agentCount} agents</span>
        <span className="text-[10px] text-zinc-700 font-mono">depth {maxDepth}</span>
      </div>

      <div className="flex" style={{ minHeight: "520px" }}>
        <div className="w-[280px] shrink-0 border-r border-zinc-800/60 p-3 overflow-y-auto" style={{ maxHeight: "520px" }}>
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[9px] font-semibold text-zinc-600 uppercase tracking-[0.08em]">agents</span>
            <span className="text-[9px] text-zinc-700 font-mono">running: {tree.children?.filter(c => c.status === "running").length || 0}</span>
          </div>
          <TreeNode node={tree} selectedId={selectedId} onSelect={setSelectedId} depth={0} />
          <div className="mt-3 flex gap-3 text-[9px] text-zinc-700">
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> completed</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" /> running</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-red-400" /> failed</span>
          </div>
        </div>

        <div className="flex-1 flex flex-col p-3 overflow-y-auto" style={{ maxHeight: "520px" }}>
          {selectedNode && selectedNode.toolCalls && selectedNode.toolCalls.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <TimerIcon className="w-3 h-3 text-zinc-500" />
                  <span className="text-[9px] font-semibold text-zinc-600 uppercase tracking-[0.06em]">agent: {selectedNode.label}</span>
                </div>
                <span className="text-[9px] font-mono text-zinc-700">{selectedNode.toolCalls.length} calls · {formatDuration(selectedNode.toolCalls.reduce((s, c) => s + c.duration, 0))} total</span>
              </div>
              <TimelineBars calls={selectedNode.toolCalls} />
            </>
          ) : selectedNode && (
            <div className="flex items-center justify-center h-20 text-[10px] text-zinc-700">No tool call data for this agent</div>
          )}

          <div className="flex items-center gap-1.5 mb-2.5">
            <span className="text-[9px] text-zinc-600 mr-1">events:</span>
            {["all", "agent", "exec", "tool", "fail"].map((t) => (
              <button key={t} onClick={() => setFilterType(t)}
                className={`text-[9px] px-2 py-0.5 rounded-md ${filterType === t ? "bg-emerald-400/10 text-emerald-400 border border-emerald-400/20" : "bg-zinc-800/40 text-zinc-600 border border-zinc-800 hover:text-zinc-400"}`}
              >{t}</button>
            ))}
          </div>

          <div className="flex-1 space-y-0.5">
            {filteredEvents.map((e, i) => (
              <div key={i} className="flex items-start gap-2.5 py-1.5 px-2 rounded-lg hover:bg-zinc-800/15 cursor-pointer">
                <span className="text-[9px] font-mono text-zinc-700 w-12 shrink-0">{e.ts}</span>
                <EventIcon type={e.type} />
                <span className="text-[10px] text-zinc-400 flex-1">{e.message}</span>
                {e.source && <span className="text-[8px] text-zinc-700 font-mono">{e.source}</span>}
              </div>
            ))}
          </div>
        </div>

        {selectedNode && selectedNode.toolCalls && selectedNode.toolCalls.some((t) => t.status === "failure") && (
          <div className="w-[280px] shrink-0 border-l border-zinc-800/60 p-3 flex flex-col" style={{ maxHeight: "520px" }}>
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[9px] font-semibold text-zinc-600 uppercase tracking-[0.06em]">tool detail</span>
              <CrossCircledIcon className="w-3 h-3 text-red-400" />
            </div>
            <div className="flex gap-1.5 mb-2.5">
              <span className="text-[8px] px-1.5 py-0.5 rounded-full bg-red-400/10 text-red-400 border border-red-400/20 font-mono">failed</span>
            </div>
            <div className="flex-1 font-mono text-[9px] text-zinc-600 leading-relaxed bg-zinc-900/50 rounded-xl p-3 overflow-y-auto">
              {selectedNode.toolCalls.filter(t => t.status === "failure").map((t, i) => (
                <div key={i} className="mb-2">
                  <span className="text-zinc-700">{"// "}{t.name}</span><br/>
                  {t.detail || "No error details available"}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
