"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import {
  Activity,
  Bot,
  Cpu,
  GitBranch,
  Network,
  Radio,
  Sparkles,
  Users,
  Wrench,
  Zap,
} from "lucide-react";
import { ActivityFeed } from "@/components/activity/ActivityFeed";
import { ObservabilityPanels } from "@/components/activity/ObservabilityPanels";
import { PageShell } from "@/components/shared/PageShell";
import { useActivityFeed, ACTIVITY_EVENT_TYPES } from "@/lib/hooks/use-activity-feed";

type SessionSummary = {
  count: number;
  lastTs: string;
  lastTool?: string;
  lastEvent?: string;
};

const spring: Parameters<typeof motion.div>[0]["transition"] = {
  type: "spring",
  stiffness: 120,
  damping: 18,
};

const enter: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { ...spring, delay: 0.02 * i },
  }),
};

const containerV: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.04, delayChildren: 0.05 } },
};

function StreamDot({ live }: { live: boolean }) {
  return (
    <span className="relative inline-flex w-2 h-2">
      {live && (
        <motion.span
          aria-hidden
          className="absolute inset-0 rounded-full bg-emerald-400/40"
          animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
          transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
      <span
        className={
          "relative inline-block w-2 h-2 rounded-full " +
          (live ? "bg-emerald-400" : "bg-zinc-700")
        }
      />
    </span>
  );
}

function StatBlock({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: number;
  hint?: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  tone?: "default" | "accent";
}) {
  return (
    <div className="flex flex-col gap-1 px-5 py-4">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-zinc-500">
        <Icon className="w-3 h-3" strokeWidth={1.5} />
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span
          className={
            "text-[28px] font-semibold tabular-nums leading-none tracking-tight font-mono " +
            (tone === "accent" ? "text-emerald-300" : "text-zinc-100")
          }
        >
          {value}
        </span>
        {hint && (
          <span className="text-[10px] text-zinc-600 font-mono">{hint}</span>
        )}
      </div>
    </div>
  );
}

function ActiveSessionTile({
  sid,
  info,
  index,
}: {
  sid: string;
  info: SessionSummary;
  index: number;
}) {
  const age = useMemo(() => {
    if (!info.lastTs) return "—";
    const ms = Date.now() - new Date(info.lastTs).getTime();
    if (ms < 1000) return "now";
    if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
    return `${Math.round(ms / 60_000)}m ago`;
  }, [info.lastTs]);

  return (
    <motion.a
      custom={index}
      variants={enter}
      href={`/activity?session=${encodeURIComponent(sid)}`}
      className="group relative block px-4 py-3.5 hover:bg-white/[0.025] active:translate-y-[1px] transition-[background,transform] duration-200 ease-[cubic-bezier(0.16,1,0.3,1)]"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-mono text-zinc-300 truncate max-w-[150px]" title={sid}>
          {sid.length > 22 ? sid.slice(0, 22) + "…" : sid}
        </span>
        <span className="text-[9px] font-mono text-zinc-600 tabular-nums">{info.count} ev</span>
      </div>
      <div className="flex items-center gap-1.5 min-h-[14px]">
        {info.lastTool ? (
          <>
            <Wrench className="w-2.5 h-2.5 text-emerald-400/80 shrink-0" strokeWidth={1.5} />
            <span className="text-[10.5px] text-zinc-300 font-mono truncate">{info.lastTool}</span>
          </>
        ) : (
          <span className="text-[10.5px] text-zinc-600 font-mono">idle</span>
        )}
      </div>
      <div className="flex items-center gap-1.5 mt-1 text-[9px] text-zinc-600 font-mono">
        <StreamDot live={!!info.lastTool} />
        <span>{age}</span>
      </div>
    </motion.a>
  );
}

function ActivityPageInner() {
  const params = useSearchParams();
  const sessionId = params.get("session") || "";
  const isGlobal = !sessionId;
  const statsFeed = useActivityFeed({ sessionId: sessionId || null });

  const counts = statsFeed.counts;
  const total = statsFeed.total;
  const stateOpen = statsFeed.state === "open";

  const sessionGroups = useMemo(() => {
    return statsFeed.events.reduce<Record<string, SessionSummary>>((acc, e) => {
      const sid = String((e.payload as Record<string, unknown>)?.session_id || "_anon");
      if (!acc[sid]) acc[sid] = { count: 0, lastTs: e.timestamp };
      acc[sid].count += 1;
      if (!acc[sid].lastTs || e.timestamp > acc[sid].lastTs) {
        acc[sid].lastTs = e.timestamp;
        acc[sid].lastEvent = e.type;
      }
      if (e.type === "ToolExecutionStarted" || e.type === "tool.execution.started") {
        acc[sid].lastTool = String((e.payload as Record<string, unknown>)?.tool_name || "");
      }
      return acc;
    }, {});
  }, [statsFeed.events]);

  const activeSessions = useMemo(
    () =>
      Object.entries(sessionGroups)
        .filter(([sid]) => sid !== "_anon")
        .sort(([, a], [, b]) => (a.lastTs < b.lastTs ? 1 : -1))
        .slice(0, 12),
    [sessionGroups],
  );

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  const headline = (
    <div className="border-y border-white/[0.06] divide-x divide-white/[0.06] grid grid-cols-2 md:grid-cols-4">
      <StatBlock
        label="Live"
        value={total}
        hint={stateOpen ? "streaming" : "idle"}
        icon={Radio}
        tone="accent"
      />
      <StatBlock
        label="Tool calls"
        value={counts["tool.execution.started"] ?? 0}
        hint="in flight"
        icon={Wrench}
      />
      <StatBlock
        label="LLM calls"
        value={counts["llmcall.started"] ?? 0}
        hint="rounds"
        icon={Cpu}
      />
      <StatBlock
        label="Subagents"
        value={counts["subagent.spawned"] ?? 0}
        hint={`${counts["subagent.completed"] ?? 0} done`}
        icon={Users}
      />
    </div>
  );

  const secondary = (
    <div className="border-b border-white/[0.06] divide-x divide-white/[0.06] grid grid-cols-2 md:grid-cols-4">
      <StatBlock
        label="Boards"
        value={
          (counts["board.completed"] ?? 0) + (counts["board.failed"] ?? 0)
        }
        hint="kanban"
        icon={GitBranch}
      />
      <StatBlock
        label="KG refresh"
        value={
          (counts["kg.refreshed"] ?? 0) + (counts["kg.refreshed.failed"] ?? 0)
        }
        hint="codegraph"
        icon={Network}
      />
      <StatBlock
        label="Teams"
        value={
          (counts["team.created"] ?? 0) + (counts["team.dissolved"] ?? 0)
        }
        hint="C02"
        icon={Users}
      />
      <StatBlock
        label="Event types"
        value={ACTIVITY_EVENT_TYPES.length}
        hint="catalog"
        icon={Sparkles}
      />
    </div>
  );

  return (
    <PageShell
      title={isGlobal ? "Activity · Global Live" : "Activity"}
      description={
        isGlobal
          ? "Every event from every active session, in one stream. Subagent tool calls flow up to the orchestrator via the Hermes child-progress pattern."
          : "Live stream of events for this session: subagent heartbeats, tool calls, kanban transitions, KG refreshes."
      }
      sections={[
        {
          title: "Headline",
          description: isGlobal
            ? "Tallies across all active sessions since this page opened."
            : "Tallies for the active session since this page opened.",
          children: (
            <div className="overflow-hidden">
              {headline}
              {secondary}
            </div>
          ),
        },
        ...(isGlobal
          ? [
              {
                title: "Active sessions",
                description: "Click a session to follow its events in the feed below.",
                children: (
                  <motion.div
                    variants={containerV}
                    initial="hidden"
                    animate="show"
                    className="border border-white/[0.06] divide-y divide-white/[0.06] grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
                  >
                    <AnimatePresence>
                      {activeSessions.length === 0 ? (
                        <motion.div
                          key="empty"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="col-span-full px-5 py-10 flex flex-col items-center gap-2 text-center"
                        >
                          <div className="w-9 h-9 rounded-full border border-dashed border-white/10 flex items-center justify-center">
                            <Activity className="w-4 h-4 text-zinc-700" strokeWidth={1.5} />
                          </div>
                          <p className="text-[12px] text-zinc-500">
                            Waiting for the first event.
                          </p>
                          <p className="text-[10.5px] text-zinc-700 font-mono max-w-[280px]">
                            Submit a job via{" "}
                            <code className="text-emerald-400/80">POST /api/jobs</code>{" "}
                            to see orchestrator + subagent streams merge here.
                          </p>
                        </motion.div>
                      ) : (
                        activeSessions.map(([sid, info], i) => (
                          <ActiveSessionTile
                            key={sid}
                            sid={sid}
                            info={info}
                            index={i}
                          />
                        ))
                      )}
                    </AnimatePresence>
                  </motion.div>
                ),
              },
            ]
          : []),
        {
          title: "Observability",
          description: isGlobal
            ? "Tool health, cost burn, and error categories across the last 60 minutes. Polled every 10s; the live feed above handles sub-second updates."
            : "Tool health, cost burn, and error categories for this session over the last 60 minutes.",
          children: <ObservabilityPanels sessionId={sessionId || undefined} sinceMinutes={60} />,
        },
        {
          title: "Live feed",
          description: "Filter chips, pause, and clear. Connection badge top-right.",
          children: (
            <div className={hydrated ? "opacity-100" : "opacity-0"}>
              <ActivityFeed sessionId={sessionId} />
            </div>
          ),
        },
      ]}
    />
  );
}

export default function ActivityPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[60vh] flex items-center justify-center">
          <div className="flex items-center gap-2 text-zinc-600 text-[12px] font-mono">
            <Zap className="w-3.5 h-3.5 animate-pulse text-emerald-400/70" strokeWidth={1.5} />
            <span>Connecting…</span>
          </div>
        </div>
      }
    >
      <ActivityPageInner />
    </Suspense>
  );
}
