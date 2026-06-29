"use client";

import { useQuery } from "@tanstack/react-query";
import { Crosshair, GitBranch, TestTube, Clock } from "lucide-react";
import { api } from "@/lib/api/api-client";

const API = typeof window !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001" : "http://localhost:8001";

export function ImpactPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "impact"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/impact`))as any;
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-zinc-100">Test Impact Analysis</h2>
        <p className="text-sm text-zinc-500 mt-1">Predict which tests to run based on code changes</p>
      </div>
      <div className="shimmer-bg border border-zinc-800/30 rounded-xl p-6 space-y-4">
        <h3 className="text-sm font-medium text-zinc-300">Impact Summary</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Changed Files", value: data?.changedFiles ?? 0, icon: GitBranch, color: "text-zinc-100" },
            { label: "Affected Tests", value: data?.affectedTests ?? 0, icon: Crosshair, color: "text-amber-400" },
            { label: "Total Tests", value: data?.totalTests ?? 0, icon: TestTube, color: "text-emerald-400" },
            { label: "Time Saved", value: data ? `${data.estimatedTimeSaved}%` : "—", icon: Clock, color: "text-blue-400" },
          ].map((card) => (
            <div key={card.label} className="space-y-1.5">
              <div className="flex items-center gap-2">
                <card.icon className={`w-3.5 h-3.5 ${card.color}`} strokeWidth={1.5} />
                <span className="text-xs text-zinc-500">{card.label}</span>
              </div>
              <p className={`text-2xl font-semibold ${isLoading ? "text-zinc-600" : "text-zinc-100"}`}>
                {isLoading ? "..." : card.value}
              </p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-center h-32 bg-zinc-900/30 border border-zinc-800/30 rounded-xl text-sm text-zinc-600">
        Connect a git repository and run a pipeline to see file-to-test mappings
      </div>
    </div>
  );
}
