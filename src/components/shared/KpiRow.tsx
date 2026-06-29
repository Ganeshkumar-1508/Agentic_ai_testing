"use client";

import { cn } from "@/lib/utils";

interface KpiItem {
  label: string;
  value: React.ReactNode;
  sub?: string;
  pulse?: boolean;
}

export function KpiRow({ items }: { items: KpiItem[] }) {
  return (
    <div className="border-t border-white/[0.06]">
      <div className="grid grid-cols-4 divide-x divide-white/[0.06]">
        {items.map((kpi, i) => (
          <div key={i} className="py-5 px-6 first:pl-0 last:pr-0">
            <div className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">{kpi.label}</div>
            <div className="text-[28px] font-semibold font-mono text-zinc-100 tabular-nums flex items-center gap-2 leading-none">
              {kpi.value}
              {kpi.pulse && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
            </div>
            {kpi.sub && <div className="text-[11px] text-zinc-600 font-mono mt-2">{kpi.sub}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
