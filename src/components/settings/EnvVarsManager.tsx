"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Plus, Trash2, Eye, EyeOff, Shield, Variable, Save } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface EnvVar {
  id: string;
  key: string;
  value: string;
  isSecret: boolean;
  description?: string;
  createdAt?: string;
  updatedAt?: string;
}

export function EnvVarsManager() {
  const queryClient = useQueryClient();
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newSecret, setNewSecret] = useState(false);
  const [newDesc, setNewDesc] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ["env-vars"],
    queryFn: async () => {
      const d = await api.get<{ variables: EnvVar[] }>("/api/settings/env-vars");
      return d?.variables ?? [];
    },
  });

  const upsertMut = useMutation({
    mutationFn: (body: { key: string; value: string; is_secret: boolean; description?: string }) =>
      api.post("/api/settings/env-vars", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["env-vars"] });
      setNewKey(""); setNewValue(""); setNewSecret(false); setNewDesc(""); setShowForm(false);
      toast.success("Environment variable saved");
    },
    onError: () => toast.error("Failed to save"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/api/settings/env-vars/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["env-vars"] });
      toast.success("Variable deleted");
    },
    onError: () => toast.error("Failed to delete"),
  });

  const variables = data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Environment Variables</div>
          <p className="text-[11px] text-zinc-600 mt-0.5">
            These are injected into sandbox containers at spawn time
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 h-8 rounded-xl bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors"
        >
          <Plus className="w-3 h-3" strokeWidth={2} />
          Add Variable
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Key</label>
                  <input
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))}
                    placeholder="DATABASE_URL"
                    className="w-full h-8 px-3 rounded-lg bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30 font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Value</label>
                  <input
                    value={newValue}
                    onChange={(e) => setNewValue(e.target.value)}
                    placeholder="postgres://..."
                    className="w-full h-8 px-3 rounded-lg bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30 font-mono"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Description</label>
                <input
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Database connection string for test sandbox"
                  className="w-full h-8 px-3 rounded-lg bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30"
                />
              </div>
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newSecret}
                    onChange={(e) => setNewSecret(e.target.checked)}
                    className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 accent-emerald-500"
                  />
                  <span className="text-[11px] text-zinc-500">Secret (masked in UI)</span>
                </label>
                <button
                  onClick={() => {
                    if (!newKey.trim()) { toast.error("Key is required"); return; }
                    if (!newValue.trim()) { toast.error("Value is required"); return; }
                    upsertMut.mutate({ key: newKey.trim(), value: newValue.trim(), is_secret: newSecret, description: newDesc.trim() || undefined });
                  }}
                  className="flex items-center gap-1.5 px-3 h-7 rounded-lg bg-emerald-500/15 text-emerald-400 text-[10px] font-semibold hover:bg-emerald-500/25 transition-colors"
                >
                  <Save className="w-3 h-3" strokeWidth={2} />
                  Save
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-1">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded-xl shimmer-bg" />
            ))}
          </div>
        ) : variables.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-zinc-600">
            <Variable className="w-8 h-8 mb-2" strokeWidth={1} />
            <span className="text-xs">No environment variables configured</span>
          </div>
        ) : (
          variables.map((v) => (
            <div
              key={v.id}
              className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-white/[0.01] border border-white/[0.04] hover:bg-white/[0.02] transition-colors group"
            >
              <div className="w-7 h-7 rounded-lg bg-emerald-500/8 flex items-center justify-center shrink-0">
                {v.isSecret
                  ? <Shield className="w-3.5 h-3.5 text-amber-400/70" strokeWidth={1.5} />
                  : <Variable className="w-3.5 h-3.5 text-emerald-400/70" strokeWidth={1.5} />
                }
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-semibold text-zinc-200">{v.key}</span>
                  {v.isSecret && <span className="text-[8px] text-amber-400/60 uppercase tracking-wider">encrypted</span>}
                </div>
                {v.description && (
                  <div className="text-[10px] text-zinc-600 truncate">{v.description}</div>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono text-zinc-600 max-w-[120px] truncate">
                  {v.isSecret && !revealed.has(v.id)
                    ? "********"
                    : v.value
                  }
                </span>
                {v.isSecret && (
                  <button
                    onClick={() => setRevealed((p) => { const n = new Set(p); if (n.has(v.id)) n.delete(v.id); else n.add(v.id); return n; })}
                    className="p-1 rounded text-zinc-600 hover:text-zinc-400 transition-colors"
                  >
                    {revealed.has(v.id)
                      ? <EyeOff className="w-3 h-3" strokeWidth={1.5} />
                      : <Eye className="w-3 h-3" strokeWidth={1.5} />
                    }
                  </button>
                )}
                <button
                  onClick={() => { if (confirm("Delete this variable?")) deleteMut.mutate(v.id); }}
                  className="p-1 rounded text-zinc-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

