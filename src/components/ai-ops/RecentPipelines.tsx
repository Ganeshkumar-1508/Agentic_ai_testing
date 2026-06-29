"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api/api-client";

export function RecentPipelines() {
  const { data, isLoading } = useQuery({
    queryKey: ["recent-pipelines"],
    queryFn: async () => {
      const json = await api.get<{ sessions: any[] }>(`/api/pipeline-activity/recent?limit=10`);
      return (json?.sessions ?? []) as Array<{
        session_id: string;
        status: string;
        goal: string;
        source: string;
        cost: number;
      }>;
    },
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return (
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 space-y-3">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        {[1,2,3].map(i => <div key={i} className="h-10 bg-white/[0.02] rounded-lg animate-pulse" />)}
      </div>
    );
  }

  if (!data || data.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 80, damping: 18 }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 space-y-2"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">Recent Pipeline Runs</span>
        <span className="text-[9px] text-zinc-600 font-mono tabular-nums">{data.length} runs</span>
      </div>
      <div className="space-y-1 max-h-[320px] overflow-y-auto">
        {data.map((s) => (
          <div key={s.session_id}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs border border-transparent hover:bg-white/[0.03] hover:border-white/[0.06] transition-colors cursor-default">
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.status === "running" ? "bg-emerald-400 animate-pulse" : s.status === "completed" ? "bg-emerald-400" : s.status === "failed" ? "bg-red-400" : "bg-zinc-700"}`} />
            <span className="text-zinc-400 font-mono w-20 truncate">{s.session_id.slice(0, 12)}</span>
            <span className="text-zinc-600 flex-1 truncate">{(s.goal || "").slice(0, 70)}</span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${
              s.status === "running" ? "bg-emerald-400/10 text-emerald-400" :
              s.status === "completed" ? "bg-emerald-400/10 text-emerald-400" :
              s.status === "failed" ? "bg-red-400/10 text-red-400" : "bg-zinc-800 text-zinc-600"
            }`}>{s.status}</span>
            {s.cost > 0 && <span className="text-zinc-600 font-mono text-[9px]">${s.cost.toFixed(4)}</span>}
          </div>
        ))}
      </div>
      <div className="text-[10px] text-zinc-600 pt-1 border-t border-white/[0.04] text-center">
        <a href="/pipeline" className="hover:text-zinc-300 transition-colors">View all pipelines →</a>
      </div>
    </motion.div>
  );
}
