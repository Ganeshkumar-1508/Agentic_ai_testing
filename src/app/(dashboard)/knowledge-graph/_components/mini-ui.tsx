"use client";

import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function SectionCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("rounded-2xl border border-white/[0.06] bg-white/[0.02] p-3.5", className)}>{children}</div>;
}

export function StatPill({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-mono text-neutral-500">
      <span className="uppercase tracking-[0.18em]">{label}</span>
      <span className={cn("font-semibold text-neutral-100", accent && "text-emerald-300")}>{value}</span>
    </div>
  );
}

export function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="text-[8px] font-mono uppercase tracking-[0.24em] text-neutral-500">{label}</div>
      <div className="mt-1 text-[13px] font-semibold text-neutral-100">{value}</div>
    </div>
  );
}

export function MetadataRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-2">
      <div className="w-20 shrink-0 text-[10px] font-mono uppercase tracking-[0.18em] text-neutral-500">{label}</div>
      <div className={cn("min-w-0 flex-1 break-words text-[11px] text-neutral-300", mono && "font-mono text-[10.5px]")}>{value}</div>
    </div>
  );
}

export function GraphMetaBadge({ icon: Icon, label, value, accent }: { icon?: LucideIcon; label?: string; value: string; accent?: boolean }) {
  return (
    <div className={cn("hidden items-center gap-1.5 rounded-xl border px-2.5 py-2 text-[10px] font-mono lg:inline-flex", accent ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-200" : "border-white/[0.06] bg-white/[0.03] text-neutral-400")}>
      {Icon ? <Icon className="h-3 w-3" strokeWidth={1.7} /> : null}
      {label ? <span className="text-neutral-600">{label}</span> : null}
      <span className="max-w-[220px] truncate">{value}</span>
    </div>
  );
}
