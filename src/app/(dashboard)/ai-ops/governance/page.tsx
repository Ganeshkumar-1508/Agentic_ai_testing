"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatsCard } from "@/components/shared/StatsCard";
import { AlertTriangle, Database, Eye, FileText, ExternalLink } from "lucide-react";
import { api } from "@/lib/api/api-client";

type SpillItem = {
  key: string;
  session_id: string;
  tool_call_id: string;
  size_chars: number;
  size_kb: number;
  preview: string;
  created_at: string | null;
};

type SpillDetail = {
  key: string;
  content: string;
  size_chars: number;
};

function formatBytes(chars: number): string {
  if (chars > 1024 * 1024) return `${(chars / 1024 / 1024).toFixed(1)} MB`;
  if (chars > 1024) return `${(chars / 1024).toFixed(1)} KB`;
  return `${chars} chars`;
}

export default function GovernancePage() {
  const [config, setConfig] = useState<{ default_result_size_chars: number; max_preview_chars: number } | null>(null);
  const [spills, setSpills] = useState<SpillItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<SpillDetail | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [cfg, spillsData] = await Promise.all([
        api.get<{ default_result_size_chars: number; max_preview_chars: number }>("/api/ops/governance/config"),
        api.get<{ spills?: SpillItem[] }>("/api/ops/governance/spills?limit=50"),
      ]);
      setConfig(cfg);
      setSpills(spillsData?.spills ?? []);
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const viewSpill = async (key: string) => {
    try {
      const data = await api.get<SpillDetail>(`/api/ops/governance/spills/${encodeURIComponent(key)}`);
      setSelected(data);
    } catch {}
  };

  const totalSpilled = spills.reduce((s, x) => s + x.size_chars, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard icon={<Database size={16} />} label="Spilled Results" value={spills.length} sub="oversized tool outputs" delay={0.05} />
        <StatsCard icon={<AlertTriangle size={16} />} label="Total Spilled" value={formatBytes(totalSpilled)} sub="across all spills" delay={0.1} />
        <StatsCard icon={<Eye size={16} />} label="Preview Limit" value={config ? `${config.max_preview_chars.toLocaleString()} chars` : "..."} sub="inline preview size" delay={0.15} />
        <StatsCard icon={<FileText size={16} />} label="Result Cap" value={config ? formatBytes(config.default_result_size_chars) : "..."} sub="per-tool limit before spill" delay={0.2} />
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-48 rounded-2xl shimmer-bg border border-zinc-800/30" />
        ) : (
          <motion.div key="content" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6">
            <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
              <h2 className="text-sm font-medium text-zinc-100 mb-4">Tool Output Spills</h2>
              {spills.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-zinc-600">
                  <Database size={28} className="opacity-20 mb-2" strokeWidth={1} />
                  <p className="text-sm">No spills recorded</p>
                  <p className="text-xs mt-1">Tool outputs under {config?.default_result_size_chars.toLocaleString()} chars are kept inline</p>
                </div>
              ) : (
                <div className="space-y-1 max-h-[500px] overflow-y-auto pr-1 -mr-1">
                  {spills.map((s) => (
                    <div
                      key={s.key}
                      className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-white/[0.02] transition-colors cursor-pointer"
                      onClick={() => viewSpill(s.key)}
                    >
                      <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-zinc-300 truncate">{s.key}</span>
                          <span className="text-[10px] text-zinc-500 font-mono shrink-0">{formatBytes(s.size_chars)}</span>
                        </div>
                        <p className="text-[11px] text-zinc-500 truncate mt-0.5">{s.preview}</p>
                      </div>
                      <ExternalLink size={10} className="text-zinc-600 shrink-0" strokeWidth={1.5} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
              <h2 className="text-sm font-medium text-zinc-100 mb-4">Spill Details</h2>
              {!selected ? (
                <div className="flex flex-col items-center justify-center h-48 text-zinc-600">
                  <FileText size={28} className="opacity-20 mb-2" strokeWidth={1} />
                  <p className="text-xs">Click a spill to view its full content</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="p-2.5 rounded-lg bg-zinc-800/50">
                    <div className="text-[10px] text-zinc-500 font-mono break-all">{selected.key}</div>
                    <div className="text-[10px] text-zinc-600 mt-1">{formatBytes(selected.size_chars)} total</div>
                  </div>
                  <div className="p-3 rounded-xl bg-zinc-900/80 border border-zinc-800 max-h-[400px] overflow-y-auto">
                    <pre className="text-[11px] font-mono text-zinc-300 whitespace-pre-wrap break-words leading-relaxed">
                      {selected.content}
                    </pre>
                  </div>
                </div>
              )}

              <div className="mt-4 p-3 rounded-xl bg-zinc-900/50 border border-zinc-800">
                <p className="text-[10px] font-mono text-zinc-500">
                  Spill key format: <span className="text-zinc-400">tool_result:{`{session_id}`}:{`{tool_call_id}`}</span>
                </p>
                <p className="text-[10px] font-mono text-zinc-500 mt-1">
                  Full output stored in <span className="text-zinc-400">memory_entries</span> table with category <span className="text-zinc-400">tool_spill</span>.
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
