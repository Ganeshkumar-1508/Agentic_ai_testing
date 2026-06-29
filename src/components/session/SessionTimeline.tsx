"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Cpu, Wrench, User, Loader2, AlertCircle, ChevronRight, Clock, DollarSign, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface TimelineSpan {
  type: string;
  label: string;
  started_at: string;
  duration_ms: number;
  cost_usd: number;
  status: boolean | string;
  tokens: number;
  preview?: string;
}

interface TokenUsagePoint {
  timestamp: string;
  tokens: number;
  cost_usd: number;
  model: string;
}

interface TimelineData {
  spans: TimelineSpan[];
  token_usage: TokenUsagePoint[];
}

const SPAN_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  tool_call: { bg: "bg-blue-500/15", text: "text-blue-400", border: "border-blue-500/30" },
  llm_response: { bg: "bg-emerald-500/15", text: "text-emerald-400", border: "border-emerald-500/30" },
  user: { bg: "bg-amber-500/15", text: "text-amber-400", border: "border-amber-500/30" },
  running: { bg: "bg-zinc-500/15", text: "text-zinc-400", border: "border-zinc-500/30" },
};

const SPAN_ICONS: Record<string, React.ElementType> = {
  tool_call: Wrench,
  llm_response: Cpu,
  user: User,
};

const FILTER_OPTIONS = [
  { id: "all", label: "All", icon: Activity },
  { id: "llm_response", label: "LLM", icon: Cpu },
  { id: "tool_call", label: "Tools", icon: Wrench },
  { id: "user", label: "User", icon: User },
] as const;

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

function SkeletonBar() {
  return <div className="h-8 rounded-lg bg-zinc-800/30 shimmer" />;
}

export function SessionTimeline({ sessionId }: { sessionId: string | null }) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [selectedSpan, setSelectedSpan] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const d = await api.get<TimelineData>(`/api/sessions/${sessionId}/timeline`);
      setData(d);
    } catch {
      setError("Failed to load timeline");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.spans;
    return data.spans.filter((s) => s.type === filter);
  }, [data, filter]);

  const { minTime, maxTime, timeRange } = useMemo(() => {
    if (!data || data.spans.length === 0) return { minTime: 0, maxTime: 0, timeRange: 1 };
    const times = data.spans.map((s) => new Date(s.started_at).getTime());
    const min = Math.min(...times);
    const max = Math.max(...times) + Math.max(...data.spans.map((s) => s.duration_ms));
    return { minTime: min, maxTime: max, timeRange: Math.max(max - min, 1) };
  }, [data]);

  const totalCost = useMemo(() => {
    if (!data) return 0;
    return data.spans.reduce((s, sp) => s + sp.cost_usd, 0);
  }, [data]);

  const totalTokens = useMemo(() => {
    if (!data) return 0;
    return data.spans.reduce((s, sp) => s + (sp.tokens || 0), 0);
  }, [data]);

  const barLeft = (startedAt: string) => {
    const t = new Date(startedAt).getTime();
    return ((t - minTime) / timeRange) * 100;
  };

  const barWidth = (startedAt: string, durationMs: number) => {
    const t = new Date(startedAt).getTime();
    return Math.max((durationMs / timeRange) * 100, 0.5);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-6 h-6 rounded-lg bg-zinc-800/50 flex items-center justify-center">
          <BarChart3 size={13} className="text-zinc-400" strokeWidth={1.5} />
        </div>
        <div>
          <h3 className="text-xs font-semibold text-zinc-200">Session Timeline</h3>
          <p className="text-[10px] text-zinc-600">LLM calls, tool executions, and user messages over time</p>
        </div>
      </div>

      {data && (
        <div className="flex items-center gap-3 text-[10px] text-zinc-600 font-mono">
          <span className="flex items-center gap-1"><Clock size={10} strokeWidth={1.5} /> {data.spans.length} events</span>
          <span className="flex items-center gap-1"><DollarSign size={10} strokeWidth={1.5} /> ${totalCost.toFixed(4)}</span>
          <span className="flex items-center gap-1"><BarChart3 size={10} strokeWidth={1.5} /> {totalTokens.toLocaleString()} tok</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => <SkeletonBar key={i} />)}
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 py-4 text-zinc-600 text-xs">
          <AlertCircle size={12} strokeWidth={1.5} className="text-red-400/60" />
          <span>{error}</span>
        </div>
      ) : !data || data.spans.length === 0 ? (
        <div className="flex flex-col items-center py-8 text-zinc-600 gap-2">
          <Activity size={16} strokeWidth={1.5} className="text-zinc-700" />
          <p className="text-xs">No timeline events for this session</p>
          <p className="text-[10px] text-zinc-700">Events appear as the agent runs</p>
        </div>
      ) : (
        <>
          <div className="flex gap-1 bg-zinc-900/50 border border-zinc-800/30 rounded-xl p-0.5 w-fit">
            {FILTER_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = filter === opt.id;
              return (
                <button key={opt.id} onClick={() => setFilter(opt.id)}
                  className={cn("flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-lg font-medium transition-all active:scale-[0.97]",
                    active ? "bg-zinc-800 text-zinc-200" : "text-zinc-600 hover:text-zinc-400")}>
                  <Icon size={10} strokeWidth={1.5} />
                  {opt.label}
                </button>
              );
            })}
          </div>

          <div ref={scrollRef} className="overflow-x-auto overflow-y-hidden rounded-xl border border-zinc-800/30 bg-zinc-900/20">
            <div className="relative min-w-[600px] p-4 space-y-1">
              {/* Time axis */}
              <div className="flex items-end h-6 mb-2 text-[9px] font-mono text-zinc-700 border-b border-zinc-800/20">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex-1 text-left" style={{ paddingLeft: i === 0 ? "0" : "4px" }}>
                    {new Date(minTime + (timeRange / 5) * i).toLocaleTimeString()}
                  </div>
                ))}
              </div>

              <AnimatePresence mode="popLayout">
                {filtered.map((span, i) => {
                  const colors = SPAN_COLORS[span.type] || SPAN_COLORS.running;
                  const Icon = SPAN_ICONS[span.type];
                  const left = `${barLeft(span.started_at)}%`;
                  const width = `${barWidth(span.started_at, span.duration_ms)}%`;
                  const isSelected = selectedSpan === i;

                  return (
                    <motion.div
                      key={`${span.type}-${span.started_at}-${i}`}
                      layout
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                      className="relative h-7"
                    >
                      {/* Bar */}
                      <div
                        className={cn("absolute inset-y-0 rounded-md border transition-all cursor-pointer hover:z-10",
                          colors.bg, colors.border,
                          isSelected ? "z-10 ring-1 ring-emerald-500/30" : "")}
                        style={{ left, width, minWidth: "4px" }}
                        onClick={() => setSelectedSpan(isSelected ? null : i)}
                        title={`${span.label} · ${formatDuration(span.duration_ms)}`}
                      >
                        {width.replace("%", "") && parseFloat(width) > 8 && (
                          <div className="flex items-center gap-1 h-full px-2 truncate text-[9px] font-mono text-zinc-400">
                            {Icon && <Icon size={8} strokeWidth={1.5} className="shrink-0" />}
                            <span className="truncate">{span.label}</span>
                            {span.duration_ms > 0 && <span className="shrink-0 text-zinc-600">· {formatDuration(span.duration_ms)}</span>}
                          </div>
                        )}
                      </div>

                      {/* Detail expand */}
                      <AnimatePresence>
                        {isSelected && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            className="absolute top-full left-0 right-0 z-20 mt-1"
                          >
                            <div className="rounded-lg border border-zinc-800/40 bg-zinc-900/90 backdrop-blur-md p-3 space-y-2 text-[11px] shadow-lg">
                              <div className="flex items-center gap-2 font-medium text-zinc-200">
                                {Icon && <Icon size={12} strokeWidth={1.5} className={colors.text} />}
                                {span.label}
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-[10px] font-mono text-zinc-600">
                                <div><span className="text-zinc-700">Duration</span><br /><span className="text-zinc-400">{formatDuration(span.duration_ms)}</span></div>
                                <div><span className="text-zinc-700">Cost</span><br /><span className="text-zinc-400">${span.cost_usd.toFixed(6)}</span></div>
                                <div><span className="text-zinc-700">Tokens</span><br /><span className="text-zinc-400">{span.tokens.toLocaleString()}</span></div>
                              </div>
                              {span.preview && (
                                <p className="text-[10px] text-zinc-500 font-mono bg-zinc-950/50 rounded px-2 py-1 line-clamp-2">{span.preview}</p>
                              )}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.div>
                  );
                })}
              </AnimatePresence>

              {filtered.length === 0 && (
                <div className="flex items-center justify-center h-16 text-[11px] text-zinc-700">
                  No {filter === "all" ? "" : filter} events
                </div>
              )}
            </div>
          </div>

          {/* Token usage mini chart */}
          {data.token_usage.length > 0 && (
            <div className="rounded-xl border border-zinc-800/30 bg-zinc-900/20 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <BarChart3 size={11} className="text-zinc-500" strokeWidth={1.5} />
                <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">Token Burn</span>
              </div>
              <div className="flex items-end gap-[1px] h-8">
                {data.token_usage.map((pt, i) => {
                  const allTokens = data.token_usage.map((t) => t.tokens);
                  const max = Math.max(...allTokens, 1);
                  const h = (pt.tokens / max) * 100;
                  return (
                    <div key={i} className="flex-1 min-w-[2px] rounded-sm bg-emerald-500/20 hover:bg-emerald-500/40 transition-colors"
                      style={{ height: `${Math.max(h, 4)}%` }}
                      title={`${pt.tokens.toLocaleString()} tok · $${pt.cost_usd.toFixed(4)} · ${pt.model}`}
                    />
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
