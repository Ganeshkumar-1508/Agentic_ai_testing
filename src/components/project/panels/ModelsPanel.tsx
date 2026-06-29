"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function ModelsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "providers"],
    queryFn: async () => {
      return (await api.get<any[]>(`/api/settings/providers`))?? [];
    },
  });

  const providers = Array.isArray(data) ? data : [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-neutral-100">Models & Fallback</h2>
        <p className="text-sm text-neutral-500 mt-1">Tiered provider fallback chain and model routing</p>
      </div>
      {providers.length === 0 && !isLoading && (
        <div className="flex items-center justify-center h-48 text-neutral-500 text-sm">
          No providers configured
        </div>
      )}
      {isLoading && (
        <div className="flex items-center justify-center h-48 text-neutral-500 text-sm">
          Loading providers...
        </div>
      )}
      <div className="space-y-3">
        {providers.map((p: any, i: number) => (
          <div key={p.provider} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="flex items-center justify-center w-6 h-6 rounded-full bg-white/[0.06] text-xs font-mono text-neutral-400">
                  {i + 1}
                </span>
                <div>
                  <span className="text-sm font-medium text-neutral-200">{p.provider}</span>
                  <span className="text-xs text-neutral-500 ml-2">Tier {i < 2 ? "Primary" : i < 4 ? "Secondary" : "Fallback"}</span>
                </div>
              </div>
              {p.configured ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
              ) : (
                <XCircle className="w-4 h-4 text-neutral-600" strokeWidth={1.5} />
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div><span className="text-neutral-500">Model: </span><span className="text-neutral-300 font-mono">{p.model || "—"}</span></div>
              <div><span className="text-neutral-500">Key: </span><span className={p.has_key ? "text-emerald-400" : "text-neutral-600"}>{p.has_key ? "Set" : "Missing"}</span></div>
              <div><span className="text-neutral-500">Base URL: </span><span className="text-neutral-300 font-mono truncate">{p.base_url || "default"}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
