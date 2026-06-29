"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Columns3, CheckCircle2, Clock, AlertTriangle, Loader2, ExternalLink } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface Task {
  id: string; title: string; column: string; tags: string; resultSummary: string;
}

const COLUMNS = ["backlog", "ready", "in_progress", "review", "done", "blocked"];
const COL_LABELS: Record<string, string> = {
  backlog: "Backlog", ready: "Ready", in_progress: "Running",
  review: "Review", done: "Done", blocked: "Blocked",
};
const COL_COLORS: Record<string, string> = {
  backlog: "text-zinc-500", ready: "text-blue-400", in_progress: "text-emerald-400",
  review: "text-amber-400", done: "text-zinc-500", blocked: "text-red-400",
};

export default function KanbanBoardSection({ boardId, sessionId }: { boardId: string | null; sessionId: string | null }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!boardId) return;
    setLoading(true);
    setError(null);
    api.get<{ tasks?: Task[] }>(`/api/kanban/boards/${boardId}/tasks`)
      .then(d => { setTasks(d.tasks || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });

    const interval = setInterval(() => {
      api.get<{ tasks?: Task[] }>(`/api/kanban/boards/${boardId}/tasks`)
        .then(d => setTasks(d.tasks || []))
        .catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [boardId]);

  if (!boardId) return null;

  const colCounts = COLUMNS.map(col => ({
    col,
    label: COL_LABELS[col],
    color: COL_COLORS[col],
    count: tasks.filter(t => t.column === col).length,
  }));

  const activeTasks = tasks.filter(t => t.column === "in_progress");
  const doneCount = tasks.filter(t => t.column === "done").length;
  const blockedCount = tasks.filter(t => t.column === "blocked").length;
  const totalCount = tasks.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-card border border-white/[0.06] rounded-xl overflow-hidden"
    >
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <Columns3 className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          <span className="text-[13px] font-medium text-zinc-200">Kanban Board</span>
          {loading && <Loader2 className="w-3 h-3 text-zinc-500 animate-spin" strokeWidth={2} />}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 font-mono">
            <span className="text-emerald-400 font-semibold">{doneCount}</span>
            <span className="text-zinc-600">/</span>
            <span>{totalCount}</span>
            <span className="text-zinc-600 ml-1">done</span>
          </div>
          <a
            href={`/kanban?board=${boardId}`}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium text-zinc-400 hover:text-emerald-400 hover:bg-emerald-500/5 border border-white/[0.06] hover:border-emerald-500/20 transition-all"
          >
            <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
            Open Board
          </a>
        </div>
      </div>

      {error && (
        <div className="px-5 py-3 text-[12px] text-red-400 font-mono flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5" strokeWidth={1.5} />
          {error}
        </div>
      )}

      {!error && tasks.length === 0 && !loading && (
        <div className="px-5 py-8 text-center">
          <div className="text-[13px] text-zinc-600">No tasks yet. Orchestrator is decomposing...</div>
          <div className="flex items-center justify-center gap-1 mt-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/50 animate-pulse" />
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/50 animate-pulse delay-75" />
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/50 animate-pulse delay-150" />
          </div>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="divide-y divide-white/[0.04]">
          {/* Column summary */}
          <div className="grid grid-cols-6 gap-px bg-white/[0.04]">
            {colCounts.map(({ col, label, color, count }) => (
              <div key={col} className="bg-card px-3 py-2 text-center">
                <div className={`text-[18px] font-semibold font-mono ${color}`}>{count}</div>
                <div className="text-[9px] text-zinc-600 uppercase tracking-[0.08em] mt-0.5">{label}</div>
              </div>
            ))}
          </div>

          {/* Active tasks */}
          {activeTasks.length > 0 && (
            <div className="px-4 py-3 space-y-1.5">
              <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.06em] mb-2 flex items-center gap-2">
                <Loader2 className="w-3 h-3 text-emerald-400 animate-spin" strokeWidth={2} />
                Currently Running
              </div>
              {activeTasks.map(t => {
                const tags = t.tags ? t.tags.split(",").filter(Boolean) : [];
                const agentTag = tags.find((tag: string) => tag.startsWith("agent:"));
                return (
                  <motion.div
                    key={t.id}
                    layout
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg bg-emerald-500/[0.03] border border-emerald-500/10"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                    <span className="text-[12px] text-zinc-200 truncate flex-1">{t.title}</span>
                    {agentTag && (
                      <span className="text-[10px] font-mono text-emerald-400/70 px-1.5 py-0.5 rounded bg-emerald-500/5 border border-emerald-500/10 shrink-0">
                        {agentTag.replace("agent:", "")}
                      </span>
                    )}
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Blocked tasks */}
          {blockedCount > 0 && (
            <div className="px-4 py-3 space-y-1.5">
              <div className="text-[10px] font-mono text-red-400 uppercase tracking-[0.06em] mb-2 flex items-center gap-2">
                <AlertTriangle className="w-3 h-3" strokeWidth={2} />
                Blocked
              </div>
              {tasks.filter(t => t.column === "blocked").map(t => (
                <div key={t.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-red-500/[0.03] border border-red-500/10">
                  <AlertTriangle className="w-3 h-3 text-red-400 shrink-0" strokeWidth={1.5} />
                  <span className="text-[12px] text-zinc-300 truncate flex-1">{t.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}
