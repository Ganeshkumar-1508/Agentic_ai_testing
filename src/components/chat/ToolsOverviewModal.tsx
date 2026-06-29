"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Wrench, Search, CheckCircle2, XCircle, Clock, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import type { RailTool } from "./RightRail";

interface ToolDefinition {
  name: string;
  tool_name?: string;
  description?: string;
  category?: string;
}

interface ToolsOverviewModalProps {
  open: boolean;
  onClose: () => void;
  activeTools: RailTool[];
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.03 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] as const } },
};

const statusConfig = {
  running: { icon: Loader2, className: "text-blue-400 animate-spin", label: "Running" },
  done: { icon: CheckCircle2, className: "text-emerald-400", label: "Done" },
  error: { icon: XCircle, className: "text-red-400", label: "Error" },
  pending: { icon: Clock, className: "text-zinc-600", label: "Pending" },
};

function SkeletonCard() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5">
      <div className="w-7 h-7 rounded-lg bg-zinc-800/60 shimmer" />
      <div className="flex-1 space-y-1">
        <div className="h-3 w-28 bg-zinc-800/60 rounded shimmer" />
        <div className="h-2 w-40 bg-zinc-800/40 rounded shimmer" />
      </div>
    </div>
  );
}

export function ToolsOverviewModal({ open, onClose, activeTools }: ToolsOverviewModalProps) {
  const [allTools, setAllTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<"active" | "all">("active");

  useEffect(() => {
    if (!open || tab !== "all") return;
    setLoading(true);
    setError(null);
    api.get<{ tools?: ToolDefinition[] }>("/api/ops/tools")
      .then((d) => setAllTools(d?.tools || []))
      .catch(() => setError("Failed to load tools"))
      .finally(() => setLoading(false));
  }, [open, tab]);

  const filteredAll = useMemo(() => {
    if (!search) return allTools;
    const q = search.toLowerCase();
    return allTools.filter((t) =>
      (t.name || t.tool_name || "").toLowerCase().includes(q)
    );
  }, [allTools, search]);

  const handleClose = useCallback(() => {
    setSearch("");
    setTab("active");
    onClose();
  }, [onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[300] bg-zinc-950/60 backdrop-blur-sm flex items-center justify-center"
          onClick={handleClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="bg-zinc-900 border border-zinc-800/60 rounded-[1.5rem] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] w-full max-w-md mx-4 overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
                  <Wrench size={15} className="text-zinc-400" strokeWidth={1.5} />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-zinc-100">Tools</h2>
                  <p className="text-[10px] text-zinc-600 mt-0.5">Tools available to the current agent</p>
                </div>
              </div>
              <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-zinc-800/50 text-zinc-600 hover:text-zinc-400 transition-colors active:scale-[0.95]">
                <X size={14} strokeWidth={1.5} />
              </button>
            </div>

            <div className="px-5 pb-3">
              <div className="flex gap-1 bg-zinc-800/40 border border-zinc-700/30 rounded-xl p-0.5">
                <button
                  onClick={() => setTab("active")}
                  className={cn(
                    "flex-1 text-[10px] px-3 py-1.5 rounded-[10px] font-medium transition-all",
                    tab === "active" ? "bg-zinc-700/60 text-zinc-200" : "text-zinc-600 hover:text-zinc-400"
                  )}
                >
                  Active ({activeTools.length})
                </button>
                <button
                  onClick={() => setTab("all")}
                  className={cn(
                    "flex-1 text-[10px] px-3 py-1.5 rounded-[10px] font-medium transition-all",
                    tab === "all" ? "bg-zinc-700/60 text-zinc-200" : "text-zinc-600 hover:text-zinc-400"
                  )}
                >
                  All Tools
                </button>
              </div>
            </div>

            <div className="max-h-72 overflow-y-auto border-t border-zinc-800/30 px-2 py-1">
              {tab === "active" ? (
                activeTools.length === 0 ? (
                  <div className="flex flex-col items-center py-8 text-zinc-600 gap-2">
                    <Wrench size={16} strokeWidth={1.5} className="text-zinc-700" />
                    <p className="text-xs">No tools active this session</p>
                    <p className="text-[10px] text-zinc-700">Tools appear here as the agent uses them</p>
                  </div>
                ) : (
                  <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-0.5 py-1">
                    {activeTools.map((tool, i) => {
                      const cfg = statusConfig[tool.status] || statusConfig.pending;
                      const Icon = cfg.icon;
                      return (
                        <motion.div
                          key={`${tool.name}-${i}`}
                          variants={itemVariants}
                          className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-zinc-800/20 transition-colors"
                        >
                          <Icon size={12} className={cn("shrink-0", cfg.className)} strokeWidth={2} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-zinc-300 truncate">{tool.name}</div>
                            <div className="text-[10px] text-zinc-600">{cfg.label}{tool.durationMs ? ` · ${tool.durationMs}ms` : ""}</div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </motion.div>
                )
              ) : (
                <>
                  <div className="px-1 pt-2 pb-1">
                    <div className="relative">
                      <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" strokeWidth={1.5} />
                      <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search tools..."
                        className="w-full text-[10px] bg-zinc-800/60 border border-zinc-700/50 rounded-lg pl-8 pr-2.5 py-1.5 text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/40 transition-colors"
                      />
                    </div>
                  </div>
                  {loading ? (
                    <div className="space-y-1 py-2">
                      {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
                    </div>
                  ) : error ? (
                    <div className="flex flex-col items-center py-8 text-zinc-600 gap-2">
                      <AlertCircle size={16} strokeWidth={1.5} className="text-red-400/60" />
                      <p className="text-xs">{error}</p>
                    </div>
                  ) : filteredAll.length === 0 ? (
                    <div className="flex flex-col items-center py-8 text-zinc-600 gap-2">
                      <Wrench size={16} strokeWidth={1.5} className="text-zinc-700" />
                      <p className="text-xs">{search ? "No tools match your search" : "No tools available"}</p>
                    </div>
                  ) : (
                    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-0.5 py-1">
                      {filteredAll.map((t, i) => {
                        const name = t.name || t.tool_name || "tool";
                        const isRunning = activeTools.some((at) => at.name === name && at.status === "running");
                        return (
                          <motion.div
                            key={`${name}-${i}`}
                            variants={itemVariants}
                            className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-zinc-800/20 transition-colors"
                          >
                            <div className={cn(
                              "w-6 h-6 rounded-lg flex items-center justify-center text-[9px] font-bold",
                              isRunning ? "bg-blue-500/10 text-blue-400" : "bg-zinc-800/50 text-zinc-600"
                            )}>
                              {name.charAt(0).toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs text-zinc-300 truncate">{name}</div>
                              <div className="text-[10px] text-zinc-600 truncate">{t.description || "No description"}</div>
                            </div>
                            {isRunning && (
                              <Loader2 size={10} className="text-blue-400 animate-spin shrink-0" strokeWidth={2} />
                            )}
                          </motion.div>
                        );
                      })}
                    </motion.div>
                  )}
                </>
              )}
            </div>

            <div className="px-5 py-3 border-t border-zinc-800/30 flex items-center justify-between">
              {tab === "active" ? (
                <span className="text-[10px] text-zinc-700">{activeTools.filter((t) => t.status === "running").length} running · {activeTools.filter((t) => t.status === "done").length} completed</span>
              ) : (
                <span className="text-[10px] text-zinc-700">{allTools.length} tools registered</span>
              )}
              <button
                onClick={handleClose}
                className="text-[10px] px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-500 hover:text-zinc-300 border border-zinc-700/50 transition-colors active:scale-[0.97]"
              >
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
