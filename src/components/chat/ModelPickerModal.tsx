"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Check, Cpu, Loader2, AlertCircle, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface ProviderModel {
  provider?: string;
  model?: string;
  enabled?: boolean;
  label?: string;
}

interface ModelPickerModalProps {
  open: boolean;
  onClose: () => void;
  currentModel: string;
  onSelect: (model: string) => void;
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.03 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] as const } },
};

function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5">
      <div className="w-4 h-4 rounded-full bg-zinc-800/60 shimmer" />
      <div className="flex-1 space-y-1">
        <div className="h-3 w-32 bg-zinc-800/60 rounded shimmer" />
        <div className="h-2 w-20 bg-zinc-800/40 rounded shimmer" />
      </div>
    </div>
  );
}

export function ModelPickerModal({ open, onClose, currentModel, onSelect }: ModelPickerModalProps) {
  const [models, setModels] = useState<ProviderModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    api.get<any[]>("/api/settings/providers")
      .then((data) => {
        setModels(Array.isArray(data) ? data.filter((p: any) => p.enabled !== false) : []);
      })
      .catch(() => setError("Failed to load models"))
      .finally(() => setLoading(false));
  }, [open]);

  const filtered = useMemo(() => {
    if (!search) return models;
    const q = search.toLowerCase();
    return models.filter((m) =>
      (m.model || m.provider || "").toLowerCase().includes(q)
    );
  }, [models, search]);

  const handleSelect = useCallback((model: string) => {
    onSelect(model);
    onClose();
  }, [onSelect, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[300] bg-zinc-950/60 backdrop-blur-sm flex items-center justify-center"
          onClick={onClose}
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
                  <Cpu size={15} className="text-zinc-400" strokeWidth={1.5} />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-zinc-100">Select Model</h2>
                  <p className="text-[10px] text-zinc-600 mt-0.5">Choose a provider and model for this session</p>
                </div>
              </div>
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-zinc-800/50 text-zinc-600 hover:text-zinc-400 transition-colors active:scale-[0.95]">
                <X size={14} strokeWidth={1.5} />
              </button>
            </div>

            <div className="px-5 pb-3">
              <div className="relative">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" strokeWidth={1.5} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search models..."
                  className="w-full text-xs bg-zinc-800/60 border border-zinc-700/50 rounded-xl pl-9 pr-3 py-2 text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/40 transition-colors"
                  autoFocus
                />
              </div>
            </div>

            <div className="max-h-72 overflow-y-auto border-t border-zinc-800/30 px-2 py-1">
              {loading ? (
                <div className="space-y-1 py-2">
                  {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
                </div>
              ) : error ? (
                <div className="flex flex-col items-center py-8 text-zinc-600 gap-2">
                  <AlertCircle size={16} strokeWidth={1.5} className="text-red-400/60" />
                  <p className="text-xs">{error}</p>
                </div>
              ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-zinc-600 gap-2">
                  <Cpu size={16} strokeWidth={1.5} className="text-zinc-700" />
                  <p className="text-xs">{search ? "No models match your search" : "No models configured"}</p>
                  <p className="text-[10px] text-zinc-700">Add a provider in Settings to get started</p>
                </div>
              ) : (
                <motion.div variants={containerVariants} initial="hidden" animate="visible">
                  {filtered.map((m, i) => {
                    const label = m.model || m.provider || "unknown";
                    const isActive = label === currentModel;
                    return (
                      <motion.button
                        key={`${m.provider}-${m.model}-${i}`}
                        variants={itemVariants}
                        onClick={() => handleSelect(label)}
                        className={cn(
                          "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-200 active:scale-[0.98]",
                          isActive
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "text-zinc-300 hover:bg-zinc-800/40 hover:text-zinc-100"
                        )}
                      >
                        <div className={cn(
                          "w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors",
                          isActive ? "border-emerald-400" : "border-zinc-700"
                        )}>
                          {isActive && <div className="w-2 h-2 rounded-full bg-emerald-400" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{label}</div>
                          <div className="text-[10px] text-zinc-600 mt-0.5 truncate">{m.provider || "unknown provider"}</div>
                        </div>
                        {isActive && (
                          <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400/80 border border-emerald-500/20 font-mono">active</span>
                        )}
                      </motion.button>
                    );
                  })}
                </motion.div>
              )}
            </div>

            <div className="px-5 py-3 border-t border-zinc-800/30 flex items-center justify-between">
              <span className="text-[10px] text-zinc-700">{models.length} model{models.length !== 1 ? "s" : ""} available</span>
              <button
                onClick={onClose}
                className="text-[10px] px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-500 hover:text-zinc-300 border border-zinc-700/50 transition-colors active:scale-[0.97]"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
