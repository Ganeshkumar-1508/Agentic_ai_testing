"use client";

import { useQuery } from "@tanstack/react-query";
import { TrendingDown, AlertTriangle, CheckCircle2, Activity } from "lucide-react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { api } from "@/lib/api/api-client";


export function RegressionPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "regression"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/regression`))?? {};
    },
  });

  const runData = ((data as any)?.runTrend ?? []).map((r: any) => ({ date: r.date?.slice(0, 10) || "", status: r.status === "completed" ? 1 : r.status === "failed" ? -1 : 0, label: r.status }));
  const flakyData = ((data as any)?.flakyTrend ?? []).map((r: any) => ({ date: r.date?.slice(0, 10) || "", score: r.score }));
  const covData = ((data as any)?.coverageTrend ?? []).map((r: any) => ({ date: r.date?.slice(0, 10) || "", line: r.lineCoverage ?? 0, branch: r.branchCoverage ?? 0 }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-neutral-100">Regression Detection</h2>
        <p className="text-sm text-neutral-500 mt-1">Automatically detect performance and quality regressions</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: "Total Runs", value: (data as any)?.totalRuns ?? "—", icon: Activity, color: "text-neutral-100" },
          { label: "Passing", value: ((data as any)?.runTrend ?? []).filter((r: any) => r.status === "completed").length, icon: CheckCircle2, color: "text-emerald-400" },
          { label: "Flaky Tracked", value: ((data as any)?.flakyTrend ?? []).length, icon: AlertTriangle, color: "text-amber-400" },
          { label: "Coverage Reports", value: ((data as any)?.coverageTrend ?? []).length, icon: TrendingDown, color: "text-emerald-400" },
        ].map((card) => (
          <div key={card.label} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-500 font-medium">{card.label}</span>
              <card.icon className={`w-4 h-4 ${card.color}`} strokeWidth={1.5} />
            </div>
            <p className="text-xl font-semibold text-neutral-100">{isLoading ? "..." : String(card.value)}</p>
          </div>
        ))}
      </div>

      {covData.length > 0 && (
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-medium text-neutral-300">Coverage Trend</h3>
          <div className="h-48 min-h-[192px]">
            <ResponsiveContainer width="100%" height={192} debounce={50}>
              <LineChart data={covData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", fontSize: "12px" }} />
                <Line type="monotone" dataKey="line" stroke="#34d399" strokeWidth={2} dot={false} name="Line Coverage" />
                <Line type="monotone" dataKey="branch" stroke="#fbbf24" strokeWidth={2} dot={false} name="Branch Coverage" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {runData.length > 0 && (
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-medium text-neutral-300">Run Status Timeline</h3>
          <div className="h-24 min-h-[96px]">
            <ResponsiveContainer width="100%" height={96} debounce={50}>
              <BarChart data={runData} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 9 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", fontSize: "12px" }}
                  formatter={(_: any, __: any, props: any) => [props.payload?.label || "unknown", "Status"]} />
                <Bar dataKey="status" radius={[3, 3, 0, 0]} maxBarSize={24}>
                  {runData.map((entry: any, idx: number) => (
                    <Cell key={idx} fill={entry.label === "completed" ? "#34d399" : entry.label === "failed" ? "#ef4444" : "#64748b"} opacity={entry.label === "completed" ? 0.9 : entry.label === "failed" ? 0.9 : 0.4} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-4 text-[10px] text-zinc-600">
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-400" /> Pass</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-400" /> Fail</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-zinc-600 opacity-40" /> Other</span>
          </div>
        </div>
      )}

      {flakyData.length > 0 && (
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-medium text-neutral-300">Flaky Score Trend</h3>
          <div className="h-32 min-h-[128px]">
            <ResponsiveContainer width="100%" height={128} debounce={50}>
              <LineChart data={flakyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", fontSize: "12px" }} />
                <Line type="monotone" dataKey="score" stroke="#f59e0b" strokeWidth={2} dot={false} name="Flaky Score" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
