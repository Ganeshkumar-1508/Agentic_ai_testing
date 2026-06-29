"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { AlertTriangle, Shield, CheckCircle2, XCircle, Search, TrendingUp, Clock } from "lucide-react";

interface FlakyTest {
  testName: string;
  branch: string;
  totalRuns: number;
  passCount: number;
  failCount: number;
  flakyScore: number;
  isQuarantined: boolean;
  lastHealed: string | null;
  updatedAt: string;
}

export default function FlakyTestsPage() {
  const [tests, setTests] = useState<FlakyTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    api.get<{ flaky?: FlakyTest[] }>("/api/tests/flaky?limit=50")
      .then(d => setTests(d?.flaky ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = tests.filter(t => {
    if (filter === "quarantined" && !t.isQuarantined) return false;
    if (filter === "active" && t.isQuarantined) return false;
    if (search && !t.testName.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const quarantinedCount = tests.filter(t => t.isQuarantined).length;
  const highRiskCount = tests.filter(t => t.flakyScore >= 0.7).length;
  const avgScore = tests.length > 0 ? (tests.reduce((s, t) => s + t.flakyScore, 0) / tests.length) : 0;

  const handleQuarantine = async (testName: string, branch: string, quarantine: boolean) => {
    try {
      await api.post(`/api/tests/flaky/${encodeURIComponent(testName)}/quarantine`, { branch, quarantine });
      setTests(prev => prev.map(t => t.testName === testName && t.branch === branch ? { ...t, isQuarantined: quarantine } : t));
    } catch {}
  };

  return (
    <div className="space-y-6">
      <PageHeader description="Auto-detected flaky tests with quarantine and self-healing" />

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total Flaky", value: tests.length, icon: AlertTriangle, color: "text-amber-400" },
          { label: "Quarantined", value: quarantinedCount, icon: Shield, color: "text-red-400" },
          { label: "High Risk", value: highRiskCount, icon: TrendingUp, color: "text-red-400" },
          { label: "Avg Score", value: avgScore.toFixed(2), icon: Clock, color: "text-zinc-300" },
        ].map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
            className="rounded-[2rem] p-4 card-wireframe">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">{s.label}</span>
              <s.icon className={`w-3.5 h-3.5 ${s.color}`} strokeWidth={1.5} />
            </div>
            <div className={`text-2xl font-semibold font-mono ${s.color}`}>{s.value}</div>
          </motion.div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" strokeWidth={1.5} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search flaky tests..."
            className="w-full pl-9 pr-3 py-2 rounded-xl bg-card border border-white/[0.06] text-[13px] text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-emerald-500/30" />
        </div>
        <div className="flex gap-1">
          {["all", "active", "quarantined"].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={cn("px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all", filter === f ? "bg-emerald-500/15 text-emerald-400" : "text-zinc-500 hover:text-zinc-300")}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-14 rounded-xl shimmer-bg" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-sm text-zinc-600">
          <AlertTriangle className="w-8 h-8 mx-auto mb-3 text-zinc-700" strokeWidth={1} />
          {search ? "No flaky tests match your search" : "No flaky tests detected yet"}
        </div>
      ) : (
        <div className="space-y-1.5">
          {filtered.map((t, i) => {
            const scoreColor = t.flakyScore >= 0.7 ? "text-red-400" : t.flakyScore >= 0.3 ? "text-amber-400" : "text-emerald-400";
            const scoreBg = t.flakyScore >= 0.7 ? "bg-red-500/10" : t.flakyScore >= 0.3 ? "bg-amber-500/10" : "bg-emerald-500/10";
            return (
              <motion.div key={`${t.testName}-${t.branch}`} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
                className="flex items-center gap-4 px-4 py-3 rounded-xl bg-card border border-white/[0.06] hover:border-white/[0.1] transition-all">
                <span className={cn("w-2 h-2 rounded-full shrink-0", t.isQuarantined ? "bg-red-400" : t.flakyScore >= 0.7 ? "bg-red-400" : t.flakyScore >= 0.3 ? "bg-amber-400" : "bg-emerald-400")} />
                <div className="flex-1 min-w-0">
                  <span className="text-[13px] text-zinc-200 font-mono truncate block">{t.testName}</span>
                  <span className="text-[10px] text-zinc-600 font-mono">{t.branch}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <div className={cn("px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold", scoreBg, scoreColor)}>
                    {t.flakyScore.toFixed(2)}
                  </div>
                  <span className="text-[10px] font-mono text-zinc-600">{t.passCount}/{t.totalRuns} pass</span>
                  <span className="text-[10px] font-mono text-zinc-600">{t.failCount} fail</span>
                  <Badge variant="outline" className={cn("text-[10px] px-2 py-0 rounded font-medium", t.isQuarantined ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-zinc-800 text-zinc-500 border-zinc-700")}>
                    {t.isQuarantined ? "quarantined" : "active"}
                  </Badge>
                  <button onClick={() => handleQuarantine(t.testName, t.branch, !t.isQuarantined)}
                    className="text-[10px] px-2 py-1 rounded-lg border border-white/[0.06] text-zinc-500 hover:text-zinc-300 hover:border-white/[0.1] transition-colors">
                    {t.isQuarantined ? "Unquarantine" : "Quarantine"}
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
