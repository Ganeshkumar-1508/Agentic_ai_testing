"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatsCard } from "@/components/shared/StatsCard";
import { PulseDot } from "@/components/ai-ops/PulseDot";
import { BookOpen, Sparkles, Archive, RotateCw, Pin, History, Activity } from "lucide-react";
import { api } from "@/lib/api/api-client";

type CuratorStatus = {
  total_skills: number;
  active: number;
  stale: number;
  archived: number;
  agent_created: number;
  bundled: number;
  total_uses: number;
  pinned_count: number;
  last_curated_at: string | null;
  interval_hours: number;
  stale_after_days: number;
  archive_after_days: number;
  next_run_hours: number;
  state: Record<string, unknown>;
};

type SkillInfo = {
  name: string;
  description: string;
  version: string;
  path: string;
  requires_toolsets: string[];
};

type UsageRecord = {
  use_count: number;
  view_count: number;
  patch_count: number;
  last_used_at: string | null;
  created_by?: string;
  pinned?: boolean;
  state?: string;
};

function FilterButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs rounded-md transition-colors ${active ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}
    >
      {label}
    </button>
  );
}

function stateDot(state: string | undefined) {
  switch (state) {
    case "active": return "bg-emerald-400";
    case "stale": return "bg-amber-400";
    case "archived": return "bg-zinc-600";
    default: return "bg-emerald-400";
  }
}

export default function SkillsPage() {
  const [status, setStatus] = useState<CuratorStatus | null>(null);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [usage, setUsage] = useState<Record<string, UsageRecord>>({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "agent" | "bundled">("all");
  const [running, setRunning] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [statusData, skillsData, usageData] = await Promise.all([
        api.get<CuratorStatus>("/api/ops/skills/curator-status"),
        api.get<{ skills?: SkillInfo[] }>("/api/skills"),
        api.get<{ usage?: Record<string, UsageRecord> }>("/api/ops/skills/usage"),
      ]);
      setStatus(statusData);
      setSkills(skillsData?.skills ?? []);
      setUsage(usageData?.usage ?? {});
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const runCurator = async () => {
    setRunning(true);
    try {
      await api.post("/api/ops/skills/curator-run");
      await fetchData();
    } catch {
    } finally {
      setRunning(false);
    }
  };

  const filteredSkills = skills.filter((s) => {
    const u = usage[s.name];
    const createdBy = u?.created_by ?? "bundled";
    if (filter === "agent") return createdBy === "agent";
    if (filter === "bundled") return createdBy !== "agent";
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard icon={<BookOpen size={16} />} label="Total Skills" value={status?.total_skills ?? 0} sub={`${status?.agent_created ?? 0} agent-created, ${status?.bundled ?? 0} bundled`} delay={0.05} />
        <StatsCard icon={<Sparkles size={16} />} label="Active" value={status?.active ?? 0} sub={`Used within ${status?.stale_after_days ?? 30}d`} delay={0.1} />
        <StatsCard icon={<History size={16} />} label="Stale" value={status?.stale ?? 0} sub={`${status?.archive_after_days ?? 90}d until archive`} delay={0.15} />
        <StatsCard icon={<Archive size={16} />} label="Archived" value={status?.archived ?? 0} sub="moved to .archive/" delay={0.2} />
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6">
            {[0, 1].map((i) => <div key={i} className="h-64 rounded-2xl shimmer-bg border border-zinc-800/30" />)}
          </motion.div>
        ) : (
          <motion.div key="content" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6">
            {/* Skill Library */}
            <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-sm font-medium text-zinc-100">Skill Library</h2>
                <div className="flex gap-1 bg-zinc-800 rounded-lg p-0.5">
                  <FilterButton label="All" active={filter === "all"} onClick={() => setFilter("all")} />
                  <FilterButton label="Agent" active={filter === "agent"} onClick={() => setFilter("agent")} />
                  <FilterButton label="Bundled" active={filter === "bundled"} onClick={() => setFilter("bundled")} />
                </div>
              </div>

              <div className="space-y-0.5 max-h-[500px] overflow-y-auto pr-1 -mr-1">
                {filteredSkills.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-32 text-zinc-600">
                    <BookOpen size={24} className="opacity-20 mb-2" strokeWidth={1} />
                    <p className="text-xs">No skills in this category</p>
                  </div>
                ) : (
                  filteredSkills.map((s) => {
                    const u = usage[s.name] ?? {};
                    const state = u.state ?? "active";
                    const daysSince = u.last_used_at ? Math.floor((Date.now() - new Date(u.last_used_at).getTime()) / 86400000) : null;
                    return (
                      <div key={s.name} className={`flex items-center gap-3 p-2.5 rounded-xl hover:bg-white/[0.02] transition-colors ${state === "archived" ? "opacity-60" : ""}`}>
                        <span className={`w-2 h-2 rounded-full shrink-0 ${stateDot(state)} ${state === "stale" ? "animate-pulse" : ""}`} />
                        <span className="text-sm font-medium text-zinc-100 w-32 truncate shrink-0">{s.name}</span>
                        <span className="text-[10px] text-zinc-500 font-mono w-12 shrink-0">v{s.version || "1"}</span>
                        <span className="flex-1 min-w-0">
                          <span className={`text-xs truncate block ${state === "stale" ? "text-amber-400/80" : "text-zinc-500"}`}>
                            {state === "stale" && daysSince !== null
                              ? `Unused for ${daysSince}d — ${Math.max(0, (status?.archive_after_days ?? 90) - daysSince)}d until archive`
                              : s.description || "—"}
                          </span>
                        </span>
                        <span className="text-[9px] text-zinc-600 font-mono w-10 text-right shrink-0">{u.use_count ?? 0} use{(u.use_count ?? 0) !== 1 ? "s" : ""}</span>
                        {daysSince !== null && <span className="text-[9px] text-zinc-600 w-10 text-right shrink-0">{daysSince}d</span>}
                        {u.pinned && <Pin size={10} className="text-amber-400 shrink-0" strokeWidth={1.5} />}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Curator Timeline + Controls */}
            <div className="space-y-4">
              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <h2 className="text-sm font-medium text-zinc-100 mb-4">Curator Status</h2>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02]">
                    <span className="text-xs text-zinc-400">Last curated</span>
                    <span className="text-xs text-zinc-100 font-mono">
                      {status?.last_curated_at
                        ? new Date(status.last_curated_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit" })
                        : "Never"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02]">
                    <span className="text-xs text-zinc-400">Next run</span>
                    <span className="text-xs text-zinc-100 font-mono">
                      ~{Math.round(status?.next_run_hours ?? 0)}h
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02]">
                    <span className="text-xs text-zinc-400">Interval</span>
                    <span className="text-xs text-zinc-500 font-mono">{status?.interval_hours ?? 168}h ({Math.round((status?.interval_hours ?? 168) / 24)}d)</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02]">
                    <span className="text-xs text-zinc-400">Pinned skills</span>
                    <span className="text-xs text-zinc-100 font-mono">{status?.pinned_count ?? 0}</span>
                  </div>
                </div>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <h2 className="text-sm font-medium text-zinc-100 mb-4">Controls</h2>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={runCurator}
                    disabled={running}
                    className="px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
                  >
                    <RotateCw size={10} strokeWidth={1.5} className={running ? "animate-spin" : ""} />
                    {running ? "Running..." : "Run Curator"}
                  </button>
                  <button className="px-3 py-1.5 text-xs rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors inline-flex items-center gap-1.5">
                    <Pin size={10} strokeWidth={1.5} /> Pin
                  </button>
                  <button className="px-3 py-1.5 text-xs rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors inline-flex items-center gap-1.5">
                    <Archive size={10} strokeWidth={1.5} /> Restore
                  </button>
                </div>

                <div className="mt-4 p-3 rounded-xl bg-zinc-900/50 border border-zinc-800">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-400">Self-improvement</span>
                    <span className="text-emerald-400/80 font-mono">Active (5m throttle)</span>
                  </div>
                  <div className="flex items-center justify-between text-xs mt-2">
                    <span className="text-zinc-400">Total uses</span>
                    <span className="text-zinc-500 font-mono">{status?.total_uses ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs mt-2">
                    <span className="text-zinc-400">Agent-created</span>
                    <span className="text-zinc-500 font-mono">{status?.agent_created ?? 0}</span>
                  </div>
                </div>
              </div>

              {/* Self-Improvement Activity */}
              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-7 h-7 rounded-lg bg-zinc-500/10 flex items-center justify-center text-zinc-400">
                    <Activity size={12} strokeWidth={1.5} />
                  </div>
                  <div>
                    <h2 className="text-sm font-medium text-zinc-100">Self-Improvement</h2>
                    <span className="text-[10px] text-zinc-500">Background review runs after sessions (5-min throttle)</span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-2.5 rounded-xl bg-white/[0.02]">
                    <span className="text-[10px] text-zinc-400">Skills created</span>
                    <span className="text-sm text-zinc-100 block font-mono mt-0.5">{status?.agent_created ?? 0}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/[0.02]">
                    <span className="text-[10px] text-zinc-400">Total uses</span>
                    <span className="text-sm text-zinc-100 block font-mono mt-0.5">{status?.total_uses ?? 0}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/[0.02]">
                    <span className="text-[10px] text-zinc-400">Pinned</span>
                    <span className="text-sm text-zinc-100 block font-mono mt-0.5">{status?.pinned_count ?? 0}</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
