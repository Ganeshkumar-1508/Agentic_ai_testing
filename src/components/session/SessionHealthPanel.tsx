"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity, Database, Save, TrendingDown, Clock, FileText,
  CheckCircle2, Loader2, AlertCircle, Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface HealthData {
  compressions: {
    count: number;
    tokens_before: number;
    tokens_after: number;
    tokens_saved: number;
    ratio: number;
  };
  artifacts: {
    l0_count: number;
  };
  checkpoints: {
    count: number;
    latest: string | null;
    types: Record<string, number>;
  };
  token_usage: {
    records: number;
    total_tokens: number;
    total_cost: number;
  };
}

interface SessionHealthPanelProps {
  sessionId: string | null;
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-3.5 space-y-1.5 hover:border-zinc-700/50 transition-colors">
      <div className="flex items-center gap-2">
        <div className={cn(
          "w-6 h-6 rounded-lg flex items-center justify-center",
          accent === "emerald" ? "bg-emerald-500/10" :
          accent === "blue" ? "bg-blue-500/10" :
          accent === "amber" ? "bg-amber-500/10" :
          "bg-zinc-800/50"
        )}>
          <Icon size={12} className={cn(
            accent === "emerald" ? "text-emerald-400" :
            accent === "blue" ? "text-blue-400" :
            accent === "amber" ? "text-amber-400" :
            "text-zinc-500"
          )} strokeWidth={1.5} />
        </div>
        <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-lg font-semibold text-zinc-100 tracking-tight">{value}</div>
      {sub && <div className="text-[10px] text-zinc-600">{sub}</div>}
    </div>
  );
}

export function SessionHealthPanel({ sessionId }: SessionHealthPanelProps) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const d = await api.get<HealthData>(`/api/sessions/${sessionId}/health`);
      setData(d);
    } catch {
      setError("Failed to load session health");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { load(); setMounted(true); }, [load]);

  const formatTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
  };

  if (!mounted) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-6 h-6 rounded-lg bg-zinc-800/50 flex items-center justify-center">
          <Activity size={13} className="text-zinc-400" strokeWidth={1.5} />
        </div>
        <div>
          <h3 className="text-xs font-semibold text-zinc-200">Session Health</h3>
          <p className="text-[10px] text-zinc-600">Compression, memory, checkpoints</p>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-3.5 space-y-2">
              <div className="h-2.5 w-16 bg-zinc-800/60 rounded shimmer" />
              <div className="h-5 w-12 bg-zinc-800/60 rounded shimmer" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 py-4 text-zinc-600 text-xs">
          <AlertCircle size={12} strokeWidth={1.5} className="text-red-400/60" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="grid grid-cols-2 gap-2">
          <StatCard
            icon={Save}
            label="Compression"
            value={data.compressions.count > 0 ? `${data.compressions.ratio}%` : "0%"}
            sub={data.compressions.count > 0
              ? `${formatTokens(data.compressions.tokens_saved)} tokens saved`
              : "No compressions recorded"}
            accent="emerald"
          />
          <StatCard
            icon={FileText}
            label="L0 Artifacts"
            value={String(data.artifacts.l0_count)}
            sub="Raw tool call records"
            accent="blue"
          />
          <StatCard
            icon={Clock}
            label="Checkpoints"
            value={String(data.checkpoints.count)}
            sub={data.checkpoints.count > 0
              ? `${Object.keys(data.checkpoints.types).length} types`
              : "No checkpoints saved"}
            accent="amber"
          />
          <StatCard
            icon={TrendingDown}
            label="Token Usage"
            value={formatTokens(data.token_usage.total_tokens)}
            sub={`$${data.token_usage.total_cost.toFixed(4)} · ${data.token_usage.records} records`}
          />
        </div>
      ) : (
        <div className="flex items-center justify-center py-6 text-zinc-700 text-xs gap-2">
          <Activity size={14} strokeWidth={1.5} />
          No session selected
        </div>
      )}

      {data && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {data.checkpoints.count > 0 && Object.entries(data.checkpoints.types).map(([type, count]) => (
            <span key={type} className="text-[9px] px-2 py-0.5 rounded-full bg-zinc-800/40 text-zinc-600 font-mono border border-zinc-800/30">
              {type}: {count}
            </span>
          ))}
          {data.token_usage.records > 0 && (
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-zinc-800/40 text-zinc-600 font-mono border border-zinc-800/30">
              ${data.token_usage.total_cost.toFixed(4)} total
            </span>
          )}
        </div>
      )}
    </div>
  );
}
