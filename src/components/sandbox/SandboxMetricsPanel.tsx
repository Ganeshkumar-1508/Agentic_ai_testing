"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Container, Activity, X } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface SandboxMetric {
  id: number;
  session_id: string;
  container_id: string;
  container_name: string;
  image: string;
  status: string;
  running: boolean;
  exit_code: number;
  oom_killed: boolean;
  restart_count: number;
  duration_ms: number;
  cpu_shares: number;
  memory_limit_bytes: number;
  error: string;
  created_at: string;
}

export function SandboxMetricsPanel() {
  const [selected, setSelected] = useState<SandboxMetric | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["sandbox-metrics"],
    queryFn: async () => {
      const json = await api.get<{ metrics?: SandboxMetric[] }>(`/api/ops/sandbox-metrics?limit=20`);
      return json?.metrics ?? [];
    },
    refetchInterval: 30_000,
  });

  const metrics = data ?? [];

  if (isLoading) {
    return (
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4">
        <div className="w-36 h-4 rounded-full shimmer-bg" />
        {[1,2,3].map(i => <div key={i} className="h-12 bg-white/[0.02] rounded-xl animate-pulse" />)}
      </div>
    );
  }

  if (metrics.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 80, damping: 18 }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Container className="w-4 h-4 text-zinc-500" strokeWidth={1.5} />
          <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Sandbox Containers</span>
        </div>
        <span className="text-[10px] text-zinc-600 font-mono tabular-nums">{metrics.length} containers</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/[0.05] text-zinc-500">
              <th className="text-left py-2 px-3 font-medium">Container</th>
              <th className="text-left py-2 px-3 font-medium">Image</th>
              <th className="text-center py-2 px-3 font-medium">Status</th>
              <th className="text-right py-2 px-3 font-medium">Duration</th>
              <th className="text-right py-2 px-3 font-medium">Exit</th>
              <th className="text-right py-2 px-3 font-medium">Restarts</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => (
              <motion.tr
                key={m.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03, type: "spring", stiffness: 100, damping: 20 }}
                onClick={() => setSelected(selected?.id === m.id ? null : m)}
                className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors cursor-pointer"
              >
                <td className="py-2.5 px-3">
                  <span className="text-zinc-300 font-mono">{m.container_name || m.container_id || "-"}</span>
                </td>
                <td className="py-2.5 px-3 text-zinc-500 truncate max-w-[120px]">{m.image || "-"}</td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full font-mono ${
                    m.status === "running" ? "bg-emerald-400/10 text-emerald-400" :
                    m.status === "exited" ? (m.exit_code === 0 ? "bg-zinc-800 text-zinc-500" : "bg-red-400/10 text-red-400") :
                    "bg-zinc-800 text-zinc-600"
                  }`}>
                    {m.status === "running" && <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />}
                    {m.status || "unknown"}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-right text-zinc-400 font-mono tabular-nums">
                  {m.duration_ms ? `${(m.duration_ms / 1000).toFixed(0)}s` : "-"}
                </td>
                <td className="py-2.5 px-3 text-right font-mono tabular-nums">
                  <span className={m.exit_code === 0 ? "text-zinc-500" : "text-red-400"}>{m.exit_code}</span>
                </td>
                <td className="py-2.5 px-3 text-right text-zinc-600 font-mono tabular-nums">{m.restart_count}</td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden border-t border-white/[0.05] pt-4"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Container Details</span>
              <button onClick={() => setSelected(null)} className="p-1 rounded text-zinc-600 hover:text-zinc-400">
                <X className="w-3 h-3" strokeWidth={1.5} />
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Container ID", value: selected.container_id || "-" },
                { label: "Session ID", value: selected.session_id.slice(0, 12) + "..." },
                { label: "Exit Code", value: String(selected.exit_code), color: selected.exit_code === 0 ? "text-emerald-400" : "text-red-400" },
                { label: "OOM Killed", value: selected.oom_killed ? "Yes" : "No", color: selected.oom_killed ? "text-red-400" : "text-zinc-400" },
                { label: "Memory Limit", value: selected.memory_limit_bytes ? formatBytes(selected.memory_limit_bytes) : "-" },
                { label: "CPU Shares", value: String(selected.cpu_shares || "-") },
                { label: "Duration", value: selected.duration_ms ? formatDuration(selected.duration_ms) : "-" },
                { label: "Restarts", value: String(selected.restart_count) },
              ].map((f) => (
                <div key={f.label} className="bg-white/[0.01] border border-white/[0.04] rounded-lg p-2.5">
                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider">{f.label}</div>
                  <div className={`text-xs font-mono mt-0.5 tabular-nums ${f.color || "text-zinc-300"}`}>{f.value}</div>
                </div>
              ))}
            </div>
            {selected.error && (
              <div className="mt-3 px-3 py-2 rounded-lg bg-red-500/5 border border-red-500/10 text-[10px] text-red-400 font-mono">
                {selected.error}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)}GB`;
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(0)}MB`;
  return `${(bytes / 1024).toFixed(0)}KB`;
}

function formatDuration(ms: number): string {
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(0)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}
