"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";

import { cn } from "@/lib/utils";
import {
  History,
  CheckCircle2,
  XCircle,
  Loader2,
  Trash2,
  Container,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";

interface Session {
  id: string;
  status: string;
  prompt: string;
  currentStep: string | null;
  error: string | null;
  totalTokens: number;
  totalCost: number;
  createdAt: string;
  updatedAt: string;
}

interface SandboxEntry {
  session_id: string;
  container_id: string;
  name: string;
  role: string;
  created_at: number;
  last_activity: number;
}

export function SessionBrowser() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sandboxes, setSandboxes] = useState<SandboxEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"sessions" | "sandboxes">("sessions");
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [sessJson, sandJson] = await Promise.all([
        api.get<{ sessions?: Session[] }>(`/api/sessions`),
        api.get<{ sandboxes?: SandboxEntry[] }>(`/api/sandbox/list`).catch(() => null),
      ]);
      setSessions(sessJson?.sessions || []);
      if (sandJson) setSandboxes(sandJson.sandboxes || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  };

  const deleteSession = async (sid: string) => {
    if (!confirm("Delete this session and all its data?")) return;
    setDeleting(sid);
    try {
      await api.delete(`/api/sessions/${sid}`);
      setSessions((prev) => prev.filter((s) => s.id !== sid));
      toast.success("Session deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch { return iso; }
  };

  const formatCost = (cost: number) => {
    if (cost < 0.01) return "<$0.01";
    return `$${cost.toFixed(4)}`;
  };

  if (isLoading) {
    return (
      <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-6 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonBlock key={i} className="h-16 w-full rounded-[1rem]" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-6">
        <p className="text-sm text-red-400">Failed to load: {error}</p>
        <button onClick={fetchData} className="text-xs text-emerald-400 mt-2 hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 100, damping: 20 }}
      className="bg-surface border border-white/[0.05] rounded-[1.5rem]"
    >
      {/* Tabs */}
      <div className="flex items-center gap-0 border-b border-white/[0.05] px-5 pt-5 pb-0">
        <button
          onClick={() => setTab("sessions")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors",
            tab === "sessions" ? "border-emerald-500 text-emerald-400" : "border-transparent text-neutral-500 hover:text-neutral-300",
          )}
        >
          <History className="w-3.5 h-3.5" strokeWidth={1.5} />
          Sessions ({sessions.length})
        </button>
        <button
          onClick={() => setTab("sandboxes")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors",
            tab === "sandboxes" ? "border-emerald-500 text-emerald-400" : "border-transparent text-neutral-500 hover:text-neutral-300",
          )}
        >
          <Container className="w-3.5 h-3.5" strokeWidth={1.5} />
          Sandboxes ({sandboxes.length})
        </button>
      </div>

      {/* Sessions Tab */}
      {tab === "sessions" && (
        <div className="divide-y divide-white/[0.05]">
          {sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center px-6">
              <History className="w-10 h-10 text-neutral-600 mb-3" strokeWidth={1.2} />
              <p className="text-sm text-neutral-500">No sessions yet</p>
              <p className="text-xs text-neutral-600 mt-1">Start a workflow to see agent sessions here.</p>
            </div>
          ) : (
            sessions.slice(0, 50).map((session, i) => (
              <motion.div
                key={session.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="flex items-center justify-between px-5 py-4 group hover:bg-white/[0.01] transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className={cn(
                    "w-9 h-9 rounded-xl flex items-center justify-center shrink-0",
                    session.status === "completed" ? "bg-emerald-500/10" :
                    session.status === "failed" ? "bg-red-500/10" : "bg-amber-500/10",
                  )}>
                    {session.status === "completed" ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                    ) : session.status === "failed" ? (
                      <XCircle className="w-4 h-4 text-red-400" strokeWidth={1.5} />
                    ) : (
                      <Loader2 className="w-4 h-4 text-amber-400 animate-spin" strokeWidth={1.5} />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-neutral-200 truncate">
                      {session.prompt || session.id.slice(0, 16) + "..."}
                    </p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[10px] text-neutral-500">{formatTime(session.createdAt)}</span>
                      <span className={cn(
                        "text-[10px] font-mono px-1 py-0.5 rounded",
                        session.status === "completed" ? "text-emerald-400 bg-emerald-500/10" :
                        session.status === "failed" ? "text-red-400 bg-red-500/10" : "text-amber-400 bg-amber-500/10",
                      )}>
                        {session.status}
                      </span>
                      {session.totalCost > 0 && (
                        <span className="text-[10px] font-mono text-zinc-600">{formatCost(session.totalCost)}</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => deleteSession(session.id)}
                    disabled={deleting === session.id}
                    className="h-7 w-7 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100 flex items-center justify-center"
                    title="Delete session"
                  >
                    {deleting === session.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    )}
                  </button>
                </div>
              </motion.div>
            ))
          )}
        </div>
      )}

      {/* Sandboxes Tab */}
      {tab === "sandboxes" && (
        <div className="divide-y divide-white/[0.05]">
          {sandboxes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center px-6">
              <Container className="w-10 h-10 text-neutral-600 mb-3" strokeWidth={1.2} />
              <p className="text-sm text-neutral-500">No active sandboxes</p>
              <p className="text-xs text-neutral-600 mt-1">Sandboxes appear when orchestration runs are active.</p>
            </div>
          ) : (
            sandboxes.map((sb, i) => (
              <motion.div
                key={sb.name}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="flex items-center justify-between px-5 py-4 group hover:bg-white/[0.01] transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className={cn(
                    "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 bg-cyan-500/10",
                  )}>
                    <Container className="w-4 h-4 text-cyan-400" strokeWidth={1.5} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-neutral-200 truncate">{sb.name}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[10px] text-neutral-500 font-mono">{sb.container_id?.slice(0, 12)}</span>
                      <span className="text-[10px] text-neutral-500">{sb.role}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>
      )}
    </motion.div>
  );
}
