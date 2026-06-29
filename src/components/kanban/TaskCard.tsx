"use client";

import { motion } from "framer-motion";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { Plus, CheckCircle2, Eye } from "lucide-react";

export interface Task {
  id: string; title: string; column: string; priority: string; tags: string;
  assignedTo: string; failureCount: number; description: string; createdAt: string;
  agentType?: string; lastHeartbeat?: string;
  pipelineRunId: string; coverageFile: string; flakyTestName: string;
  timeboxSeconds: number; estimateMinutes: number; resultSummary: string;
  needsReview: boolean; reviewStatus: string | null; reviewNotes: string; reviewedBy: string;
  parentTaskId?: string; childrenDone?: number; childrenTotal?: number;
  sprint?: string; deadline?: string; updatedAt?: string;
}

export const PRIORITIES: Record<string, { label: string; border: string; badge: string }> = {
  p0: { label: "P0", border: "border-l-red-500", badge: "bg-red-500/10 text-red-400" },
  p1: { label: "P1", border: "border-l-amber-500", badge: "bg-amber-500/10 text-amber-400" },
  p2: { label: "P2", border: "border-l-blue-500", badge: "bg-blue-500/10 text-blue-400" },
  p3: { label: "P3", border: "border-l-zinc-600", badge: "bg-zinc-800 text-zinc-500" },
};

const AVATAR_COLORS = ["bg-emerald-700","bg-zinc-700","bg-amber-700","bg-blue-700","bg-zinc-700","bg-red-700"];

function getInitials(name: string) { return name.split(/[\s_-]+/).map(s => s[0]).join("").slice(0, 2).toUpperCase(); }

function CoverageSparkline({ file }: { file: string }) {
  const gapsQ = useQuery<{ gaps?: Array<{ path: string; percent: number }>; count: number }>({
    queryKey: ["coverage-gaps", "all"],
    queryFn: () => api.get("/api/coverage/gaps?threshold=100&limit=1000"),
    staleTime: 120_000,
  });

  const match = gapsQ.data?.gaps?.find((g) => g.path === file || g.path.endsWith(file) || file.endsWith(g.path));
  const percent = match?.percent ?? null;

  if (gapsQ.isLoading) {
    return <div className="h-9 rounded shimmer-bg" />;
  }
  if (percent == null) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px]">
          <span className="text-zinc-600">Coverage</span>
          <span className="font-mono text-zinc-700">no data</span>
        </div>
        <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden" />
      </div>
    );
  }

  const tone = percent >= 80 ? "text-emerald-400" : percent >= 60 ? "text-amber-400" : "text-red-400";
  const fill = percent >= 80 ? "bg-emerald-500" : percent >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-zinc-600">Coverage</span>
        <span className={cn("font-mono", tone)}>{percent.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", fill)} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function TimeboxRing({ seconds }: { seconds: number }) {
  const pct = Math.min(100, Math.round((seconds / 3600) * 100));
  const color = pct > 80 ? "border-red-400" : pct > 50 ? "border-amber-400 border-t-amber-400 border-r-amber-400" : "border-emerald-400 border-t-emerald-400";
  return <div className={cn("w-4 h-4 rounded-full border-2 border-zinc-700", color)} />;
}

export function SortableTaskCard(props: { task: Task; onSelect: (t: Task) => void; isSelected: boolean; onToggleSelect?: (id: string) => void; selectMode?: boolean; compact?: boolean; onTriage?: (taskId: string) => void; triageMode?: "auto" | "manual"; onReview?: (taskId: string, action: "approve" | "reject") => void; }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: props.task.id });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.4 : 1, position: "relative" as const, zIndex: isDragging ? 10 : 1 };
  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <TaskCardBody {...props} />
    </div>
  );
}

function TaskCardBody({
  task, onSelect, isSelected, onToggleSelect, selectMode, compact,
  onTriage, triageMode, onReview,
}: {
  task: Task; onSelect: (t: Task) => void; isSelected: boolean;
  onToggleSelect?: (id: string) => void; selectMode?: boolean; compact?: boolean;
  onTriage?: (taskId: string) => void; triageMode?: "auto" | "manual";
  onReview?: (taskId: string, action: "approve" | "reject") => void;
}) {
  const priority = PRIORITIES[task.priority] ?? PRIORITIES.p3;
  const tags = task.tags ? task.tags.split(",").map(t => t.trim()).filter(Boolean) : [];
  const isFlaky = tags.includes("flaky") || !!task.flakyTestName;
  const isCoverage = tags.includes("coverage") || !!task.coverageFile;
  const hasPipeline = tags.includes("pipeline") || !!task.pipelineRunId;
  const isDone = task.column === "done";
  const avatarColor = AVATAR_COLORS[task.assignedTo ? task.assignedTo.length % AVATAR_COLORS.length : 0];
  const hasProgress = task.childrenTotal != null && task.childrenTotal > 0;
  const progressPct = hasProgress ? Math.round(((task.childrenDone ?? 0) / (task.childrenTotal ?? 1)) * 100) : 0;

  return (
    <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      onClick={(e) => { if (e.shiftKey && onToggleSelect) { onToggleSelect(task.id); return; } onSelect(task); }}
      whileHover={{ scale: 1.012, transition: { type: "spring", stiffness: 100, damping: 20 } }}
      className={cn(
        "rounded-xl p-3 cursor-pointer group active:scale-[0.98] transition-transform",
        isDone ? "bg-zinc-900/50 border-zinc-800/30" :
          isFlaky ? "bg-orange-500/[0.03] border-red-500/10" : "bg-zinc-900/80 border-zinc-800/50",
        "border hover:border-zinc-700/50",
        isSelected ? "ring-[2px] ring-zinc-500/40 border-zinc-500/30" : "",
        priority.border, "border-l-[3px]", compact ? "p-2" : "",
        selectMode && "hover:ring-1 hover:ring-emerald-500/20",
      )}
    >
      {selectMode && (
        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
          {isSelected && <CheckCircle2 className="w-3 h-3 text-emerald-400" strokeWidth={2} />}
        </div>
      )}
      <div className={cn("flex items-center gap-1.5 mb-1.5 flex-wrap")}>
        {priority.label !== "P3" && <span className={cn("text-[9px] font-semibold px-1.5 py-0.5 rounded font-mono", priority.badge)}>{priority.label}</span>}
        {isFlaky && <span className="text-[9px] px-1.5 py-0.5 rounded font-medium bg-red-500/10 text-red-400">flaky</span>}
        {isCoverage && <span className="text-[9px] px-1.5 py-0.5 rounded font-medium bg-emerald-500/10 text-emerald-400">coverage</span>}
        {hasPipeline && <span className="text-[9px] px-1.5 py-0.5 rounded font-medium bg-blue-500/10 text-blue-400">pipeline</span>}
        {task.needsReview && task.column !== "review" && (
          <span className="text-[9px] px-1.5 py-0.5 rounded font-medium bg-zinc-500/10 text-zinc-400">
            <Eye className="w-2.5 h-2.5 inline mr-0.5" strokeWidth={2} />review
          </span>
        )}
        {task.failureCount > 0 && <span className="text-[9px] font-mono text-red-400/70 ml-auto">{task.failureCount}x failed</span>}
        {hasProgress && <span className="text-[9px] font-mono text-emerald-400/80 ml-auto">{task.childrenDone}/{task.childrenTotal}</span>}
      </div>

      {hasProgress && (
        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden mb-2">
          <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${progressPct}%` }} />
        </div>
      )}

      <p className={cn("text-xs leading-relaxed", isDone ? "text-zinc-500 line-through" : "text-zinc-300", compact ? "line-clamp-1" : "line-clamp-2")}>
        {task.title}
      </p>

      {!compact && task.coverageFile && task.column === "in_progress" && <CoverageSparkline file={task.coverageFile} />}

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-1.5">
          {task.assignedTo ? (
            <div className={cn("w-5 h-5 rounded-full flex items-center justify-center text-[8px] font-medium text-zinc-200", avatarColor)}>
              {getInitials(task.assignedTo)}
            </div>
          ) : (
            <div className="w-5 h-5 rounded-full bg-zinc-800 flex items-center justify-center">
              <Plus className="w-2.5 h-2.5 text-zinc-600" strokeWidth={2} />
            </div>
          )}
          {task.column === "in_progress" && (
            <span className="flex items-center gap-1 text-[9px] text-emerald-400/70">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />running
            </span>
          )}
          {isDone && <CheckCircle2 className="w-3 h-3 text-emerald-400/60" strokeWidth={1.5} />}
        </div>
        <div className="flex items-center gap-2 text-[9px] text-zinc-700">
          {task.estimateMinutes > 0 && <span className="font-mono">{task.estimateMinutes}m</span>}
          {task.deadline && <span className="text-amber-400/60 font-mono">{new Date(task.deadline).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>}
          {task.timeboxSeconds > 0 && <TimeboxRing seconds={task.timeboxSeconds} />}
          {task.pipelineRunId && task.column === "in_progress" && (
            <span className="text-blue-400/60 underline decoration-blue-400/20">trace</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}
