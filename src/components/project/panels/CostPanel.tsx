"use client";

import { useQuery } from "@tanstack/react-query";
import { DollarSign, Coins, Cpu, TrendingUp, Wallet } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "@/lib/api/api-client";


export function CostPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "cost"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/cost`))?? {};
    },
  });

  const recentUsage = ((data as any)?.recentUsage ?? []).slice(-30).map((u: any) => ({
    date: u.date?.slice(0, 10) || "",
    tokens: u.tokens ?? 0,
    cost: +(u.cost ?? 0).toFixed(4),
  }));

  const models = ((data as any)?.configuredModels ?? []).map((m: any) => ({
    name: `${m.provider}: ${m.model}`,
    value: 1,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-neutral-100">Cost & Usage</h2>
        <p className="text-sm text-neutral-500 mt-1">Token consumption and cost tracking</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { label: "Total Tokens", value: (data as any)?.totalTokens?.toLocaleString() ?? "—", icon: Coins, color: "text-emerald-400" },
          { label: "Total Cost", value: (data as any) ? `$${(data as any).totalCost.toFixed(4)}` : "—", icon: DollarSign, color: "text-emerald-400" },
          { label: "Sessions", value: (data as any)?.sessionCount ?? "—", icon: Cpu, color: "text-blue-400" },
          { label: "Avg / Session", value: (data as any) ? `$${(data as any).avgCostPerSession.toFixed(4)}` : "—", icon: Wallet, color: "text-amber-400" },
          { label: "Models Active", value: models.length || "—", icon: TrendingUp, color: "text-emerald-400" },
        ].map((card) => (
          <div key={card.label} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-500 font-medium">{card.label}</span>
              <card.icon className={`w-4 h-4 ${card.color}`} strokeWidth={1.5} />
            </div>
            <p className="text-xl font-semibold text-neutral-100">{isLoading ? "..." : card.value}</p>
          </div>
        ))}
      </div>

      {recentUsage.length > 0 && (
        <>
          <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-medium text-neutral-300">Usage Stream</h3>
            <p className="text-[10px] text-neutral-600">Token volume and cost over time</p>
            <div className="h-48 min-h-[192px]">
              <ResponsiveContainer width="100%" height={192} debounce={50}>
                <AreaChart data={recentUsage} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="tokenGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#34d399" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", fontSize: "12px" }} />
                  <Area type="monotone" dataKey="tokens" stroke="#34d399" strokeWidth={1.5} fill="url(#tokenGrad)" dot={false} stackId="1" />
                  <Area type="monotone" dataKey="cost" stroke="#f59e0b" strokeWidth={1.5} fill="url(#costGrad)" dot={false} stackId="2" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {models.length > 0 && (
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-medium text-neutral-300">Configured Models</h3>
          <div className="space-y-2">
            {models.map((m: any) => (
              <div key={m.name} className="flex items-center justify-between py-2 border-b border-white/[0.04] last:border-0 text-xs">
                <span className="text-neutral-300 font-mono">{m.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
