"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { StatsCard } from "@/components/shared/StatsCard";
import { PulseDot } from "@/components/ai-ops/PulseDot";
import { ApprovalQueue } from "@/components/agents/ApprovalQueue";
import { AutonomySlider } from "@/components/agents/AutonomySlider";
import { Bot, Target, Clock, DollarSign, Activity, Terminal, ShieldCheck } from "lucide-react";
import { RecentPipelines } from "@/components/ai-ops/RecentPipelines";
import { useEventSource } from "@/lib/hooks/use-event-source";
import { api, BASE_URL } from "@/lib/api/api-client";

// Recharts ships browser-only code that throws "Cannot access 'e' before
// initialization" during Next 16's prerender + React 19 hydration path. Loading
// these client-only is the durable fix (see recharts issue #5663).
const ModelRoutingStats = dynamic(
  () => import("@/components/ai-ops/ModelRoutingStats").then((m) => m.ModelRoutingStats),
  { ssr: false, loading: () => <div className="h-[260px] animate-pulse rounded-lg shimmer-bg" /> }
);
const PipelineMetricsPanel = dynamic(
  () => import("@/components/ai-ops/PipelineMetricsPanel").then((m) => m.PipelineMetricsPanel),
  { ssr: false, loading: () => <div className="h-[260px] animate-pulse rounded-lg shimmer-bg" /> }
);

const SSE_EVENT_TYPES = [
  "session.started",
  "session.completed",
  "session.failed",
  "session.cancelled",
  "subagent.spawned",
  "subagent.thinking",
  "subagent.tool_start",
  "subagent.tool_completed",
  "subagent.complete",
  "subagent.failed",
  "subagent.interrupted",
  "stage:start",
  "stage:progress",
  "stage:complete",
  "steer.injected",
  "approval.resolved",
] as const;

type Subagent = {
  id: string;
  goal: string;
  depth: number;
  status: string;
  interrupted?: boolean;
  error?: string;
};

type ActiveSession = {
  id: string | null;
  status: string | null;
  total_tokens: number;
  total_cost: number;
  created_at: string | null;
};

type DelegateEvent = {
  id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  parent_id: string | null;
  agent_id: string | null;
  created_at: string | null;
};

function eventColor(eventType: string): string {
  if (eventType.includes("spawned")) return "text-emerald-400 bg-emerald-500/10";
  if (eventType.includes("started")) return "text-zinc-400 bg-zinc-500/10";
  if (eventType.includes("completed")) return "text-emerald-400 bg-emerald-500/10";
  if (eventType.includes("failed")) return "text-red-400 bg-red-500/10";
  if (eventType.includes("cancelled")) return "text-amber-400 bg-amber-500/10";
  if (eventType.includes("thinking")) return "text-zinc-400 bg-zinc-500/10";
  if (eventType.includes("tool_start") || eventType.includes("tool_completed")) return "text-amber-400 bg-amber-500/10";
  if (eventType.includes("resolved")) return "text-blue-400 bg-blue-500/10";
  return "text-zinc-500 bg-zinc-800";
}

function eventLabel(eventType: string): string {
  const short = eventType.replace(/^(delegate|pipeline|session)\./, "");
  return short.replace(/_/g, " ").toUpperCase();
}

function EventIcon({ eventType }: { eventType: string }) {
  if (eventType.includes("failed")) return <span className="w-1.5 h-1.5 rounded-full bg-red-400/60" />;
  if (eventType.includes("completed")) return <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />;
  if (eventType.includes("spawned")) return <PulseDot color="bg-emerald-400" />;
  if (eventType.includes("thinking")) return <PulseDot color="bg-zinc-400" />;
  if (eventType.includes("tool_start")) return <PulseDot color="bg-amber-400" />;
  if (eventType.includes("started")) return <PulseDot color="bg-zinc-400" />;
  if (eventType.includes("resolved")) return <span className="w-1.5 h-1.5 rounded-full bg-blue-400/60" />;
  return <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />;
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour12: false });
}

function elapsedSince(iso: string | null): string {
  if (!iso) return "0s";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function depthLabel(d: number): string {
  return `d${d}`;
}

export default function SwarmPage() {
  const [subagents, setSubagents] = useState<Subagent[]>([]);
  const [session, setSession] = useState<ActiveSession | null>(null);
  const [events, setEvents] = useState<DelegateEvent[]>([]);
  const [toolCallsTotal, setToolCallsTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedSubagent, setSelectedSubagent] = useState<string | null>(null);

  const sseUrl = session?.id && session.status === "running"
    ? `${BASE_URL}/api/delegate/${session.id}/stream`
    : null;

  useEventSource({
    url: sseUrl,
    eventTypes: SSE_EVENT_TYPES,
    onEvent: (event_type, rawData) => {
      const data = (rawData ?? {}) as {
        parent_id?: string;
        agent_id?: string;
        subagent_id?: string;
        goal?: string;
        depth?: number;
        error?: string;
      };
      const sseEvent: DelegateEvent = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        event_type,
        event_data: data as Record<string, unknown>,
        parent_id: data.parent_id ?? null,
        agent_id: data.agent_id ?? null,
        created_at: new Date().toISOString(),
      };
      setEvents((prev) => [sseEvent, ...prev].slice(0, 100));

      if (event_type === "subagent.spawned") {
        if (!data.subagent_id) return;
        const subagentId = data.subagent_id;
        const goal = data.goal || "";
        const depth = data.depth || 0;
        setSubagents((prev) => [
          ...prev.filter((s) => s.id !== subagentId),
          {
            id: subagentId,
            goal,
            depth,
            status: "running",
          },
        ]);
      } else if (event_type === "subagent.complete") {
        setSubagents((prev) =>
          prev.map((s) =>
            s.id === data.subagent_id ? { ...s, status: "completed" } : s
          )
        );
      } else if (event_type === "subagent.failed") {
        setSubagents((prev) =>
          prev.map((s) =>
            s.id === data.subagent_id
              ? { ...s, status: "failed", error: data.error }
              : s
          )
        );
      } else if (event_type === "session.completed") {
        setSession((prev) =>
          prev ? { ...prev, status: "completed" } : prev
        );
      } else if (event_type === "session.failed") {
        setSession((prev) =>
          prev ? { ...prev, status: "failed" } : prev
        );
      }
    },
  });

  const fetchData = useCallback(async () => {
    try {
      const [activeData, eventsData] = await Promise.all([
        api.get<{ subagents?: Subagent[]; active_session?: ActiveSession | null; tool_calls_total?: number }>("/api/ops/swarm/active"),
        api.get<{ events?: DelegateEvent[] }>("/api/ops/swarm/delegate-events?limit=30"),
      ]);

      setSubagents(activeData?.subagents ?? []);
      setSession(activeData?.active_session ?? null);
      setToolCallsTotal(activeData?.tool_calls_total ?? 0);
      setEvents((prev) => {
        const incoming = eventsData?.events ?? [];
        if (prev.length === 0) return incoming;
        const existingIds = new Set(prev.slice(0, 30).map((e) => e.id));
        const merged = [...prev];
        for (const ev of incoming) {
          if (!existingIds.has(ev.id)) {
            merged.unshift(ev);
          }
        }
        return merged.slice(0, 100);
      });
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  // Polling fallback (reduced when SSE is active)
  useEffect(() => {
    fetchData();
    if (session?.id && session.status === "running") {
      const interval = setInterval(fetchData, 15000);
      return () => clearInterval(interval);
    } else {
      const interval = setInterval(fetchData, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchData, session?.id, session?.status]);

  const activeCount = subagents.filter((s) => s.status === "running").length;

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard
          icon={<Bot size={16} />}
          label="Active Subagents"
          value={activeCount}
          sub={subagents.length > 0 ? `${subagents.length} total spawned` : "No active sessions"}
          delay={0.05}
        />
        <StatsCard
          icon={<Target size={16} />}
          label="Tool Calls"
          value={toolCallsTotal}
          sub="delegate tool events"
          delay={0.1}
        />
        <StatsCard
          icon={<Clock size={16} />}
          label="Elapsed"
          value={session?.created_at ? elapsedSince(session.created_at) : "0s"}
          sub={session?.id ? `session: ${session.id.slice(0, 8)}` : "No active session"}
          delay={0.15}
        />
        <StatsCard
          icon={<DollarSign size={16} />}
          label="Tokens & Cost"
          value={session?.total_tokens ? `${Math.round(session.total_tokens / 1000)}k` : "0"}
          sub={session?.total_cost != null ? `$${session.total_cost.toFixed(3)}` : "No cost data"}
          delay={0.2}
        />
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6"
          >
            {[0, 1].map((i) => (
              <div key={i} className="h-80 rounded-2xl shimmer-bg border border-zinc-800/30" />
            ))}
          </motion.div>
        ) : (
          <motion.div
            key="content"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
            className="space-y-6"
          >
            {/* Main grid: Delegation Tree + Event Stream */}
            <div className="grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6">
              {/* Delegation Tree */}
              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-sm font-medium text-zinc-100">Delegation Tree</h2>
                  <div className="flex items-center gap-3">
                    <AutonomySlider sessionId={session?.id || ""} />
                    <div className="flex items-center gap-3 text-[10px] text-zinc-500">
                      <span className="flex items-center gap-1.5"><PulseDot color="bg-emerald-400" /> Running</span>
                      <span className="flex items-center gap-1.5 opacity-50"><span className="w-1.5 h-1.5 rounded-full bg-zinc-600" /> Done</span>
                      <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-red-400/60" /> Failed</span>
                    </div>
                  </div>
                </div>

                {subagents.length === 0 && !session ? (
                  <div className="flex flex-col items-center justify-center h-64 text-zinc-600">
                    <Bot size={32} className="opacity-20 mb-3" strokeWidth={1} />
                    <p className="text-sm">No active delegation tree</p>
                    <p className="text-xs mt-1">Run a pipeline to see subagent activity</p>
                  </div>
                ) : (
                  <div className="relative">
                    <svg viewBox="0 0 640 220" className="w-full overflow-visible">
                      {/* Root Agent */}
                      <rect x="270" y="0" width="100" height="32" rx="16" fill="#34d399" opacity="0.9" />
                      <text x="320" y="21" textAnchor="middle" fill="#09090b" fontSize="10" fontWeight="600" fontFamily="Geist, system-ui, sans-serif">Root Agent</text>

                      {/* Connector lines */}
                      <line x1="320" y1="32" x2="320" y2="50" stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" />
                      <line x1="80" y1="50" x2="560" y2="50" stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" />

                      {/* Subagent nodes */}
                      {subagents.slice(0, 4).map((sa, i) => {
                        const xPositions = [80, 260, 440, 560];
                        const x = xPositions[i] ?? 80 + i * 120;
                        const isRunning = sa.status === "running";
                        const isFailed = sa.status === "failed" || sa.interrupted;
                        const fill = isFailed ? "rgba(248,113,113,0.08)" : isRunning ? "rgba(52,211,153,0.08)" : "rgba(255,255,255,0.02)";
                        const stroke = isFailed ? "rgba(248,113,113,0.25)" : isRunning ? "rgba(52,211,153,0.25)" : "rgba(255,255,255,0.06)";
                        const dotColor = isFailed ? "bg-red-400" : isRunning ? "bg-emerald-400" : "bg-zinc-600";

                        return (
                          <g key={sa.id} onClick={() => setSelectedSubagent(selectedSubagent === sa.id ? null : sa.id)} style={{ cursor: "pointer" }}>
                            <line x1={x} y1="50" x2={x} y2="70" stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" />
                            <rect x={x - 60} y="70" width="120" height="36" rx="18" fill={fill} stroke={stroke} strokeWidth="1" />
                            {isRunning && (
                              <circle cx={x - 40} cy="88" r="4" fill="#34d399">
                                <animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite" />
                              </circle>
                            )}
                            {isFailed && <circle cx={x - 40} cy="88" r="4" fill="#f87171" />}
                            {!isRunning && !isFailed && <circle cx={x - 40} cy="88" r="4" fill="#a1a1aa" />}
                            <text x={x - 28} y="90" fill="#f4f4f5" fontSize="10" fontWeight="500">
                              {sa.goal.slice(0, 12)}{sa.goal.length > 12 ? ".." : ""}
                            </text>
                            <text x={x - 28} y="102" fill="#a1a1aa" fontSize="8" fontFamily="JetBrains Mono, monospace">
                              depth={sa.depth}, {sa.status}
                            </text>

                            {/* Depth marker */}
                            <line x1={640} y1={sa.depth === 0 ? 16 : sa.depth === 1 ? 88 : 88} x2={652} y2={sa.depth === 0 ? 16 : sa.depth === 1 ? 88 : 88} stroke="rgba(255,255,255,0.06)" strokeWidth="1" strokeDasharray="2 2" />
                            <text x={656} y={sa.depth === 0 ? 20 : sa.depth === 1 ? 92 : 92} fill="#52525b" fontSize="8" fontFamily="JetBrains Mono, monospace">{depthLabel(sa.depth)}</text>
                          </g>
                        );
                      })}

                      {/* Legend hint */}
                      {subagents.length > 4 && (
                        <text x="320" y="200" textAnchor="middle" fill="#52525b" fontSize="9" fontFamily="JetBrains Mono, monospace">
                          +{subagents.length - 4} more subagents
                        </text>
                      )}
                    </svg>

                    {/* Subagent summary cards */}
                    {subagents.length > 0 && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-4">
                        {subagents.slice(0, 4).map((sa) => {
                          const isFailed = sa.status === "failed" || sa.interrupted;
                          const isRunning = sa.status === "running";
                          const borderColor = isFailed ? "border-red-500/10" : isRunning ? "border-emerald-500/10" : "border-white/[0.06]";
                          const bgColor = isFailed ? "bg-red-500/5" : isRunning ? "bg-emerald-500/5" : "bg-white/[0.02]";
                          return (
                            <div
                              key={sa.id}
                              className={`p-2.5 rounded-xl ${bgColor} ${borderColor} border cursor-pointer transition-colors hover:brightness-110 ${selectedSubagent === sa.id ? "ring-1 ring-emerald-500/30" : ""}`}
                              onClick={() => setSelectedSubagent(selectedSubagent === sa.id ? null : sa.id)}
                            >
                              <div className="flex items-center gap-1.5 mb-0.5">
                                {isRunning ? <PulseDot color="bg-emerald-400" /> : <span className={`w-1.5 h-1.5 rounded-full ${isFailed ? "bg-red-400/60" : "bg-zinc-600"}`} />}
                                <span className="text-[11px] font-medium text-zinc-100 truncate">{sa.goal.slice(0, 16)}</span>
                              </div>
                              <div className="text-[9px] text-zinc-500 font-mono truncate">d={sa.depth}, {sa.status}</div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Event Stream */}
              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-medium text-zinc-100">Event Stream</h2>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400/80 font-mono">live</span>
                  {session?.status === "running" && (
                    <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      SSE
                    </span>
                  )}
                </div>
                <div className="space-y-0.5 max-h-[420px] overflow-y-auto pr-1 -mr-1">
                  {events.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-zinc-600">
                      <Activity size={24} className="opacity-20 mb-2" strokeWidth={1} />
                      <p className="text-xs">No events yet — run a pipeline to see live activity</p>
                    </div>
                  ) : (
                    events.map((ev) => (
                      <div key={ev.id} className="flex gap-2.5 py-2 px-2 -mx-2 rounded-lg hover:bg-white/[0.02] transition-colors">
                        <div className="flex flex-col items-center gap-1 pt-0.5">
                          <EventIcon eventType={ev.event_type} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-zinc-500 font-mono tabular-nums">{formatTime(ev.created_at)}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${eventColor(ev.event_type)}`}>
                              {eventLabel(ev.event_type)}
                            </span>
                          </div>
                          <div className="text-sm text-zinc-300 mt-0.5 truncate">
                            {typeof ev.event_data?.preview === "string" ? ev.event_data.preview : ev.event_type}
                          </div>
                          {ev.agent_id && (
                            <div className="text-[10px] text-zinc-600 mt-0.5 font-mono">
                              {ev.agent_id.slice(0, 8)}{ev.parent_id ? ` / parent: ${ev.parent_id.slice(0, 8)}` : ""}
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Selected subagent tool trace */}
            {/* Approval Queue */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6"
            >
              <div className="flex items-center gap-2 mb-4">
                <ShieldCheck size={14} className="text-amber-400" strokeWidth={1.5} />
                <h2 className="text-sm font-medium text-zinc-100">Pending Approvals</h2>
              </div>
              <ApprovalQueue
                sessionId={session?.id || ""}
                onApprove={(id, scope) => fetchData()}
                onDeny={() => fetchData()}
              />
            </motion.div>

            {selectedSubagent && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-amber-500/10 flex items-center justify-center">
                      <PulseDot color="bg-amber-400" />
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-zinc-100">
                        {subagents.find((s) => s.id === selectedSubagent)?.goal ?? "Subagent"} — Tool Trace
                      </h3>
                      <span className="text-[10px] text-zinc-500 font-mono">
                        {selectedSubagent.slice(0, 8)}, depth={subagents.find((s) => s.id === selectedSubagent)?.depth ?? "?"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-zinc-900/80 border border-zinc-800">
                  <div className="text-[11px] font-mono leading-relaxed">
                    <div className="text-zinc-500">$ delegate_task --role leaf --tools [read, write]</div>
                    <div className="text-emerald-400/80 mt-1">Tool calls streamed in real-time...</div>
                    <div className="text-zinc-600 mt-3 border-t border-zinc-800 pt-3 text-[10px]">
                      Select a subagent from the tree above to see its tool trace. Full output stored as
                      <span className="text-emerald-400/60 underline decoration-emerald-500/30 cursor-pointer ml-1">tool_result:{session?.id?.slice(0, 8) ?? "?"}:{selectedSubagent.slice(0, 8)}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <PipelineMetricsPanel />
      <RecentPipelines />

      <ModelRoutingStats />
    </div>
  );
}
