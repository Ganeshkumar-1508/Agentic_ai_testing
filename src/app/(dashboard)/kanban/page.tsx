"use client";

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { DndContext, useSensor, useSensors, PointerSensor, closestCorners } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Plus, Search, Columns3, AlertTriangle,
  BarChart3, LayoutGrid, X, Sparkles, Pencil, ThumbsUp, ThumbsDown, Eye, ChevronDown, GitBranch,
} from "lucide-react";
import { SortableTaskCard, type Task, PRIORITIES } from "@/components/kanban/TaskCard";
import { api } from "@/lib/api/api-client";

interface Board { id: string; name: string; description?: string; columns: string[]; wipLimits: Record<string, number>; }
interface BoardStats { total: number; done: number; wip: number; flaky: number; autoCreated: number; }

const DEFAULT_COLUMNS = ["triage", "backlog", "ready", "in_progress", "review", "done", "flaky_heat"];

function snakeToTitle(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function resolveLabels(columns: string[]): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const col of columns) labels[col] = snakeToTitle(col);
  return labels;
}

function BoardSelector({ boards, activeId, onSelect, onCreate }: {
  boards: Board[]; activeId: string | null;
  onSelect: (id: string) => void; onCreate: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-300 hover:border-zinc-700 transition-colors">
        <Columns3 className="w-3.5 h-3.5" strokeWidth={1.5} />
        <span className="truncate max-w-[120px]">{boards.find(b => b.id === activeId)?.name ?? "Select board"}</span>
        <ChevronDown className="w-3 h-3 text-zinc-600" strokeWidth={1.5} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-56 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl z-50 p-1.5 space-y-0.5">
          {boards.map(b => (
            <button key={b.id} onClick={() => { onSelect(b.id); setOpen(false); }}
              className={cn("w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs text-left transition-colors",
                b.id === activeId ? "bg-zinc-800 text-zinc-200" : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-300")}>
              <GitBranch className="w-3 h-3 shrink-0" strokeWidth={1.5} />
              <span className="truncate">{b.name}</span>
            </button>
          ))}
          <div className="border-t border-zinc-800 pt-1.5 mt-1.5">
            <input value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && name.trim()) { onCreate(name.trim()); setName(""); setOpen(false); } }}
              placeholder="New board name..." className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none" />
          </div>
        </div>
      )}
    </div>
  );
}

function EventHistory({ events }: { events: Array<{ id: string; event_type: string; task_id: string; payload: any }> }) {
  if (events.length === 0) return null;
  return (
    <div className="py-1.5 border-b border-zinc-800/50">
      <span className="text-zinc-600 block mb-1.5 text-xs">Event History</span>
      <div className="space-y-1">
        {events.map(e => (
          <div key={e.id} className="flex items-start gap-2 text-[10px]">
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-1 shrink-0" />
            <span className="text-zinc-500">{e.payload?.to_column ? `→ ${e.payload.to_column}` : e.event_type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function KanbanPage() {
  const queryClient = useQueryClient();
  const [triageMode, setTriageMode] = useState<"auto" | "manual">("auto");
  const [newTaskReview, setNewTaskReview] = useState(false);
  const [search, setSearch] = useState("");
  const [filterAssignee, setFilterAssignee] = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [filterTag, setFilterTag] = useState("");
  const [filterSprint, setFilterSprint] = useState("");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [addingTo, setAddingTo] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [boardName, setBoardName] = useState("");
  const [activeBoard, setActiveBoard] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return new URLSearchParams(window.location.search).get("board")
      || localStorage.getItem("testai:last-board")
      || null;
  });
  const [viewMode, setViewMode] = useState<"swimlane" | "table" | "roadmap">("swimlane");
  const [selectMode, setSelectMode] = useState(false);
  const [undoMsg, setUndoMsg] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const { data: boards } = useQuery({
    queryKey: ["kanban-boards"],
    queryFn: async () => {
      const json = await api.get<{ boards?: Board[] }>("/api/kanban/boards");
      return json?.boards ?? [];
    },
  });

  useEffect(() => {
    if (activeBoard) {
      try { localStorage.setItem("testai:last-board", activeBoard); } catch {}
      return;
    }
    if (boards && boards.length > 0) {
      setActiveBoard(boards[0].id);
    }
  }, [boards, activeBoard]);

  useEffect(() => {
    if (boards && activeBoard && !boards.find((b) => b.id === activeBoard)) {
      setActiveBoard(boards[0]?.id ?? null);
    }
  }, [boards, activeBoard]);

  const { data: tasks, isLoading } = useQuery({
    queryKey: ["kanban-tasks", activeBoard],
    queryFn: async () => {
      if (!activeBoard) return [];
      const json = await api.get<{ tasks?: Task[] }>(`/api/kanban/boards/${activeBoard}/tasks`);
      return json?.tasks ?? [];
    },
    enabled: !!activeBoard,
    refetchInterval: 10000,
  });

  const { data: stats } = useQuery({
    queryKey: ["kanban-stats", activeBoard],
    queryFn: async () => {
      if (!activeBoard) return { total: 0, done: 0, wip: 0, flaky: 0, autoCreated: 0 };
      return api.get<BoardStats>(`/api/kanban/boards/${activeBoard}/stats`);
    },
    enabled: !!activeBoard,
    refetchInterval: 10000,
  });

  const { data: events } = useQuery({
    queryKey: ["kanban-events", activeBoard],
    queryFn: async () => {
      if (!activeBoard) return [];
      const json = await api.get<{ events?: any[] }>(`/api/kanban/boards/${activeBoard}/events?limit=10`);
      return json?.events ?? [];
    },
    enabled: !!activeBoard,
    refetchInterval: 5000,
  });

  const createBoardMut = useMutation({
    mutationFn: async (name: string) => {
      const json = await api.post<{ id: string }>("/api/kanban/boards", { name });
      return json.id;
    },
    onSuccess: (id) => { queryClient.invalidateQueries({ queryKey: ["kanban-boards"] }); setActiveBoard(id); setBoardName(""); },
  });

  const createTaskMut = useMutation({
    mutationFn: async (body: { board_id: string; title: string; column_name: string; priority?: string; tags?: string; needs_review?: boolean }) => {
      await api.post(`/api/kanban/boards/${activeBoard}/tasks`, { ...body, board_id: activeBoard! });
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["kanban-tasks", activeBoard] }); setNewTitle(""); setAddingTo(""); toast.success("Task created"); },
  });

  const moveMut = useMutation({
    mutationFn: async ({ taskId, column }: { taskId: string; column: string }) => {
      const t = tasks?.find(t => t.id === taskId);
      await api.patch(`/api/kanban/tasks/${taskId}`, { column_name: column });
      return { taskId, fromCol: t?.column ?? "", toCol: column };
    },
    onMutate: async ({ taskId, column }) => {
      if (!activeBoard) return;
      await queryClient.cancelQueries({ queryKey: ["kanban-tasks", activeBoard] });
      const previous = queryClient.getQueryData<Task[]>(["kanban-tasks", activeBoard]);
      queryClient.setQueryData<Task[]>(["kanban-tasks", activeBoard], (old) =>
        (old ?? []).map((t) => (t.id === taskId ? { ...t, column } : t))
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous && activeBoard) {
        queryClient.setQueryData(["kanban-tasks", activeBoard], context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["kanban-tasks", activeBoard] });
      queryClient.invalidateQueries({ queryKey: ["kanban-stats", activeBoard] });
    },
    onSuccess: (data) => {
      setUndoMsg(`Moved to ${columnLabels[data.toCol] ?? data.toCol}`);
      setTimeout(() => setUndoMsg(null), 4000);
    },
  });

  const reviewMut = useMutation({
    mutationFn: async ({ taskId, action, reviewer }: { taskId: string; action: string; reviewer: string }) => {
      return api.post<{ mode?: string; subtasks_created?: number }>(`/api/kanban/tasks/${taskId}/review`, { action, reviewer });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kanban-tasks", activeBoard] });
      toast.success("Review recorded");
    },
    onError: () => toast.error("Review failed"),
  });

  const triageMut = useMutation({
    mutationFn: async ({ taskId, instructions }: { taskId: string; instructions?: string }) => {
      return api.post<{ mode: string; subtasks_created?: number }>(`/api/kanban/tasks/${taskId}/triage`, {
        mode: triageMode,
        instructions: instructions ?? "",
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["kanban-tasks", activeBoard] });
      if (data.mode === "auto") {
        toast.success(`Triaged — ${data.subtasks_created ?? 0} subtasks planned`);
      }
    },
    onError: () => toast.error("Triage failed"),
  });

  const [commentText, setCommentText] = useState("");
  const commentRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "c" && !e.ctrlKey && !e.metaKey && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        commentRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const commentMut = useMutation({
    mutationFn: async ({ taskId, body }: { taskId: string; body: string }) => {
      await api.post(`/api/kanban/tasks/${taskId}/comment`, { author: "user", body });
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["kanban-events", activeBoard] }); setCommentText(""); toast.success("Comment added"); },
    onError: () => toast.error("Comment failed"),
  });

  const deleteMut = useMutation({
    mutationFn: async (taskId: string) => { await api.delete(`/api/kanban/tasks/${taskId}`); },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["kanban-tasks", activeBoard] }); toast.success("Deleted"); },
  });

  const batchDeleteMut = useMutation({
    mutationFn: async () => {
      await Promise.all(Array.from(selectedIds).map((id) => api.delete(`/api/kanban/tasks/${id}`)));
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["kanban-tasks", activeBoard] }); setSelectedIds(new Set()); toast.success(`${selectedIds.size} deleted`); },
  });

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  };

  const sprints = useMemo(() => {
    if (!tasks || !Array.isArray(tasks)) return [];
    return [...new Set(tasks.map(t => t.sprint).filter(Boolean))].sort().reverse();
  }, [tasks]);

  const filteredTasks = useMemo(() => {
    if (!tasks || !Array.isArray(tasks)) return [];
    return tasks.filter(t => {
      if (search && !t.title.toLowerCase().includes(search.toLowerCase())) return false;
      if (filterAssignee && t.assignedTo !== filterAssignee) return false;
      if (filterPriority && t.priority !== filterPriority) return false;
      if (filterSprint && t.sprint !== filterSprint) return false;
      if (filterTag) { const tt = (t.tags ?? "").split(",").map(s => s.trim()); if (!tt.includes(filterTag)) return false; }
      return true;
    });
  }, [tasks, search, filterAssignee, filterPriority, filterTag, filterSprint]);

  const doneThisWeek = useMemo(() => {
    if (!tasks || !Array.isArray(tasks)) return 0;
    const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return tasks.filter(t => t.column === "done" && new Date(t.createdAt).getTime() > weekAgo).length;
  }, [tasks]);

  const assignees = useMemo(() => !tasks || !Array.isArray(tasks) ? [] : [...new Set(tasks.map(t => t.assignedTo).filter(Boolean))], [tasks]);
  const currentBoard = boards?.find(b => b.id === activeBoard);
  const activeColumns = currentBoard?.columns ?? DEFAULT_COLUMNS;
  const columnLabels = useMemo(() => resolveLabels(activeColumns), [activeColumns]);
  const wipLimit = currentBoard?.wipLimits?.in_progress ?? 3;
  const wipCount = Array.isArray(filteredTasks) ? filteredTasks.filter(t => t.column === "in_progress").length : 0;

  // Table view data
  const tableTasks = useMemo(() => {
    if (!filteredTasks || !Array.isArray(filteredTasks) || viewMode !== "table") return [];
    return [...filteredTasks].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }, [filteredTasks, viewMode]);

  if (!activeBoard && boards?.length === 0) {
    return (
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="max-w-7xl mx-auto px-6 py-16 flex flex-col items-center justify-center">
        <motion.div className="w-14 h-14 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-5"
          animate={{ y: [0, -4, 0] }} transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}>
          <Columns3 className="w-6 h-6 text-zinc-500" strokeWidth={1} />
        </motion.div>
        <h2 className="text-lg font-medium text-zinc-200 mb-1.5">No boards yet</h2>
        <p className="text-sm text-zinc-600 mb-6 max-w-sm text-center leading-relaxed">
          Create a board to start coordinating tasks across agents and profiles.
        </p>
        <div className="flex gap-2">
          <input value={boardName} onChange={(e) => setBoardName(e.target.value)}
            placeholder="Board name..."
            className="px-3 h-9 rounded-xl bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30"
            onKeyDown={(e) => { if (e.key === "Enter" && boardName.trim()) createBoardMut.mutate(boardName.trim()); }} />
          <motion.button onClick={() => { if (boardName.trim()) createBoardMut.mutate(boardName.trim()); }}
            whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            className="px-4 h-9 rounded-xl bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors flex items-center gap-1.5">
            <Plus className="w-3.5 h-3.5" strokeWidth={2} /> Create
          </motion.button>
        </div>
      </motion.div>
    );
  }

  const metricStats = [
    { label: "Throughput", value: stats?.done ?? 0, sub: "tasks completed this week", dot: "bg-emerald-400" },
    { label: "Avg Cycle Time", value: stats && stats.done > 0 ? `${(stats.total / stats.done || 0).toFixed(1)}m` : "â€”", sub: "per task", dot: "bg-amber-400" },
    { label: "WIP", value: wipCount, sub: `active, ${wipLimit} limit`, dot: "bg-red-400" },
    { label: "Auto-created", value: stats?.autoCreated ?? 0, sub: "flaky + coverage tasks", dot: "bg-blue-400" },
  ];

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">System / Kanban</div>
          <div className="flex items-center gap-3">
            <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100 truncate max-w-[320px]" title={currentBoard?.name}>
              {currentBoard?.name ?? "Board"}
            </h1>
            <span className="text-[11px] text-zinc-600 font-mono shrink-0">{filteredTasks.length} tasks</span>
            {currentBoard?.description && (
              <span className="text-[11px] text-zinc-600 truncate max-w-[240px] hidden md:inline" title={currentBoard.description}>
                {currentBoard.description}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <BoardSelector
            boards={boards ?? []}
            activeId={activeBoard}
            onSelect={setActiveBoard}
            onCreate={(name) => createBoardMut.mutate(name)}
          />
          {/* View toggle â€” wireframe: Swimlane / Gantt / Burndown */}
          <div className="flex gap-0.5 p-0.5 bg-zinc-900/60 border border-zinc-800/60 rounded-lg">
            {[
              { id: "swimlane" as const, icon: LayoutGrid, label: "Swimlane" },
              { id: "table" as const, icon: Columns3, label: "Gantt" },
              { id: "roadmap" as const, icon: BarChart3, label: "Burndown" },
            ].map(v => (
              <button key={v.id} onClick={() => setViewMode(v.id)}
                className={cn("flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] font-medium rounded-md transition-colors",
                  viewMode === v.id ? "bg-zinc-800 text-zinc-100 shadow-sm" : "text-zinc-600 hover:text-zinc-400")}>
                <v.icon className="w-3 h-3" strokeWidth={1.5} />
                {v.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 p-0.5 bg-zinc-900/60 border border-zinc-800/60 rounded-lg">
            <button onClick={() => setTriageMode("auto")}
              className={cn("flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium rounded-md transition-colors",
                triageMode === "auto" ? "bg-emerald-500/15 text-emerald-300 shadow-sm" : "text-zinc-600 hover:text-zinc-400")}>
              <Sparkles className="w-3 h-3" strokeWidth={1.5} /> Auto
            </button>
            <button onClick={() => setTriageMode("manual")}
              className={cn("flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium rounded-md transition-colors",
                triageMode === "manual" ? "bg-zinc-800 text-zinc-100 shadow-sm" : "text-zinc-600 hover:text-zinc-400")}>
              <Pencil className="w-3 h-3" strokeWidth={1.5} /> Manual
            </button>
          </div>
          <button onClick={() => { setSelectMode(!selectMode); if (!selectMode) setSelectedIds(new Set()); }}
            className={cn("px-3 h-8 rounded-lg text-xs font-medium transition-colors",
              selectMode ? "bg-emerald-500/15 text-emerald-400" : "bg-zinc-800 hover:bg-zinc-700 text-zinc-400")}>
            {selectMode ? "Done" : "Select"}
          </button>
          <button onClick={() => setAddingTo(activeColumns[0])}
            className="flex items-center gap-1.5 px-4 h-8 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium transition-colors">
            <Plus className="w-3.5 h-3.5" strokeWidth={1.5} /> New Task
          </button>
        </div>
      </div>

      {/* Quick filters */}
      <div className="flex items-center gap-2 text-xs flex-wrap">
        <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">Filters</span>
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-500 min-w-[160px]">
          <Search className="w-3 h-3 shrink-0" strokeWidth={1.5} />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks..." className="bg-transparent text-xs text-zinc-300 placeholder:text-zinc-700 outline-none flex-1" />
          <span className="text-[9px] text-zinc-700 font-mono">Ctrl+K</span>
        </div>
        {["all", "flaky", "coverage"].map(f => (
          <button key={f} onClick={() => setFilterTag(f === "all" ? "" : f)}
            className={cn("px-2.5 py-1 rounded-md border transition-colors",
              filterTag === f || (f === "all" && !filterTag) ? "bg-zinc-800 border-zinc-700 text-zinc-200" : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300")}>
            {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <select value={filterSprint} onChange={(e) => setFilterSprint(e.target.value)}
          className="px-2 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-xs text-zinc-500 outline-none">
          <option value="">All Sprints</option>
          {sprints.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filterAssignee} onChange={(e) => setFilterAssignee(e.target.value)}
          className="px-2 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-xs text-zinc-500 outline-none">
          <option value="">Assignee</option>
          {assignees.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}
          className="px-2 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-xs text-zinc-500 outline-none">
          <option value="">Priority</option>
          {["p0","p1","p2","p3"].map(p => <option key={p} value={p}>{PRIORITIES[p].label}</option>)}
        </select>
      </div>

      {/* Batch actions bar */}
      <AnimatePresence>
        {selectedIds.size > 0 && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
            className="flex items-center gap-3 px-4 py-2 rounded-lg bg-zinc-500/10 border border-zinc-500/30 text-xs text-zinc-400">
            <span className="font-mono font-semibold">{selectedIds.size}</span> selected
            <span className="w-px h-3 bg-zinc-500/30" />
            <button className="hover:text-zinc-300 transition-colors" onClick={() => setSelectedIds(new Set())}>Clear</button>
            <button className="hover:text-zinc-300 transition-colors" onClick={() => { selectedIds.forEach(id => moveMut.mutate({ taskId: id, column: "in_progress" })); }}>Assign</button>
            <button className="hover:text-zinc-300 transition-colors" onClick={() => { selectedIds.forEach(id => moveMut.mutate({ taskId: id, column: "done" })); }}>Move</button>
            <button className="hover:text-red-300 transition-colors text-red-400/80" onClick={() => { if (confirm(`Delete ${selectedIds.size} tasks?`)) batchDeleteMut.mutate(); }}>Delete</button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Board â€” Swimlane with Drag & Drop */}
      {viewMode === "swimlane" && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragEnd={(event) => {
            const { active, over } = event;
            if (!over || !active) return;
            const taskId = active.id as string;
            const targetCol = over.data?.current?.column || over.id as string;
            const currentTask = tasks?.find(t => t.id === taskId);
            if (currentTask && currentTask.column !== targetCol) {
              moveMut.mutate({ taskId, column: targetCol });
            }
          }}
        >
          <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: 420 }}>
            {activeColumns.map(col => {
              const colTasks = filteredTasks.filter(t => t.column === col);
              const atWipLimit = col === "in_progress" && colTasks.length >= wipLimit;
              const springEnter = { duration: 0.3, ease: [0.16, 1, 0.3, 1] as const };

              return (
                <motion.div key={col} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={springEnter}
                  className="flex-shrink-0 w-64 bg-zinc-900/30 border border-zinc-800/40 rounded-xl p-3"
                  data-column={col}>
                  <div className="flex items-center justify-between mb-3 px-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{columnLabels[col]}</span>
                      <span className={cn("text-[10px] font-mono", atWipLimit ? "text-amber-400" : "text-zinc-600")}>
                        {colTasks.length}{col === "in_progress" ? `/${wipLimit}` : ""}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {col === "done" && doneThisWeek > 0 && (
                        <span className="text-[9px] text-zinc-700">{doneThisWeek} done this week</span>
                      )}
                      <button onClick={() => { setAddingTo(col); setNewTitle(""); }}
                        className="text-zinc-700 hover:text-zinc-400 transition-colors">
                        <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </button>
                    </div>
                  </div>
                  {atWipLimit && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} transition={springEnter}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md mb-3 bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-400 overflow-hidden">
                      <AlertTriangle className="w-3 h-3 shrink-0" strokeWidth={1.5} />WIP limit reached
                    </motion.div>
                  )}
                  {col === "flaky_heat" && (
                    <div className="text-[9px] text-amber-400/40 mb-3 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400/40 animate-pulse" />auto-populated
                    </div>
                  )}
                  <SortableContext items={colTasks.map(t => t.id)} strategy={verticalListSortingStrategy}>
                    <div className="space-y-2 min-h-[60px]" data-column-drop={col}>
                      <AnimatePresence>
                        {colTasks.map(task => (
                          <SortableTaskCard key={task.id} task={task}
                            onSelect={(t) => setSelectedTask(selectedTask?.id === t.id ? null : t)}
                            isSelected={selectedIds.has(task.id)}
                            onToggleSelect={selectMode ? toggleSelect : undefined}
                            selectMode={selectMode}
                            compact={col === "done"}
                            onTriage={col === "triage" ? (id) => triageMut.mutate({ taskId: id }) : undefined}
                            triageMode={col === "triage" ? triageMode : undefined}
                            onReview={col === "review" ? (id, action) => reviewMut.mutate({ taskId: id, action, reviewer: "human" }) : undefined} />
                        ))}
                      </AnimatePresence>
                    </div>
                  </SortableContext>
                  {addingTo === col && (
                    <div className="space-y-1.5 mt-2">
                      <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
                        placeholder="Task title..."
                        className="w-full px-2.5 py-1.5 rounded-lg bg-zinc-800 border border-white/[0.06] text-xs outline-none focus:border-emerald-500/30"
                        onKeyDown={(e) => { if (e.key === "Enter" && newTitle.trim()) createTaskMut.mutate({ board_id: activeBoard!, title: newTitle.trim(), column_name: col, needs_review: newTaskReview }); }}
                        autoFocus />
                      <label className="flex items-center gap-1.5 text-[10px] text-zinc-600 cursor-pointer select-none">
                        <input type="checkbox" checked={newTaskReview} onChange={(e) => setNewTaskReview(e.target.checked)}
                          className="w-3 h-3 rounded border-zinc-700 bg-zinc-800 accent-emerald-400" />
                        <Eye className="w-2.5 h-2.5" strokeWidth={1.5} /> Needs review
                      </label>
                      <div className="flex gap-1">
                        <button onClick={() => { if (newTitle.trim()) createTaskMut.mutate({ board_id: activeBoard!, title: newTitle.trim(), column_name: col, needs_review: newTaskReview }); }}
                          className="px-2 py-1 rounded text-[9px] bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors">Add</button>
                        <button onClick={() => { setAddingTo(""); setNewTitle(""); }}
                          className="px-2 py-1 rounded text-[9px] text-zinc-600 hover:text-zinc-400 transition-colors">Cancel</button>
                      </div>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        </DndContext>
      )}

      {/* Table view */}
      {viewMode === "table" && (
        <div className="bg-zinc-900/30 border border-zinc-800/40 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800/40">
                  <th className="text-left px-4 py-2.5 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Title</th>
                  <th className="text-left px-4 py-2.5 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Status</th>
                  <th className="text-left px-4 py-2.5 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Priority</th>
                  <th className="text-left px-4 py-2.5 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Assignee</th>
                  <th className="text-left px-4 py-2.5 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Tags</th>
                  <th className="text-right px-4 py-2.5 text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {tableTasks.map(t => (
                  <tr key={t.id} className="border-b border-zinc-800/20 hover:bg-zinc-800/20 cursor-pointer" onClick={() => setSelectedTask(selectedTask?.id === t.id ? null : t)}>
                    <td className="px-4 py-2.5 text-zinc-300 font-medium max-w-[300px] truncate">{t.title}</td>
                    <td className="px-4 py-2.5"><span className="text-zinc-500">{columnLabels[t.column] ?? t.column}</span></td>
                    <td className="px-4 py-2.5">
                      <span className={cn("text-[10px] font-mono font-semibold", PRIORITIES[t.priority]?.badge ?? "")}>{PRIORITIES[t.priority]?.label ?? t.priority}</span>
                    </td>
                    <td className="px-4 py-2.5 text-zinc-600">{t.assignedTo || "â€”"}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1">{(t.tags ?? "").split(",").filter(Boolean).slice(0, 2).map(tg => (
                        <span key={tg} className="text-[8px] text-zinc-600 px-1 py-0.5 rounded bg-zinc-800">{tg.trim()}</span>
                      ))}</div>
                    </td>
                    <td className="px-4 py-2.5 text-zinc-700 font-mono text-right" suppressHydrationWarning>{new Date(t.createdAt).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Roadmap view */}
      {viewMode === "roadmap" && (
        <div className="bg-zinc-900/30 border border-zinc-800/40 rounded-xl p-6 text-center">
          <BarChart3 className="w-8 h-8 text-zinc-700 mx-auto mb-2" strokeWidth={1} />
          <p className="text-sm text-zinc-600">Roadmap timeline view â€” drag tasks to set dates</p>
          <p className="text-xs text-zinc-700 mt-1">Coming soon: Gantt chart with dependency arrows</p>
        </div>
      )}

      {/* Metrics bar â€” asymmetric grid per DESIGN_VARIANCE=8 */}
      <motion.div initial="hidden" animate="show" variants={{
        hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
      }} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr] gap-3">
        {metricStats.map((m, i) => (
          <motion.div key={m.label} variants={{
            hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
          }} layout className={cn("bg-zinc-900/30 border border-zinc-800/40 rounded-xl p-4", i === 0 ? "lg:col-span-1" : "")}>
            <div className="flex items-center gap-1.5 mb-2">
              <motion.span className={cn("w-2 h-2 rounded-full", m.dot)} animate={{ scale: [1, 1.3, 1] }} transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }} />
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">{m.label}</span>
            </div>
            <div className="text-lg font-semibold tracking-tight text-zinc-100">{m.value}</div>
            <div className="text-[10px] text-zinc-600">{m.sub}</div>
          </motion.div>
        ))}
      </motion.div>

      {/* Keyboard shortcuts + SSE status */}
      <div className="flex items-center gap-4 text-[10px] text-zinc-700 pt-2 border-t border-zinc-800/30">
        {[["N","New task"],["Space","Open detail"],["Esc","Close"],["C","Comment"],["B","Block"],["/","Search"],["â‡§+Click","Multi-select"]].map(([k,l]) => (
          <span key={k}><span className="font-mono text-zinc-600">{k}</span> {l}</span>
        ))}
        <span className="ml-auto text-zinc-800">{events?.length ?? 0} events â€¢ live updates</span>
      </div>

      {/* Task detail panel */}
      <AnimatePresence>
        {selectedTask && (
          <motion.div initial={{ opacity: 0, x: 300 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 300 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 bottom-0 w-96 bg-zinc-900 border-l border-zinc-800 z-50 overflow-y-auto shadow-2xl">
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <span className={cn("text-[9px] font-semibold px-1.5 py-0.5 rounded font-mono", PRIORITIES[selectedTask.priority]?.badge ?? "")}>
                  {PRIORITIES[selectedTask.priority]?.label ?? selectedTask.priority}
                </span>
                <button onClick={() => setSelectedTask(null)} className="text-zinc-600 hover:text-zinc-400 transition-colors">
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>
              <h2 className="text-sm font-semibold text-zinc-100">{selectedTask.title}</h2>
              {selectedTask.description && <p className="text-xs text-zinc-400 leading-relaxed">{selectedTask.description}</p>}
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                  <span className="text-zinc-600">Status</span>
                  <span className="text-zinc-300">{columnLabels[selectedTask.column] ?? selectedTask.column}</span>
                </div>
                {selectedTask.assignedTo && <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                  <span className="text-zinc-600">Assignee</span><span className="text-zinc-300">{selectedTask.assignedTo}</span>
                </div>}
                {selectedTask.parentTaskId && <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                  <span className="text-zinc-600">Parent</span><span className="text-zinc-300 font-mono text-[10px]">{selectedTask.parentTaskId.slice(0, 8)}</span>
                </div>}
                {selectedTask.childrenTotal != null && selectedTask.childrenTotal > 0 && (
                  <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                    <span className="text-zinc-600">Children</span>
                    <span className="text-emerald-400 font-mono text-[10px]">{selectedTask.childrenDone ?? 0}/{selectedTask.childrenTotal} done</span>
                  </div>
                )}
                {selectedTask.flakyTestName && <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                  <span className="text-zinc-600">Flaky Test</span><span className="text-zinc-300 font-mono text-[10px]">{selectedTask.flakyTestName}</span>
                </div>}
                {selectedTask.pipelineRunId && <div className="flex items-center justify-between py-1.5">
                  <span className="text-zinc-600">Pipeline</span>
                  <span className="text-blue-400 font-mono text-[10px]">{selectedTask.pipelineRunId.slice(0, 8)}</span>
                </div>}
                <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                  <span className="text-zinc-600">Review gate</span>
                  <span className={selectedTask.needsReview ? "text-zinc-400 font-mono text-[10px]" : "text-zinc-600 font-mono text-[10px]"}>
                    {selectedTask.needsReview ? "Required" : "Off"}
                  </span>
                </div>
                {selectedTask.reviewStatus && (
                  <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/50">
                    <span className="text-zinc-600">Review status</span>
                    <span className={cn("font-mono text-[10px]",
                      selectedTask.reviewStatus === "approved" ? "text-emerald-400" :
                      selectedTask.reviewStatus === "rejected" ? "text-rose-400" : "text-amber-400")}>
                      {selectedTask.reviewStatus}
                    </span>
                  </div>
                )}
                {selectedTask.resultSummary && (
                  <div className="py-1.5 border-b border-zinc-800/50">
                    <span className="text-zinc-600 block mb-1">Result</span>
                    <span className="text-zinc-300 text-[11px] leading-relaxed">{selectedTask.resultSummary}</span>
                  </div>
                )}
              </div>
              {/* Event history */}
              <EventHistory events={(events ?? []).filter((e: any) => e.task_id === selectedTask.id).slice(0, 5)} />

              {/* Comment input */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <input ref={commentRef} value={commentText} onChange={e => setCommentText(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter" && commentText.trim()) { commentMut.mutate({ taskId: selectedTask.id, body: commentText.trim() }); } }}
                    placeholder="Comment... (Enter to send, C to focus)"
                    className="flex-1 bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-zinc-600 transition-colors" />
                  <button onClick={() => { if (commentText.trim()) { commentMut.mutate({ taskId: selectedTask.id, body: commentText.trim() }); } }}
                    className="shrink-0 px-2.5 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors disabled:opacity-40"
                    disabled={!commentText.trim()}>Send</button>
                </div>
              </div>

              <div className="flex gap-2 pt-2">
                {selectedTask.reviewStatus === "rejected" ? (
                  <>
                    <button onClick={() => moveMut.mutate({ taskId: selectedTask.id, column: "in_progress" })}
                      className="flex-1 px-3 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors">Rework</button>
                    <button onClick={() => { reviewMut.mutate({ taskId: selectedTask.id, action: "approve", reviewer: "human" }); }}
                      className="flex-1 px-3 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-xs font-semibold hover:bg-blue-500/20 transition-colors">Override</button>
                  </>
                ) : selectedTask.column === "review" ? (
                  <>
                    <button onClick={() => { reviewMut.mutate({ taskId: selectedTask.id, action: "approve", reviewer: "human" }); }}
                      className="flex-1 px-3 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors">
                      <ThumbsUp className="w-3 h-3 inline mr-1" strokeWidth={1.5} /> Approve
                    </button>
                    <button onClick={() => { reviewMut.mutate({ taskId: selectedTask.id, action: "reject", reviewer: "human" }); }}
                      className="flex-1 px-3 py-2 rounded-lg bg-rose-500/10 text-rose-400 text-xs font-semibold hover:bg-rose-500/20 transition-colors">
                      <ThumbsDown className="w-3 h-3 inline mr-1" strokeWidth={1.5} /> Reject
                    </button>
                  </>
                ) : (
                  <>
                    <button onClick={() => moveMut.mutate({ taskId: selectedTask.id, column: "in_progress" })}
                      className="flex-1 px-3 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors">Start</button>
                    <button onClick={() => moveMut.mutate({ taskId: selectedTask.id, column: "done" })}
                      className="flex-1 px-3 py-2 rounded-lg bg-blue-500/10 text-blue-400 text-xs font-semibold hover:bg-blue-500/20 transition-colors">Complete</button>
                    {selectedTask.column === "blocked" ? (
                      <button onClick={() => { moveMut.mutate({ taskId: selectedTask.id, column: "ready" }); toast.success("Task unblocked"); }}
                        className="flex-1 px-3 py-2 rounded-lg bg-amber-500/10 text-amber-400 text-xs font-semibold hover:bg-amber-500/20 transition-colors">Unblock</button>
                    ) : (
                      <button onClick={() => { moveMut.mutate({ taskId: selectedTask.id, column: "blocked" }); toast.error("Task blocked"); }}
                        className="flex-1 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-xs font-semibold hover:bg-red-500/20 transition-colors">Block</button>
                    )}
                  </>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Undo toast */}
      <AnimatePresence>
        {undoMsg && (
          <motion.div initial={{ opacity: 0, y: 20, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 20, scale: 0.96 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="fixed bottom-6 right-6 flex items-center gap-3 px-4 py-2.5 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl text-xs z-50">
            <motion.span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" animate={{ scale: [1, 1.4, 1] }} transition={{ repeat: Infinity, duration: 1.5 }} />
            <span className="text-zinc-300">{undoMsg}</span>
            <span className="w-px h-3 bg-zinc-700" />
            <button className="text-emerald-400 hover:text-emerald-300 font-medium transition-colors active:scale-[0.95]" onClick={() => setUndoMsg(null)}>Dismiss</button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
