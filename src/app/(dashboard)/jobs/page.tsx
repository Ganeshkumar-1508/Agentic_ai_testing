"use client";

/**
 * /jobs — list JobSpecs submitted via the C08 canonical surface.
 *
 * Reads from `GET /api/jobs?session_id=...` (per C08 Q10,
 * `list_by_session` is the primary entry point).
 *
 * The default session_id is the active chat session, so the
 * page shows the jobs the user has kicked off in the chat. A
 * session_id search box lets the user pull jobs from any
 * session.
 */

import { Suspense, useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Briefcase,
  Search,
  RefreshCw,
  ExternalLink,
  CircleDot,
  GitBranch,
} from "lucide-react";
import { api } from "@/lib/api/api-client";
import type { JobSummary, JobStatus } from "@/lib/types/jobs";
import { PageShell } from "@/components/shared/PageShell";
import { KpiRow } from "@/components/shared/KpiRow";
import { cn } from "@/lib/utils";

const STATUS_PILL: Record<JobStatus, string> = {
  queued: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  submitted: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  running: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border-red-500/20",
  cancelled: "bg-red-500/10 text-red-400 border-red-500/20",
  paused: "bg-amber-500/10 text-amber-400 border-amber-500/20",
};

const TIER_LABEL: Record<number, string> = {
  1: "Autonomous",
  2: "Supervised",
  3: "Human",
};

function JobsPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [sessionInput, setSessionInput] = useState(params.get("session") || "global");
  const [activeSession, setActiveSession] = useState(params.get("session") || "global");
  const [statusFilter, setStatusFilter] = useState<JobStatus | "all">("all");

  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["jobs", activeSession],
    queryFn: () =>
      api.get<{ items: JobSummary[]; total: number; limit: number; offset: number }>(
        `/api/jobs`,
        { session_id: activeSession },
      ),
    refetchInterval: 5000,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  const filtered = useMemo(() => {
    if (!items) return [];
    if (statusFilter === "all") return items;
    return items.filter((j) => j.status === statusFilter);
  }, [items, statusFilter]);

  const counts = useMemo(() => {
    const c: Record<JobStatus, number> = {
      queued: 0,
      submitted: 0,
      running: 0,
      completed: 0,
      failed: 0,
      cancelled: 0,
      paused: 0,
    };
    if (!items) return c;
    for (const j of items) {
      if (j.status in c) c[j.status as JobStatus] += 1;
    }
    return c;
  }, [items]);

  const totalCost = useMemo(() => {
    if (!items) return 0;
    return items.reduce((acc, j) => acc + (j.latest_run_cost_usd ?? 0), 0);
  }, [items]);

  return (
    <PageShell
      title="Jobs"
      description="All jobs submitted through the C08 canonical JobSpec surface. Click any job to see its full lifecycle — status, comments, output, and the live activity feed for that job."
      actions={
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-zinc-800/50 bg-zinc-900/60">
            <Search className="w-3 h-3 text-zinc-600" strokeWidth={1.5} />
            <input
              type="text"
              value={sessionInput}
              onChange={(e) => setSessionInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setActiveSession(sessionInput);
              }}
              placeholder="session_id"
              className="bg-transparent text-[12px] text-zinc-200 placeholder-zinc-600 outline-none w-44 font-mono"
            />
          </div>
          <button
            onClick={() => refetch()}
            disabled={isRefetching}
            className="p-1.5 rounded-lg border border-zinc-800/50 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", isRefetching && "animate-spin")}
              strokeWidth={1.5}
            />
          </button>
        </div>
      }
      sections={[
        {
          title: "Headline",
          description: "Tallies for the active session.",
          children: (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            >
              <KpiRow
                items={[
                  { label: "Total", value: total, sub: `session ${truncate(activeSession, 16)}` },
                  {
                    label: "Running",
                    value: counts.running + counts.submitted,
                    sub: "active",
                    pulse: counts.running + counts.submitted > 0,
                  },
                  { label: "Failed", value: counts.failed + counts.cancelled, sub: "needs review" },
                  { label: "Cost", value: `$${totalCost.toFixed(2)}`, sub: "lifetime" },
                ]}
              />
            </motion.div>
          ),
        },
        {
          title: "Filter",
          description: "Status pills narrow the table.",
          actions: (
            <div className="flex items-center gap-1.5">
              {(["all", "running", "completed", "failed", "cancelled", "paused"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s as JobStatus | "all")}
                  className={cn(
                    "text-[10px] font-mono px-2 py-0.5 rounded-full border transition-colors",
                    statusFilter === s
                      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                      : "bg-white/[0.02] border-white/[0.05] text-zinc-500 hover:text-zinc-300",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          ),
          children: (
            <div
              className="rounded-[2rem] p-3"
              style={{ background: "#0e0e18" }}
            >
              {isLoading ? (
                <div className="text-sm text-zinc-500 text-center py-8">Loading jobs…</div>
              ) : filtered.length === 0 ? (
                <div className="text-sm text-zinc-500 text-center py-12">
                  {items.length === 0
                    ? "No jobs in this session yet. Use the chat's submit_job tool to create one."
                    : "No jobs match the current filter."}
                </div>
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {filtered.map((j) => (
                    <button
                      key={j.spec_id}
                      onClick={() => router.push(`/jobs/${j.spec_id}`)}
                      className="w-full text-left flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-white/[0.03] transition-colors group"
                    >
                      <CircleDot
                        className={cn(
                          "w-3.5 h-3.5 shrink-0",
                          j.status === "running" || j.status === "submitted"
                            ? "text-emerald-400 animate-pulse"
                            : j.status === "failed" || j.status === "cancelled"
                            ? "text-red-400"
                            : j.status === "paused"
                            ? "text-amber-400"
                            : "text-zinc-600",
                        )}
                        strokeWidth={1.5}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[12px] font-mono text-zinc-300 truncate">
                            {truncate(j.prompt, 100)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-zinc-600">
                          <span className="px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400">
                            T{j.tier} {TIER_LABEL[j.tier]}
                          </span>
                          {j.repo_url && (
                            <span className="inline-flex items-center gap-1">
                              <GitBranch className="w-2.5 h-2.5" strokeWidth={2} />
                              {truncate(j.repo_url, 36)}
                            </span>
                          )}
                          <span>{timeAgo(j.created_at)}</span>
                          {j.latest_run_duration_s != null && (
                            <span>· {formatDuration(j.latest_run_duration_s)}</span>
                          )}
                          {j.latest_run_cost_usd != null && (
                            <span>· ${j.latest_run_cost_usd.toFixed(3)}</span>
                          )}
                        </div>
                      </div>
                      <span
                        className={cn(
                          "shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded border",
                          STATUS_PILL[j.status as JobStatus] || STATUS_PILL.queued,
                        )}
                      >
                        {j.status}
                      </span>
                      <ExternalLink
                        className="w-3 h-3 text-zinc-700 group-hover:text-zinc-400 transition-colors"
                        strokeWidth={1.5}
                      />
                    </button>
                  ))}
                </div>
              )}
            </div>
          ),
        },
      ]}
    />
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={<div className="text-zinc-500">Loading…</div>}>
      <JobsPageInner />
    </Suspense>
  );
}

function truncate(s: string, n: number): string {
  if (!s) return "";
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function formatDuration(raw: number | null | undefined): string {
  if (raw == null) return "—";
  if (raw < 60) return `${raw.toFixed(1)}s`;
  const m = Math.floor(raw / 60);
  const s = Math.floor(raw % 60);
  if (m < 60) return `${m}m${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h${m % 60}m`;
}

function timeAgo(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return iso;
  const sec = Math.floor((Date.now() - d) / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}
