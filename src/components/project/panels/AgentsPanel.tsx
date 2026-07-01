"use client";

import { useQuery } from "@tanstack/react-query";
import { type ElementType } from "react";
import { Bot, Cpu, Shield, Search, PenTool, Settings2 } from "lucide-react";
import { api } from "@/lib/api/api-client";


const MODE_ICONS: Record<string, ElementType> = {
  auto: Cpu,
  ask: Search,
  architect: PenTool,
  debug: Shield,
  custom: Settings2,
};

export function AgentsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["modes"],
    queryFn: async () => {
      return (await api.get<any>(`/api/modes`))?? {};
    },
  });

  const modes = (data as any)?.modes ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-neutral-100">Sub-Agent Dashboard</h2>
        <p className="text-sm text-neutral-500 mt-1">Monitor and manage agent modes and configurations</p>
      </div>
      {isLoading && (
        <div className="flex items-center justify-center h-48 text-neutral-500 text-sm">Loading modes...</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {modes.map((m: any) => {
          const Icon = MODE_ICONS[m.name] || Bot;
          return (
            <div key={m.name} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Icon className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                </div>
                <div>
                  <h3 className="text-sm font-medium text-neutral-200 capitalize">{m.name}</h3>
                  <p className="text-xs text-neutral-500">{m.description || "—"}</p>
                </div>
              </div>
              {m.toolsets && m.toolsets.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {m.toolsets.map((t: string) => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-neutral-500">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
