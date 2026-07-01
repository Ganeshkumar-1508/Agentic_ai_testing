"use client";

import { Suspense, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";
import { type ElementType } from "react";
import { Webhook, Puzzle, Clock, Plus, Trash2, ToggleLeft, ToggleRight, Loader2, Network, History } from "lucide-react";
import { SessionBrowser } from "@/components/settings/SessionBrowser";

type AdminTab = "hooks" | "plugins" | "cron" | "swarm" | "sessions";

const TABS: { id: AdminTab; label: string; icon: ElementType }[] = [
  { id: "hooks", label: "Hooks", icon: Webhook },
  { id: "plugins", label: "Plugins", icon: Puzzle },
  { id: "cron", label: "Cron Jobs", icon: Clock },
  { id: "swarm", label: "Swarm", icon: Network },
  { id: "sessions", label: "Sessions", icon: History },
];

const SPRING = { type: "spring" as const, stiffness: 100, damping: 20 };

function AdminPageInner() {
  const [activeTab, setActiveTab] = useState<AdminTab>("hooks");

  return (
    <div className="max-w-7xl mx-auto px-8 pt-6 pb-12 space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.18em] mb-2">/admin</div>
          <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100 leading-none">Admin</h1>
          <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Hooks, plugins, cron jobs, swarm state, and session browser. One place to inspect and steer the platform's moving parts.</p>
        </div>
        <div className="flex bg-white/[0.02] border border-white/[0.06] rounded-2xl p-0.5 gap-0.5">
          {TABS.map((t) => {
            const TabIcon = t.icon;
            return (
              <motion.button key={t.id} whileTap={{ scale: 0.97 }} onClick={() => setActiveTab(t.id)}
                className={cn("flex items-center gap-1.5 px-3 h-8 rounded-xl text-[11.5px] font-medium transition-colors",
                  activeTab === t.id
                    ? "bg-emerald-500 text-zinc-950 shadow-[0_2px_8px_-2px_rgba(16,185,129,0.4)]"
                    : "text-zinc-500 hover:text-zinc-200")}>
                <TabIcon className="w-3.5 h-3.5" strokeWidth={1.5} />
                {t.label}
              </motion.button>
            );
          })}
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={activeTab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={SPRING}>
          {activeTab === "hooks" && <HooksTab />}
          {activeTab === "plugins" && <PluginsTab />}
          {activeTab === "cron" && <CronTab />}
          {activeTab === "swarm" && <SwarmTab />}
          {activeTab === "sessions" && <SessionBrowser />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function HooksTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-hooks"],
    queryFn: () => api.get<any>("/api/admin/hooks"),
  });
  const { data: events } = useQuery({
    queryKey: ["admin-hook-events"],
    queryFn: () => api.get<any>("/api/admin/hooks/events"),
  });

  const hookMap = data?.hooks ?? {};
  const eventList = events?.events ?? [];

  if (isLoading) return <SkeletonRows n={3} />;

  return (
    <div className="space-y-6">
      <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-5">
        <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Registered Hooks</div>
        {Object.keys(hookMap).length === 0 ? (
          <EmptyState message="No hooks registered" sub="Add a hook in your code with the dispatcher to see it here." />
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {Object.entries(hookMap).map(([event, hooks]: [string, any]) => (
              <div key={event} className="py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-[10.5px] font-mono text-zinc-500 w-44 shrink-0">{event}</span>
                  <span className="text-[11px] text-zinc-300">{Array.isArray(hooks) ? hooks.length : 1} handler(s)</span>
                </div>
                <span className="text-[10px] font-mono text-zinc-700">{Array.isArray(hooks) ? hooks.join(", ") : ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-5">
        <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Recent Events</div>
        {eventList.length === 0 ? <EmptyState message="No events yet" /> : (
          <div className="space-y-1.5 max-h-80 overflow-y-auto">
            {eventList.slice(0, 20).map((ev: any, i: number) => (
              <div key={i} className="text-[10.5px] font-mono text-zinc-400 px-2 py-1 rounded bg-white/[0.02]">
                {JSON.stringify(ev).slice(0, 200)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PluginsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-plugins"],
    queryFn: () => api.get<{ plugins: any[] }>("/api/admin/plugins"),
  });

  const plugins = data?.plugins ?? [];

  if (isLoading) return <SkeletonRows n={3} />;

  return (
    <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-5">
      <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Installed Plugins</div>
      {plugins.length === 0 ? (
        <EmptyState message="No plugins installed" sub="Plugins extend the orchestrator with new toolsets, models, and event handlers." />
      ) : (
        <div className="divide-y divide-white/[0.04]">
          {plugins.map((p, i) => (
            <div key={i} className="py-2.5 flex items-center gap-3">
              <Puzzle className="w-3.5 h-3.5 text-emerald-300" strokeWidth={1.5} />
              <span className="text-[12px] text-zinc-200 font-medium">{p.name ?? p}</span>
              {p.version && <span className="text-[10px] font-mono text-zinc-600">v{p.version}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CronTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-cron"],
    queryFn: () => api.get<{ jobs: any[] }>("/api/admin/cron"),
  });
  const jobs = data?.jobs ?? [];

  if (isLoading) return <SkeletonRows n={3} />;

  return (
    <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-5">
      <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Cron Jobs</div>
      {jobs.length === 0 ? (
        <EmptyState message="No cron jobs scheduled" sub="Schedule a recurring task from any agent via the cronjob tool." />
      ) : (
        <div className="divide-y divide-white/[0.04]">
          {jobs.map((j, i) => (
            <div key={i} className="py-2.5 flex items-center gap-3">
              <Clock className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
              <span className="text-[12px] text-zinc-200 font-medium">{j.name ?? j.id}</span>
              <span className="text-[10px] font-mono text-zinc-600">{j.schedule ?? j.cron ?? "—"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SwarmTab() {
  const { data: sub } = useQuery({
    queryKey: ["admin-swarm-active"],
    queryFn: () => api.get<any>("/api/ops/swarm/active"),
  });
  const { data: summary } = useQuery({
    queryKey: ["admin-swarm-summary"],
    queryFn: () => api.get<any>("/api/ops/swarm/summary"),
  });

  const subagents = sub?.subagents ?? [];
  const total = summary?.sessions_total ?? 0;
  const totalTokens = summary?.total_tokens ?? 0;
  const totalCost = summary?.total_cost ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-stretch border-y border-white/[0.06] divide-x divide-white/[0.06]">
        <StatStrip label="Sessions" value={total} />
        <StatStrip label="Subagents" value={subagents.length} />
        <StatStrip label="Tokens" value={totalTokens.toLocaleString()} />
        <StatStrip label="Total Cost" value={`$${totalCost.toFixed(4)}`} />
      </div>
      <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-5">
        <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Active Subagents</div>
        {subagents.length === 0 ? <EmptyState message="No subagents running" /> : (
          <div className="divide-y divide-white/[0.04]">
            {subagents.map((s: any, i: number) => (
              <div key={i} className="py-2.5 grid grid-cols-[140px_1fr_80px_80px] gap-3 items-center text-[11px]">
                <span className="font-mono text-zinc-500">{s.role ?? "—"}</span>
                <span className="text-zinc-300 truncate" title={s.goal}>{s.goal?.slice(0, 80) ?? "—"}</span>
                <span className="font-mono text-emerald-300">{s.status ?? "—"}</span>
                <span className="font-mono text-zinc-600 text-right">{s.tool_count ?? 0} tools</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatStrip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex-1 px-6 py-4 flex items-baseline gap-3">
      <span className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.14em]">{label}</span>
      <motion.span key={String(value)} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}
        className="text-2xl font-mono tabular-nums tracking-tight text-zinc-100">{value}</motion.span>
    </div>
  );
}

function SkeletonRows({ n }: { n: number }) {
  return (
    <div className="space-y-px">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="h-14 border-b border-white/[0.04] flex items-center gap-4 px-4">
          <div className="h-3 w-40 rounded shimmer-bg" />
          <div className="h-3 w-24 rounded shimmer-bg ml-auto" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ message, sub }: { message: string; sub?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={SPRING} className="py-8 text-center">
      <p className="text-sm text-zinc-500">{message}</p>
      {sub && <p className="text-xs text-zinc-700 mt-1.5 max-w-sm mx-auto">{sub}</p>}
    </motion.div>
  );
}

export default function AdminPage() {
  return (
    <Suspense fallback={    <div className="min-h-[100dvh] flex items-center justify-center bg-background"><div className="flex items-center gap-3 text-zinc-600"><Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} /><span className="text-sm">Loading admin...</span></div></div>}>
      <AdminPageInner />
    </Suspense>
  );
}
