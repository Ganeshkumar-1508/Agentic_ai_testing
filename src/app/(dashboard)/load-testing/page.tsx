"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { Gauge, Zap, Clock, AlertTriangle } from "lucide-react";

interface LoadRun {
  id: string;
  test_type: string;
  vu_count: number;
  duration_sec: number;
  avg_latency_ms: number;
  p99_latency_ms: number;
  error_rate: number;
  rps: number;
  status: string;
  created_at: string;
}

export default function LoadTestingPage() {
  const [runs, setRuns] = useState<LoadRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ runs?: LoadRun[] }>("/api/testing/load/runs")
      .then(d => setRuns(d?.runs ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const completedRuns = runs.filter(r => r.status === "completed");
  const avgRps = completedRuns.length > 0 ? Math.round(completedRuns.reduce((s, r) => s + (r.rps ?? 0), 0) / completedRuns.length) : 0;
  const avgLatency = completedRuns.length > 0 ? Math.round(completedRuns.reduce((s, r) => s + (r.avg_latency_ms ?? 0), 0) / completedRuns.length) : 0;
  const highErrorRuns = runs.filter(r => (r.error_rate ?? 0) > 5).length;

  return (
    <div className="space-y-6">
      <PageHeader title="Load Testing" description="Performance and load testing for API endpoints" />

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total Runs", value: runs.length, icon: Gauge, color: "text-zinc-300" },
          { label: "Avg RPS", value: avgRps, icon: Zap, color: "text-emerald-400" },
          { label: "Avg Latency", value: `${avgLatency}ms`, icon: Clock, color: "text-blue-400" },
          { label: "High Error", value: highErrorRuns, icon: AlertTriangle, color: "text-red-400" },
        ].map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
            className="rounded-[2rem] p-4 card-wireframe">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">{s.label}</span>
              <s.icon className={`w-3.5 h-3.5 ${s.color}`} strokeWidth={1.5} />
            </div>
            <div className={`text-2xl font-semibold font-mono ${s.color}`}>{s.value}</div>
          </motion.div>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-16 rounded-xl shimmer-bg" />)}</div>
      ) : runs.length === 0 ? (
        <div className="text-center py-16 text-sm text-zinc-600">
          <Gauge className="w-8 h-8 mx-auto mb-3 text-zinc-700" strokeWidth={1} />
          No load tests run yet
        </div>
      ) : (
        <div className="space-y-1.5">
          {runs.map((r, i) => (
            <motion.div key={r.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
              className="flex items-center gap-4 px-4 py-3 rounded-xl bg-card border border-white/[0.06] hover:border-white/[0.1] transition-all">
              <span className={cn("w-2 h-2 rounded-full shrink-0", r.status === "running" ? "bg-emerald-400 animate-pulse" : r.status === "completed" ? "bg-emerald-400" : r.status === "failed" ? "bg-red-400" : "bg-zinc-600")} />
              <div className="flex-1 min-w-0">
                <span className="text-[13px] text-zinc-200 truncate block">{r.test_type} test</span>
                <span className="text-[10px] text-zinc-600 font-mono">{r.vu_count} VUs / {r.duration_sec}s</span>
              </div>
              <span className="text-[11px] font-mono text-zinc-500">{r.rps ?? 0} rps</span>
              <span className="text-[11px] font-mono text-zinc-500">{r.avg_latency_ms ?? 0}ms avg</span>
              <span className="text-[11px] font-mono text-zinc-500">p99: {r.p99_latency_ms ?? 0}ms</span>
              <span className={cn("text-[11px] font-mono", (r.error_rate ?? 0) > 5 ? "text-red-400" : "text-zinc-500")}>{(r.error_rate ?? 0).toFixed(1)}% err</span>
              <Badge variant="outline" className={cn("text-[10px] px-2 py-0 rounded font-medium", r.status === "completed" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : r.status === "failed" ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-zinc-800 text-zinc-500 border-zinc-700")}>
                {r.status}
              </Badge>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
