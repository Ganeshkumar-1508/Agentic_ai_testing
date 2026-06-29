"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { Layers, GitBranch, ArrowRight, Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface Session {
  id: string;
  status: string;
  goal: string;
  repo_url?: string;
  created_at: string;
  end_reason?: string;
}

const STATUS_CONFIG = {
  running: { icon: Loader2, color: "text-emerald-400", bg: "bg-emerald-500/10", dot: "bg-emerald-400 animate-pulse" },
  completed: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10", dot: "bg-emerald-400" },
  failed: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", dot: "bg-red-400" },
  idle: { icon: AlertTriangle, color: "text-zinc-500", bg: "bg-zinc-800", dot: "bg-zinc-600" },
};

export function ActiveOrchestrationsCard() {
  const router = useRouter();

  const { data: sessions } = useQuery({
    queryKey: ["active-sessions"],
    queryFn: async () => {
      const json = await api.get<{ sessions: Session[] }>("/api/sessions?limit=10");
      return (json?.sessions ?? []).filter((s: Session) => s.repo_url);
    },
    refetchInterval: 15000,
  });

  const active = (sessions ?? []).filter(s => s.status === "running");
  const recent = (sessions ?? []).slice(0, 5);

  return (
    <div className="bg-card border border-white/[0.06] rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Active Orchestrations</span>
          {active.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[9px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              {active.length} running
            </span>
          )}
        </div>
      </div>

      {(!sessions || sessions.length === 0) ? (
        <div className="py-6 text-center">
          <GitBranch className="w-5 h-5 mx-auto mb-2 text-zinc-700" strokeWidth={1.5} />
          <p className="text-[12px] text-zinc-600">No orchestrations yet</p>
          <p className="text-[10px] text-zinc-700 mt-1">Start one from the Pipeline page</p>
        </div>
      ) : (
        <div className="space-y-1">
          {recent.map((session: Session) => {
            const cfg = STATUS_CONFIG[session.status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.idle;
            const Icon = cfg.icon;
            return (
              <motion.div
                key={session.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                onClick={() => router.push(`/history/${session.id}`)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-white/[0.03] cursor-pointer transition-colors group"
              >
                <div className={`shrink-0 ${cfg.color}`}>
                  <Icon className={`w-4 h-4 ${session.status === "running" ? "animate-spin" : ""}`} strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-zinc-200 truncate flex items-center gap-2">
                    {(session.goal || "")?.slice(0, 60) || "No description"}
                    {session.status === "running" && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] font-mono text-zinc-600">{session.id?.slice(0, 8)}</span>
                    {session.repo_url && (
                      <span className="text-[10px] font-mono text-zinc-700 truncate max-w-[180px]">
                        {session.repo_url.split("/").slice(-2).join("/")}
                      </span>
                    )}
                    <span className="text-[9px] font-mono text-zinc-700">{session.created_at?.slice(11, 16)}</span>
                  </div>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-zinc-700 group-hover:text-zinc-500 transition-colors shrink-0" strokeWidth={1.5} />
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
