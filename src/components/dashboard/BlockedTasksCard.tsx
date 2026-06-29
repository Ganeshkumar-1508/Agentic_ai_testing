"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ShieldAlert, RefreshCw, ExternalLink, AlertTriangle, RotateCcw } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface BlockedTask {
  id: string;
  title: string;
  board_id: string;
  column: string;
  column_name: string;
  failure_count: number;
  assigned_to: string;
  result_summary: string;
  created_at: string;
}

export function BlockedTasksCard() {
  const queryClient = useQueryClient();

  const { data: tasks } = useQuery({
    queryKey: ["blocked-tasks"],
    queryFn: async () => {
      const boards = (await api.get<{ boards: Array<{ id: string }> }>("/api/kanban/boards"))?.boards ?? [];
      const all: BlockedTask[] = [];
      for (const b of (Array.isArray(boards) ? boards.slice(0, 3) : [])) {
        const tJson = await api.get<{ tasks: any[] }>(`/api/kanban/boards/${b.id}/tasks`);
        for (const t of (tJson?.tasks ?? [])) {
          if (t.column === "blocked" || t.column === "flaky_heat") {
            all.push({ ...(t as BlockedTask), board_id: b.id });
          }
        }
      }
      return all.slice(0, 10);
    },
    refetchInterval: 30000,
  });

  const unblockMut = useMutation({
    mutationFn: async (taskId: string) => {
      await api.post(`/api/kanban/tasks/${taskId}/unblock`, {});
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["blocked-tasks"] });
      toast.success("Task unblocked");
    },
    onError: () => toast.error("Failed to unblock task"),
  });

  return (
    <div className="bg-card border border-white/[0.06] rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-400" strokeWidth={1.5} />
          <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Blocked Tasks</span>
          {tasks && tasks.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[9px] font-mono bg-red-500/10 text-red-400 border border-red-500/20">
              {tasks.length}
            </span>
          )}
        </div>
      </div>

      {(!tasks || tasks.length === 0) ? (
        <div className="py-6 text-center">
          <AlertTriangle className="w-5 h-5 mx-auto mb-2 text-zinc-700" strokeWidth={1.5} />
          <p className="text-[12px] text-zinc-600">No blocked tasks</p>
          <p className="text-[10px] text-zinc-700 mt-1">All tasks are flowing normally</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {tasks.map((task) => (
            <motion.div
              key={task.id}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-red-500/5 border border-red-500/10"
            >
              <div className="shrink-0 text-red-400">
                <ShieldAlert className="w-4 h-4" strokeWidth={1.5} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[12px] text-zinc-200 truncate">{task.title}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] font-mono text-zinc-600">{task.id?.slice(0, 8)}</span>
                  {task.failure_count > 0 && (
                    <span className="text-[10px] font-mono text-red-400">{task.failure_count} failures</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => unblockMut.mutate(task.id)}
                disabled={unblockMut.isPending}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 disabled:opacity-40 transition-colors shrink-0"
              >
                <RotateCcw className={`w-3 h-3 ${unblockMut.isPending ? "animate-spin" : ""}`} strokeWidth={1.5} />
                Retry
              </button>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
