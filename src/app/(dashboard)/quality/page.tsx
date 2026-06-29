"use client";

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";
import {
  Gauge, Shield, Bug, Plus, Trash2, ToggleLeft, ToggleRight, BarChart3, ClipboardList,
} from "lucide-react";

type QualityTab = "score" | "trends" | "gates" | "triage" | "defects";

const TABS: { id: QualityTab; label: string; icon: any }[] = [
  { id: "score", label: "Score", icon: Gauge },
  { id: "trends", label: "Trends", icon: BarChart3 },
  { id: "gates", label: "Gates", icon: Shield },
  { id: "triage", label: "Triage", icon: ClipboardList },
  { id: "defects", label: "Defects", icon: Bug },
];

function QualityPageInner() {
  const [activeTab, setActiveTab] = useState<QualityTab>("score");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">/quality</div>
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Quality</h1>
          <p className="text-[13px] text-zinc-500 mt-0.5">Release readiness, quality gates, and defect tracking</p>
        </div>
        <div className="flex bg-card border border-white/[0.06] rounded-full p-0.5 gap-0.5">
          {TABS.map((t) => {
            const TabIcon = t.icon;
            return (
              <button key={t.id} onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all ${
                  activeTab === t.id ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-500 hover:text-zinc-300"
                }`}>
                <TabIcon className="w-3 h-3" strokeWidth={1.5} />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === "score" && <ScoreTab />}
      {activeTab === "trends" && <TrendsTab />}
      {activeTab === "gates" && <GatesTab />}
      {activeTab === "triage" && <TriageTab />}
      {activeTab === "defects" && <DefectsTab />}
    </div>
  );
}

function ScoreTab() {
  const { data: score, isLoading } = useQuery({
    queryKey: ["quality-score"],
    queryFn: () => api.get<any>("/api/quality/score?days=14"),
    refetchInterval: 60_000,
  });
  const { data: trend } = useQuery({
    queryKey: ["quality-trend"],
    queryFn: () => api.get<any>("/api/quality/trend?days=90"),
    refetchInterval: 120_000,
  });

  if (isLoading) return <div className="py-12 text-center text-sm text-zinc-600">Loading quality score...</div>;
  if (!score || score.score === null) return <div className="py-12 text-center text-sm text-zinc-600">No quality data yet. Run some pipelines first.</div>;

  const verdictColor = score.verdict === "go" ? "text-emerald-400" : score.verdict === "caution" ? "text-amber-400" : "text-red-400";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-6">
        <div className="bg-card border border-white/[0.06] rounded-2xl p-6 flex flex-col items-center justify-center text-center">
          <div className="text-4xl font-semibold font-mono tabular-nums tracking-tight text-zinc-100">{score.score}</div>
          <div className={cn("text-[11px] font-semibold uppercase tracking-wider mt-1", verdictColor)}>{score.verdict}</div>
          <div className="text-[10px] text-zinc-600 mt-3">{score.period_days}d window</div>
          {score.components && (
            <div className="w-full mt-6 space-y-2">
              {Object.entries(score.components).map(([key, comp]: [string, any]) => (
                <div key={key} className="flex items-center gap-2 text-[11px]">
                  <span className="w-24 text-zinc-500 truncate text-right">{key.replace(/_/g, " ")}</span>
                  <div className="flex-1 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-emerald-400/60" style={{ width: `${comp.weighted || 0}%` }} />
                  </div>
                  <span className="w-8 text-right font-mono text-zinc-400">{Math.round(comp.weighted || 0)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="bg-card border border-white/[0.06] rounded-2xl p-6">
          <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-4">Trend (90d)</div>
          {trend?.trend && trend.trend.length > 0 ? (
            <div className="space-y-1.5">
              {trend.trend.slice(-12).map((t: any, i: number) => (
                <div key={i} className="flex items-center gap-3 text-[11px]">
                  <span className="w-16 text-zinc-600 font-mono">{new Date(t.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
                  <div className="flex-1 h-2 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className={cn("h-full rounded-full", t.score >= 80 ? "bg-emerald-400" : t.score >= 60 ? "bg-amber-400" : "bg-red-400")} style={{ width: `${t.score}%` }} />
                  </div>
                  <span className="w-8 text-right font-mono text-zinc-400">{Math.round(t.score)}</span>
                  <span className={cn("w-12 text-right text-[9px] font-medium uppercase", t.verdict === "go" ? "text-emerald-400" : t.verdict === "caution" ? "text-amber-400" : "text-red-400")}>{t.verdict}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-zinc-600 text-center py-8">No trend data</div>
          )}
        </div>
      </div>
    </div>
  );
}

function GatesTab() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["quality-gates"],
    queryFn: () => api.get<any>("/api/settings/gates"),
    refetchInterval: 30_000,
  });

  const [newGate, setNewGate] = useState({ name: "", metric: "pass_rate", threshold: 80, enabled: true, description: "" });
  const [adding, setAdding] = useState(false);

  const gates = data?.gates ?? [];

  const addGate = async () => {
    if (!newGate.name.trim()) return;
    await api.post("/api/settings/gates", newGate);
    toast.success("Gate created");
    setNewGate({ name: "", metric: "pass_rate", threshold: 80, enabled: true, description: "" });
    setAdding(false);
    refetch();
  };

  const toggleGate = async (g: any) => {
    await api.patch(`/api/settings/gates/${g.id}`, { enabled: !g.enabled });
    refetch();
  };

  const deleteGate = async (id: string) => {
    await api.delete(`/api/settings/gates/${id}`);
    toast.success("Gate deleted");
    refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-zinc-600">Define quality thresholds that block releases when breached</p>
        <button onClick={() => setAdding(!adding)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors text-[12px] font-medium">
          <Plus className="w-3 h-3" strokeWidth={1.5} /> Add Gate
        </button>
      </div>

      {adding && (
        <div className="bg-card border border-white/[0.06] rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-5 gap-3">
            <div className="col-span-2">
              <label className="text-[9px] text-zinc-600 uppercase tracking-wider">Name</label>
              <input value={newGate.name} onChange={(e) => setNewGate({ ...newGate, name: e.target.value })}
                placeholder="e.g. Pass rate threshold"
                className="w-full bg-card border border-white/[0.06] rounded-lg px-3 py-1.5 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30 mt-1" />
            </div>
            <div>
              <label className="text-[9px] text-zinc-600 uppercase tracking-wider">Metric</label>
              <select value={newGate.metric} onChange={(e) => setNewGate({ ...newGate, metric: e.target.value })}
                className="w-full bg-card border border-white/[0.06] rounded-lg px-3 py-1.5 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30 mt-1">
                <option value="pass_rate">Pass Rate</option>
                <option value="coverage">Coverage</option>
                <option value="flaky_rate">Flaky Rate</option>
                <option value="quality_score">Quality Score</option>
              </select>
            </div>
            <div>
              <label className="text-[9px] text-zinc-600 uppercase tracking-wider">Threshold</label>
              <input type="number" value={newGate.threshold} onChange={(e) => setNewGate({ ...newGate, threshold: Number(e.target.value) })}
                className="w-full bg-card border border-white/[0.06] rounded-lg px-3 py-1.5 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30 mt-1" />
            </div>
            <div className="flex items-end">
              <button onClick={addGate} disabled={!newGate.name.trim()}
                className="w-full px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors text-[12px] font-medium disabled:opacity-40">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 rounded-xl shimmer-bg" />)}</div>
      ) : gates.length === 0 ? (
        <div className="text-center py-12 text-sm text-zinc-600">No quality gates configured</div>
      ) : (
        <div className="bg-card border border-white/[0.06] rounded-xl overflow-hidden">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-white/[0.06] text-zinc-600">
                <th className="text-left px-4 py-2.5 font-medium">Gate</th>
                <th className="text-left px-4 py-2.5 font-medium">Metric</th>
                <th className="text-left px-4 py-2.5 font-medium">Threshold</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-right px-4 py-2.5 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {gates.map((g: any) => (
                <tr key={g.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-3 text-zinc-300">
                    <div>{g.name}</div>
                    {g.description && <div className="text-[10px] text-zinc-600">{g.description}</div>}
                  </td>
                  <td className="px-4 py-3 font-mono text-zinc-500">{g.metric}</td>
                  <td className="px-4 py-3 font-mono text-zinc-400">{g.threshold}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleGate(g)}
                      className={`flex items-center gap-1.5 text-[10px] font-medium px-2 py-1 rounded-lg transition-colors ${
                        g.enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800/50 text-zinc-600"
                      }`}>
                      {g.enabled ? <ToggleRight className="w-3 h-3" strokeWidth={1.5} /> : <ToggleLeft className="w-3 h-3" strokeWidth={1.5} />}
                      {g.enabled ? "Active" : "Disabled"}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => deleteGate(g.id)} className="p-1.5 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                      <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TriageTab() {
  const [sevFilter, setSevFilter] = useState("all");
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["triage-queue", sevFilter],
    queryFn: () => api.get<any>(`/api/triage/queue?days=7${sevFilter !== "all" ? `&severity=${sevFilter}` : ""}`),
    refetchInterval: 30_000,
  });

  const queue = data?.queue ?? [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Critical", value: data?.critical ?? 0, color: "text-red-400", bg: "border-red-500/15" },
          { label: "High", value: data?.high ?? 0, color: "text-amber-400", bg: "border-amber-500/15" },
          { label: "Medium", value: data?.medium ?? 0, color: "text-zinc-300", bg: "border-white/[0.06]" },
          { label: "Low", value: data?.low ?? 0, color: "text-zinc-500", bg: "border-white/[0.06]" },
        ].map((s) => (
          <div key={s.label} className={`bg-card border ${s.bg} rounded-xl p-4`}>
            <div className="text-[10px] text-zinc-600 uppercase tracking-wider">{s.label}</div>
            <div className={`text-2xl font-semibold font-mono mt-1 ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex bg-card border border-white/[0.06] rounded-lg p-0.5">
          {["all", "critical", "high", "medium", "low"].map((s) => (
            <button key={s} onClick={() => setSevFilter(s)}
              className={`px-2.5 py-1 rounded text-[10px] font-medium transition-all ${
                sevFilter === s ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-zinc-400"
              }`}>{s}</button>
          ))}
        </div>
        <button onClick={() => refetch()} className="p-1.5 rounded text-zinc-600 hover:text-zinc-400 transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        </button>
        <span className="text-[11px] text-zinc-600 font-mono ml-auto">{data?.total ?? 0} defects</span>
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 rounded-xl shimmer-bg" />)}</div>
      ) : queue.length === 0 ? (
        <div className="text-center py-12 text-sm text-zinc-600">No defects in the last 7 days</div>
      ) : (
        <div className="bg-card border border-white/[0.06] rounded-xl overflow-hidden">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-white/[0.06] text-zinc-600">
                <th className="text-left px-4 py-2.5 font-medium">Test Name</th>
                <th className="text-left px-4 py-2.5 font-medium">Failures</th>
                <th className="text-left px-4 py-2.5 font-medium">Error</th>
                <th className="text-left px-4 py-2.5 font-medium">First Seen</th>
                <th className="text-left px-4 py-2.5 font-medium">Severity</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((d: any, i: number) => (
                <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-3 text-zinc-300 font-mono text-[11px]">{d.test_name}</td>
                  <td className="px-4 py-3 font-mono text-zinc-400">{d.fail_count}</td>
                  <td className="px-4 py-3 text-zinc-600 text-[10px] max-w-[200px] truncate" title={d.error_message}>{d.error_message?.slice(0, 50) || "—"}</td>
                  <td className="px-4 py-3 text-zinc-600 font-mono text-[10px]">{d.first_seen ? new Date(d.first_seen).toLocaleDateString() : "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      d.severity === "critical" ? "bg-red-500/10 text-red-400" :
                      d.severity === "high" ? "bg-amber-500/10 text-amber-400" :
                      d.severity === "medium" ? "bg-blue-500/10 text-blue-400" :
                      "bg-zinc-800 text-zinc-500"
                    }`}>{d.severity}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                      d.status === "quarantined" ? "bg-zinc-500/10 text-zinc-400" : "bg-zinc-800 text-zinc-500"
                    }`}>{d.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DefectsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["defect-prediction"],
    queryFn: () => api.get<any>("/api/defect/predict?days=30").catch(() => ({ modules: [] })),
  });

  const modules = data?.modules ?? [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "High Risk", value: data?.high_risk_count ?? 0, color: "text-red-400" },
          { label: "Medium Risk", value: data?.medium_risk_count ?? 0, color: "text-amber-400" },
          { label: "Total Modules", value: data?.total_modules ?? 0, color: "text-zinc-100" },
        ].map((s) => (
          <div key={s.label} className="bg-card border border-white/[0.06] rounded-xl p-4">
            <div className="text-[10px] text-zinc-600 uppercase tracking-wider">{s.label}</div>
            <div className={cn("text-2xl font-semibold font-mono mt-1", s.color)}>{s.value}</div>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 rounded-xl shimmer-bg" />)}</div>
      ) : modules.length === 0 ? (
        <div className="text-center py-12 text-sm text-zinc-600">No module risk data available</div>
      ) : (
        <div className="space-y-2">
          {modules.slice(0, 20).map((m: any, i: number) => {
            const riskColor = m.risk_score >= 70 ? "bg-red-500" : m.risk_score >= 40 ? "bg-amber-500" : "bg-emerald-500";
            return (
              <div key={i} className="bg-card border border-white/[0.06] rounded-xl p-4">
                <div className="flex items-center gap-4">
                  <span className="text-[10px] font-mono text-zinc-600 w-6">#{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[13px] font-medium text-zinc-200">{m.module || m.name || `module-${i}`}</span>
                      <span className={cn("text-sm font-semibold font-mono", m.risk_score >= 70 ? "text-red-400" : m.risk_score >= 40 ? "text-amber-400" : "text-emerald-400")}>
                        {m.risk_score?.toFixed(1) || "0"}
                      </span>
                    </div>
                    <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                      <div className={cn("h-full rounded-full", riskColor)} style={{ width: `${Math.min(m.risk_score || 0, 100)}%` }} />
                    </div>
                    <div className="flex gap-3 mt-1 text-[10px] text-zinc-600">
                      <span>Failure rate: {m.failure_rate?.toFixed(2) || "0"}</span>
                      {m.trend && <span className={m.trend > 0 ? "text-red-400" : "text-emerald-400"}>{m.trend > 0 ? "↑" : "↓"} {Math.abs(m.trend).toFixed(1)}%</span>}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TrendsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["quality-trends"],
    queryFn: () => api.get<any>("/api/quality/trend?days=90"),
    staleTime: 120_000,
  });
  const { data: metrics } = useQuery({
    queryKey: ["quality-metrics"],
    queryFn: () => api.get<any>("/api/quality/metrics?period=90d"),
    staleTime: 120_000,
  });

  if (isLoading) return <div className="py-12 text-center text-sm text-zinc-600">Loading trends...</div>;
  const trend = data?.trend ?? [];
  const latest = trend[trend.length - 1];
  const prev = trend[trend.length - 2];

  const passRate = latest?.score ?? 0;
  const prevPass = prev?.score ?? 0;
  const passDelta = (passRate - prevPass).toFixed(1);
  const passColor = Number(passDelta) >= 0 ? "text-emerald-400" : "text-red-400";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Pass Rate", value: `${passRate.toFixed(1)}%`, delta: `${Number(passDelta) >= 0 ? "+" : ""}${passDelta}%`, deltaColor: passColor },
          { label: "Coverage", value: metrics?.metrics?.coverage_line?.[metrics?.metrics?.coverage_line?.length - 1]?.value ? `${Number(metrics.metrics.coverage_line.slice(-1)[0].value).toFixed(1)}%` : "\u2014", delta: "\u2014", deltaColor: "text-zinc-500" },
          { label: "Quality Score", value: passRate.toFixed(1), delta: `${Number(passDelta) >= 0 ? "+" : ""}${passDelta}`, deltaColor: passColor },
        ].map((s) => (
          <div key={s.label} className="bg-card border border-white/[0.06] rounded-xl p-4">
            <div className="text-[10px] text-zinc-600 uppercase tracking-wider">{s.label}</div>
            <div className="text-2xl font-semibold font-mono text-zinc-100 mt-1">{s.value}</div>
            <div className={cn("text-[11px] font-mono mt-1", s.deltaColor)}>{s.delta} vs previous sprint</div>
          </div>
        ))}
      </div>

      <div className="bg-card border border-white/[0.06] rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-white/[0.06]">
          <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Sprint Comparison</span>
        </div>
        {trend.length === 0 ? (
          <div className="text-sm text-zinc-600 text-center py-8">No trend data available</div>
        ) : (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-white/[0.06] text-zinc-600">
                <th className="text-left px-4 py-2.5 font-medium">Period</th>
                <th className="text-left px-4 py-2.5 font-medium">Score</th>
                <th className="text-left px-4 py-2.5 font-medium">Verdict</th>
                <th className="text-left px-4 py-2.5 font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {trend.slice(-8).map((t: any, i: number) => {
                const prevScore = i > 0 ? trend[trend.length - 1 - (i - 1)]?.score : t.score;
                const change = (t.score - prevScore).toFixed(1);
                return (
                  <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3 text-zinc-300 font-mono text-[11px]">{new Date(t.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</td>
                    <td className="px-4 py-3">
                      <span className={cn("font-mono font-semibold", t.score >= 80 ? "text-emerald-400" : t.score >= 60 ? "text-amber-400" : "text-red-400")}>{t.score.toFixed(1)}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-medium uppercase px-1.5 py-0.5 rounded", t.verdict === "go" ? "bg-emerald-500/10 text-emerald-400" : t.verdict === "caution" ? "bg-amber-500/10 text-amber-400" : "bg-red-500/10 text-red-400")}>{t.verdict}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("font-mono", Number(change) >= 0 ? "text-emerald-400" : "text-red-400")}>{Number(change) >= 0 ? "+" : ""}{change}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function QualityPage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] flex items-center justify-center bg-background"><div className="flex items-center gap-3 text-zinc-600"><Gauge className="w-4 h-4 animate-spin" strokeWidth={1.5} /><span className="text-sm">Loading quality...</span></div></div>}>
      <QualityPageInner />
    </Suspense>
  );
}
