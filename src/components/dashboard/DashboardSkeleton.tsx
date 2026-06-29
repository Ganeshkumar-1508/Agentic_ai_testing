"use client";

import { Loader2 } from "lucide-react";

function KpiCell() {
  return (
    <div className="rounded-[2rem] p-5 space-y-3" style={{ background: "#0e0e18" }}>
      <div className="flex items-center justify-between">
        <div className="w-20 h-3 rounded shimmer-bg" />
        <div className="w-5 h-5 rounded shimmer-bg" />
      </div>
      <div className="w-16 h-7 rounded-lg shimmer-bg" />
      <div className="flex gap-1 items-end h-5">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="flex-1 rounded-sm shimmer-bg" style={{ height: `${30 + (i * 7) % 50}%` }} />
        ))}
      </div>
    </div>
  );
}

function Block({ h = 200, p = 6 }: { h?: number; p?: number }) {
  return (
    <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
      <div className="w-28 h-3 rounded shimmer-bg" />
      <div className="w-20 h-3 rounded shimmer-bg" />
      <div className="rounded-lg shimmer-bg" style={{ height: h - 60 }} />
    </div>
  );
}

function HeaderRow() {
  return (
    <div className="flex items-start justify-between mb-2 flex-wrap gap-3">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="w-28 h-6 rounded shimmer-bg" />
          <div className="w-20 h-4 rounded-full shimmer-bg" />
        </div>
        <div className="w-64 h-3 rounded shimmer-bg" />
      </div>
      <div className="flex items-center gap-2">
        <div className="w-56 h-7 rounded-full shimmer-bg" />
        <div className="w-9 h-9 rounded-lg shimmer-bg" />
        <div className="w-16 h-7 rounded-lg shimmer-bg" />
        <div className="w-16 h-7 rounded-lg shimmer-bg" />
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="max-w-7xl mx-auto px-8 pt-6 pb-12 space-y-4">
      <HeaderRow />

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {Array.from({ length: 6 }).map((_, i) => <KpiCell key={i} />)}
      </div>

      <div className="flex items-center gap-4 px-4 py-2.5 bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem]">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full shimmer-bg" />
            <div className="w-20 h-3 rounded shimmer-bg" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        <div className="h-[200px]"><Block h={200} /></div>
        <div className="h-[200px]"><Block h={200} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        <div className="h-[260px]"><Block h={260} /></div>
        <div className="h-[260px]"><Block h={260} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        <div className="h-[260px]"><Block h={260} /></div>
        <div className="h-[260px]"><Block h={260} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        <div className="h-[320px]"><Block h={320} /></div>
        <div className="flex flex-col gap-4">
          <div className="h-[150px]"><Block h={150} /></div>
          <div className="h-[150px]"><Block h={150} /></div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr_1fr] gap-4">
        <div className="h-[220px]"><Block h={220} /></div>
        <div className="h-[220px]"><Block h={220} /></div>
        <div className="h-[220px]"><Block h={220} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_1.5fr] gap-4">
        <div className="h-[200px]"><Block h={200} /></div>
        <div className="h-[200px]"><Block h={200} /></div>
        <div className="h-[200px]"><Block h={200} /></div>
      </div>

      <div className="h-[260px]"><Block h={260} /></div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr_1fr] gap-4">
        <div className="h-[200px]"><Block h={200} /></div>
        <div className="h-[200px]"><Block h={200} /></div>
        <div className="h-[200px]"><Block h={200} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-4">
        <div className="h-[220px]"><Block h={220} /></div>
        <div className="h-[220px]"><Block h={220} /></div>
      </div>

      <div className="h-[220px]"><Block h={220} /></div>

      <div className="h-[180px]"><Block h={180} /></div>

      <div className="flex items-center gap-2 px-4 py-2 text-[11px] text-zinc-700">
        <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.5} />
        <span>Compiling dashboard data…</span>
      </div>
    </div>
  );
}
