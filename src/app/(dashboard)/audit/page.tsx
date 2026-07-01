"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { type ElementType } from "react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import {
  Search, Download, Filter, ChevronDown, ChevronRight,
  Loader2, CheckCircle2, XCircle, Clock, AlertTriangle,
  Cpu, Wrench, UserRound, GitBranch, Shield, AlertCircle,
  FileDown,
} from "lucide-react";

interface AuditEvent {
  id: number;
  session_id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  agent_id: string;
  subagent_id: string;
  created_at: string;
  tool_name: string;
  status_label: string;
  input_preview: string;
  output_preview: string;
  duration_ms: number;
  cost_usd: number;
  actor: string;
}

const EVENT_CATEGORIES = [
  { id: "", label: "All" },
  { id: "tool", label: "Tools" },
  { id: "llm", label: "LLM" },
  { id: "subagent", label: "Subagents" },
  { id: "approval", label: "Approvals" },
  { id: "error", label: "Errors" },
  { id: "guardrail", label: "Guardrails" },
  { id: "session", label: "Sessions" },
];

const STATUS_FILTERS = ["", "completed", "failed", "running", "cancelled"];

const ACTOR_FILTERS = ["", "agent", "human"];

const EVENT_TYPE_ICONS: Record<string, ElementType> = {
  ToolExecutionStarted: Wrench,
  ToolExecutionCompleted: Wrench,
  LLMCallStarted: Cpu,
  LLMCallCompleted: Cpu,
  TokenGenerated: Cpu,
  ReasoningGenerated: Cpu,
  SubagentSpawned: GitBranch,
  SubagentCompleted: GitBranch,
  ApprovalRequired: UserRound,
  "approval:required": UserRound,
  ErrorEvent: AlertTriangle,
  error: AlertCircle,
  "guardrail:denied": Shield,
  default: Clock,
};

function formatTime(iso: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

function shortId(id: string): string {
  if (!id) return "";
  return id.length > 12 ? id.slice(0, 12) + "..." : id;
}

function eventColor(type: string): string {
  if (type.includes("Started") || type.includes("start")) return "text-amber-400";
  if (type.includes("Completed") || type.includes("complete")) return "text-emerald-400";
  if (type.includes("Error") || type.includes("error")) return "text-red-400";
  if (type.includes("Approval") || type.includes("approval")) return "text-violet-400";
  if (type.includes("guardrail") || type.includes("blocked")) return "text-orange-400";
  return "text-zinc-400";
}

function eventBg(type: string): string {
  if (type.includes("Started") || type.includes("start")) return "bg-amber-500/8";
  if (type.includes("Completed") || type.includes("complete")) return "bg-emerald-500/8";
  if (type.includes("Error") || type.includes("error")) return "bg-red-500/8";
  if (type.includes("Approval") || type.includes("approval")) return "bg-violet-500/8";
  if (type.includes("guardrail") || type.includes("blocked")) return "bg-orange-500/8";
  return "bg-zinc-800/20";
}

const springProps = { type: "spring" as const, stiffness: 200, damping: 24 };

export default function AuditPage() {
  const [category, setCategory] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [search, setSearch] = useState("");
  const [days, setDays] = useState(7);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const queryParams = useMemo(() => {
    const p = new URLSearchParams();
    if (category) p.set("event_type", category);
    if (statusFilter) p.set("status", statusFilter);
    if (actorFilter === "human") p.set("search", '"actor":"human"');
    if (search) p.set("search", search);
    p.set("days", String(days));
    p.set("limit", "200");
    return p.toString();
  }, [category, statusFilter, actorFilter, search, days]);

  const { data, isLoading } = useQuery({
    queryKey: ["audit", queryParams],
    queryFn: async () => {
      const res = await api.get<{ events: AuditEvent[]; total: number }>(`/api/audit?${queryParams}`);
      return res;
    },
    refetchInterval: 15_000,
  });

  const events = data?.events ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-violet-400/70" />
        <span className="text-xs font-mono text-zinc-600">/audit</span>
      </div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
            <Search size={16} className="text-zinc-400" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Audit Trail</h1>
            <p className="text-sm text-zinc-600 mt-1">{total.toLocaleString()} events · last {days} days</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="bg-zinc-800/50 border border-zinc-700 rounded-lg px-2 py-1.5 text-[10px] text-zinc-400 outline-none focus:border-emerald-500/40">
            <option value={1}>24h</option>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
          <a href={`/api/audit/export?fmt=csv&event_type=${category}&days=${days}`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-800/40 text-zinc-400 text-[10px] hover:text-zinc-200 transition-colors"
            download>
            <FileDown size={11} strokeWidth={1.5} /> CSV
          </a>
          <a href={`/api/audit/export?fmt=json&event_type=${category}&days=${days}`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-800/40 text-zinc-400 text-[10px] hover:text-zinc-200 transition-colors"
            download>
            <FileDown size={11} strokeWidth={1.5} /> JSON
          </a>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex gap-1 bg-zinc-900/50 border border-zinc-800/30 rounded-xl p-0.5">
          {EVENT_CATEGORIES.map((cat) => (
            <button key={cat.id} onClick={() => setCategory(cat.id)}
              className={cn("px-2.5 py-1 text-[10px] rounded-lg font-medium transition-all active:scale-[0.97]",
                category === cat.id ? "bg-zinc-800 text-zinc-200" : "text-zinc-600 hover:text-zinc-400")}>
              {cat.label}
            </button>
          ))}
        </div>
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search event data..."
          className="bg-zinc-800/40 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-[11px] text-zinc-300 placeholder-zinc-600 w-48 outline-none focus:border-emerald-500/40" />
        {(statusFilter || actorFilter) && (
          <button onClick={() => { setStatusFilter(""); setActorFilter(""); }}
            className="text-[9px] text-zinc-600 hover:text-zinc-400 transition-colors">Clear filters</button>
        )}
      </div>

      {/* Events */}
      {isLoading ? (
        <div className="space-y-1">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-12 rounded-xl border border-zinc-800/30 bg-zinc-900/20 shimmer" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-zinc-600 gap-3">
          <Search size={24} strokeWidth={1} className="text-zinc-700" />
          <p className="text-sm">No audit events found</p>
          <p className="text-xs text-zinc-700">Try expanding the date range or clearing filters</p>
        </div>
      ) : (
        <div className="space-y-1">
          {events.map((ev, i) => {
            const Icon = EVENT_TYPE_ICONS[ev.event_type] || EVENT_TYPE_ICONS.default;
            const isExpanded = expandedId === ev.id;
            return (
              <motion.div key={ev.id} layout initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                transition={{ ...springProps, delay: i * 0.01 }}
                className={cn("rounded-xl border transition-all cursor-pointer",
                  isExpanded ? "border-zinc-700/50 bg-zinc-900/40" : "border-zinc-800/30 bg-zinc-900/15 hover:border-zinc-700/40")}>
                <div className="flex items-center gap-3 px-3 py-2" onClick={() => setExpandedId(isExpanded ? null : ev.id)}>
                  <div className={cn("w-6 h-6 rounded-lg flex items-center justify-center shrink-0", eventBg(ev.event_type))}>
                    <Icon size={11} className={eventColor(ev.event_type)} strokeWidth={1.5} />
                  </div>
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="text-[11px] text-zinc-400 font-mono shrink-0 w-16">{formatTime(ev.created_at).split(",")[0]}</span>
                    <span className={cn("text-[10px] font-mono shrink-0", eventColor(ev.event_type))}>{ev.event_type}</span>
                    {ev.actor === "human" && (
                      <span className="text-[8px] px-1 py-0.5 rounded bg-violet-500/10 text-violet-400 font-mono">human</span>
                    )}
                    {ev.tool_name && <span className="text-[11px] text-zinc-500 font-mono shrink-0">{ev.tool_name}</span>}
                    <span className="text-[10px] text-zinc-700 font-mono truncate">{ev.input_preview || ev.output_preview}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[9px] text-zinc-700 font-mono shrink-0">
                    {ev.status_label && (
                      <span className={cn(
                        ev.status_label === "completed" ? "text-emerald-400" :
                        ev.status_label === "failed" ? "text-red-400" : "text-zinc-500"
                      )}>{ev.status_label}</span>
                    )}
                    {ev.cost_usd > 0 && <span>${Number(ev.cost_usd).toFixed(4)}</span>}
                    {ev.duration_ms > 0 && <span>{ev.duration_ms < 1000 ? `${ev.duration_ms}ms` : `${(ev.duration_ms / 1000).toFixed(1)}s`}</span>}
                  </div>
                  {isExpanded ? <ChevronDown size={10} className="text-zinc-600" /> : <ChevronRight size={10} className="text-zinc-600" />}
                </div>

                <AnimatePresence>
                  {isExpanded && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                      transition={springProps} className="border-t border-zinc-800/30 px-4 py-3 space-y-2 overflow-hidden">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[10px]">
                        <div>
                          <span className="text-zinc-700 font-medium">Event ID</span>
                          <p className="text-zinc-500 font-mono mt-0.5">{ev.id}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Session</span>
                          <p className="text-zinc-500 font-mono mt-0.5">{shortId(ev.session_id || "")}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Agent</span>
                          <p className="text-zinc-500 font-mono mt-0.5">{shortId(ev.agent_id || "")}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Subagent</span>
                          <p className="text-zinc-500 font-mono mt-0.5">{shortId(ev.subagent_id || "")}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Timestamp</span>
                          <p className="text-zinc-500 font-mono mt-0.5">{formatTime(ev.created_at)}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Type</span>
                          <p className="text-zinc-500 font-mono mt-0.5">{ev.event_type}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Actor</span>
                          <p className={cn("font-mono mt-0.5", ev.actor === "human" ? "text-violet-400" : "text-zinc-500")}>{ev.actor}</p>
                        </div>
                        <div>
                          <span className="text-zinc-700 font-medium">Status</span>
                          <p className={cn("font-mono mt-0.5",
                            ev.status_label === "completed" ? "text-emerald-400" :
                            ev.status_label === "failed" ? "text-red-400" : "text-zinc-500")}>{ev.status_label || "—"}</p>
                        </div>
                      </div>
                      {ev.input_preview && (
                        <div className="space-y-1">
                          <span className="text-[10px] text-zinc-700 font-medium">Input</span>
                          <div className="rounded-lg bg-zinc-900/60 border border-zinc-800/30 px-3 py-2 text-[10px] text-zinc-500 font-mono whitespace-pre-wrap max-h-24 overflow-y-auto">
                            {ev.input_preview}
                          </div>
                        </div>
                      )}
                      {ev.output_preview && (
                        <div className="space-y-1">
                          <span className="text-[10px] text-zinc-700 font-medium">Output</span>
                          <div className="rounded-lg bg-zinc-900/60 border border-zinc-800/30 px-3 py-2 text-[10px] text-zinc-500 font-mono whitespace-pre-wrap max-h-24 overflow-y-auto">
                            {ev.output_preview}
                          </div>
                        </div>
                      )}
                      {ev.cost_usd > 0 || ev.duration_ms > 0 ? (
                        <div className="flex items-center gap-3 text-[10px] text-zinc-700 font-mono">
                          {ev.cost_usd > 0 && <span>Cost: ${Number(ev.cost_usd).toFixed(6)}</span>}
                          {ev.duration_ms > 0 && <span>Duration: {ev.duration_ms < 1000 ? `${ev.duration_ms}ms` : `${(ev.duration_ms / 1000).toFixed(2)}s`}</span>}
                        </div>
                      ) : null}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
