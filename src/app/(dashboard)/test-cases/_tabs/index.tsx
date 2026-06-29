"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, BASE_URL } from "@/lib/api/api-client";
import {
  AlertTriangle, Activity, Shield, RefreshCw, TrendingUp,
  Eye, RocketIcon,
} from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";

export function FlakyTab() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["flaky-tests-summary"],
    queryFn: async () => {
      const json = await api.get<any>("/api/tests/flaky", { limit: "50" });
      const flaky = json?.flaky ?? [];
      const total = flaky.length;
      const avgScore = total > 0 ? flaky.reduce((s: number, t: any) => s + (t.flakyScore ?? 0), 0) / total : 0;
      const quarantined = flaky.filter((t: any) => t.isQuarantined).length;
      return { total, avgScore, quarantined, flaky };
    },
  });

  const [filter, setFilter] = useState("all");

  if (isLoading) return <div className="py-12 text-center text-sm text-zinc-600">Loading flaky tests...</div>;
  if (!data) return <EmptyState icon={AlertTriangle} title="No Flaky Tests" description="All tests are healthy" />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Flaky Tests", value: data.total, icon: AlertTriangle, color: "text-amber-400" },
          { label: "Avg Score", value: `${(data.avgScore || 0).toFixed(1)}%`, icon: TrendingUp, color: "text-emerald-400" },
          { label: "Quarantined", value: data.quarantined, icon: Shield, color: "text-blue-400" },
        ].map((s) => (
          <div key={s.label} className="bg-[#0e0e18] border border-white/[0.06] rounded-xl p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{s.label}</span>
              <s.icon className="w-4 h-4" style={{ color: s.color.split(" ")[0].replace("text-", "") }} strokeWidth={1.5} />
            </div>
            <div className="text-xl font-semibold font-mono text-zinc-100">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex bg-[#12121c] border border-white/[0.06] rounded-lg p-0.5">
          {["all", "high", "medium", "low"].map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded text-[10px] font-medium transition-all ${
                filter === f ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-zinc-400"
              }`}>{f}</button>
          ))}
        </div>
        <button onClick={() => refetch()} className="p-1.5 rounded text-zinc-600 hover:text-zinc-400 transition-colors">
          <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.5} />
        </button>
      </div>

      <div className="bg-[#0e0e18] border border-white/[0.06] rounded-xl overflow-hidden">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-white/[0.06] text-zinc-600">
              <th className="text-left px-4 py-2 font-medium">Test</th>
              <th className="text-left px-4 py-2 font-medium">Score</th>
              <th className="text-left px-4 py-2 font-medium">Status</th>
              <th className="text-left px-4 py-2 font-medium">Last Healed</th>
            </tr>
          </thead>
          <tbody>
            {(data.flaky || []).filter((t: any) => filter === "all" || (t.flakyScore || 0) > (filter === "high" ? 50 : filter === "medium" ? 20 : 0)).slice(0, 20).map((t: any, i: number) => (
              <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                <td className="px-4 py-2.5 text-zinc-300 font-mono text-[11px]">{t.name || t.id?.slice(0, 24) || `test-${i}`}</td>
                <td className="px-4 py-2.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                    (t.flakyScore || 0) > 50 ? "bg-red-500/10 text-red-400" :
                    (t.flakyScore || 0) > 20 ? "bg-amber-500/10 text-amber-400" :
                    "bg-emerald-500/10 text-emerald-400"
                  }`}>{t.flakyScore?.toFixed(0) || "0"}</span>
                </td>
                <td className="px-4 py-2.5">
                  <span className="flex items-center gap-1 text-zinc-500">
                    {t.isQuarantined ? <Shield className="w-3 h-3 text-blue-400" strokeWidth={1.5} /> : <Activity className="w-3 h-3" strokeWidth={1.5} />}
                    {t.isQuarantined ? "Quarantined" : "Active"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-zinc-600 font-mono text-[10px]">{t.lastHealed ? new Date(t.lastHealed).toLocaleDateString() : "\u2014"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function VisualTab() {
  const [url, setUrl] = useState("");
  const [testName, setTestName] = useState("");
  const [view, setView] = useState("1280x720");
  const [captured, setCaptured] = useState<{path: string; hash: string} | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const { data: baselines } = useQuery({
    queryKey: ["visual-baselines"],
    queryFn: async () => {
      const d = await api.get<any>("/api/testing/visual/baselines");
      return d?.baselines ?? [];
    },
  });

  const capture = async () => {
    if (!url.trim()) return;
    setCapturing(true);
    setStatus(null);
    try {
      const data = await api.post<any>("/api/testing/visual/capture", { url: url.trim(), name: testName.trim() || undefined, viewport: view });
      setCaptured({ path: data.path, hash: data.hash });
      setStatus("Captured successfully");
    } catch (e: any) {
      setStatus(e?.message || "Capture failed");
    } finally {
      setCapturing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-[#0e0e18] border border-white/[0.06] rounded-xl p-5 space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-600 uppercase tracking-wider">URL</label>
            <input value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 placeholder-zinc-700 outline-none focus:border-emerald-500/30" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-600 uppercase tracking-wider">Test Name</label>
            <input value={testName} onChange={(e) => setTestName(e.target.value)}
              placeholder="homepage-hero (optional)"
              className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 placeholder-zinc-700 outline-none focus:border-emerald-500/30" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-600 uppercase tracking-wider">Viewport</label>
            <select value={view} onChange={(e) => setView(e.target.value)}
              className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30">
              <option value="1280x720">Desktop (1280x720)</option>
              <option value="1920x1080">Full HD (1920x1080)</option>
              <option value="375x812">Mobile (375x812)</option>
            </select>
          </div>
        </div>
        <button onClick={capture} disabled={capturing || !url.trim()}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors disabled:opacity-40 text-[12px] font-medium">
          {capturing ? "Capturing..." : "Capture Screenshot"}
        </button>
        {status && <p className="text-[11px] text-zinc-500">{status}</p>}
      </div>

      {captured && (
        <div className="bg-[#0e0e18] border border-white/[0.06] rounded-xl p-4">
          <div className="text-[11px] text-zinc-500 mb-2 font-mono">{captured.path}</div>
          <div className="bg-[#12121c] rounded-lg h-[300px] flex items-center justify-center text-zinc-700 text-[12px]">
            Screenshot: {captured.hash?.slice(0, 12)}
          </div>
        </div>
      )}

      {baselines && (baselines as any[]).length > 0 && (
        <div className="bg-[#0e0e18] border border-white/[0.06] rounded-xl p-4">
          <div className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-3">Baselines</div>
          <div className="space-y-1">
            {(baselines as any[]).slice(0, 10).map((b: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-[11px] text-zinc-400 py-1">
                <Eye className="w-3 h-3" strokeWidth={1.5} />
                <span className="font-mono">{b.name || b.id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function LoadTab() {
  const [spec, setSpec] = useState("{}");
  const [vuCount, setVuCount] = useState(10);
  const [duration, setDuration] = useState(60);
  const [testType, setTestType] = useState("stress");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [status, setStatus] = useState<string | null>(null);

  const runTest = async () => {
    setRunning(true);
    setResult(null);
    setStatus("Running...");
    try {
      const parsed = JSON.parse(spec);
      const data = await api.post<any>("/api/testing/load/run", {
        openapi_spec: parsed, test_type: testType, vu_count: vuCount, duration_sec: duration,
      });
      setResult(data);
      setStatus(data.status === "completed" ? "Test completed" : data.error || "Failed");
    } catch (e: any) {
      setStatus(e?.message || "Test failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-6">
        <div className="bg-[#0e0e18] border border-white/[0.06] rounded-xl p-5 space-y-4">
          <div>
            <label className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5 block">OpenAPI Spec (JSON)</label>
            <textarea value={spec} onChange={(e) => setSpec(e.target.value)} rows={8}
              className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[11px] text-zinc-300 font-mono outline-none focus:border-emerald-500/30 resize-none" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1 block">VUs</label>
              <input type="number" value={vuCount} onChange={(e) => setVuCount(Number(e.target.value))}
                className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1 block">Duration (s)</label>
              <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))}
                className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1 block">Type</label>
              <select value={testType} onChange={(e) => setTestType(e.target.value)}
                className="w-full bg-[#12121c] border border-white/[0.06] rounded-lg px-3 py-2 text-[12px] text-zinc-300 outline-none focus:border-emerald-500/30">
                <option value="stress">Stress</option>
                <option value="soak">Soak</option>
                <option value="spike">Spike</option>
              </select>
            </div>
          </div>
          <button onClick={runTest} disabled={running}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors disabled:opacity-40 text-[12px] font-medium">
            {running ? "Running..." : "Run Load Test"}
          </button>
          {status && <p className="text-[11px] text-zinc-500">{status}</p>}
        </div>
        {result && (
          <div className="bg-[#0e0e18] border border-white/[0.06] rounded-xl p-5 space-y-3">
            <div className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Results</div>
            {[
              { l: "Status", v: result.status },
              { l: "Total Requests", v: result.total_requests?.toLocaleString() },
              { l: "Avg Latency", v: result.avg_latency_ms ? `${result.avg_latency_ms.toFixed(0)}ms` : "\u2014" },
              { l: "P95", v: result.p95_latency_ms ? `${result.p95_latency_ms.toFixed(0)}ms` : "\u2014" },
              { l: "Error Rate", v: result.error_rate ? `${(result.error_rate * 100).toFixed(1)}%` : "\u2014" },
            ].filter((r) => r.v).map((r) => (
              <div key={r.l} className="flex justify-between text-[12px]">
                <span className="text-zinc-600">{r.l}</span>
                <span className="text-zinc-300 font-mono">{r.v}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
