"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { ArrowUpRight, Calendar, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface DigestConfig {
  id: string;
  platform: string;
  channel_id: string;
  schedule: string;
  enabled: boolean;
  created_at?: string;
}

interface DigestHeroProps {
  overview: any;
  loading: boolean;
  yesterday: Date | null;
  digestConfigs?: DigestConfig[];
}

function useLiveClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function greetingFor(hour: number): string {
  if (hour < 5) return "Late night";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 21) return "Good evening";
  return "Burning the midnight oil";
}

function statusOf(overview: any): { label: string; tone: "good" | "warn" | "bad" } {
  if (!overview) return { label: "Loading", tone: "good" };
  const failed = overview.tests_24h?.failed ?? 0;
  const prs = overview.prs_needing_attention ?? 0;
  if (failed > 0 || prs > 0) return { label: "Needs attention", tone: "warn" };
  return { label: "All green", tone: "good" };
}

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

export function DigestHero({ overview, loading, yesterday, digestConfigs = [] }: DigestHeroProps) {
  const now = useLiveClock();
  const hour = now?.getHours() ?? 9;
  const status = statusOf(overview);

  const dateLabel = now
    ? now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
    : "—";
  const periodLabel = yesterday
    ? `${yesterday.toLocaleDateString("en-US", { month: "short", day: "numeric" })} → ${
        now ? now.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "—"
      }`
    : now ? now.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "—";

  const primaryChannel = digestConfigs.find((c) => c.enabled) ?? digestConfigs[0];
  const channelTarget = primaryChannel
    ? `${primaryChannel.platform} · ${primaryChannel.channel_id}`
    : "No channel configured";
  const channelSchedule = primaryChannel?.schedule ?? "—";

  return (
    <motion.section
      variants={item}
      className="relative grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-8 lg:gap-12 items-end"
    >
      <div className="space-y-5">
        <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-600">
          <Calendar className="w-3 h-3" strokeWidth={1.5} />
          <span>{dateLabel}</span>
          <span className="text-zinc-800">·</span>
          <span>24h window · {periodLabel}</span>
        </div>

        <div className="space-y-1.5">
          <h1 className="text-[2.75rem] md:text-[3.5rem] font-semibold tracking-tighter leading-[0.95] text-zinc-50">
            {greetingFor(hour)}.
          </h1>
          <p className="text-sm text-zinc-500 max-w-[52ch] leading-relaxed">
            Your agents worked through the night on{" "}
            <span className="text-zinc-300">{overview?.pipeline_runs_24h ?? 0} pipeline runs</span>,
            authored <span className="text-zinc-300">{overview?.tests_24h?.passed ?? 0} passing tests</span>,
            and flagged{" "}
            <span className="text-zinc-300">{overview?.recent_failures?.length ?? 0} failures</span>{" "}
            that need a human eye.
          </p>
        </div>
      </div>

      <div className="lg:justify-self-end w-full lg:w-auto">
        <div className="flex items-center gap-3 lg:flex-col lg:items-end">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06] text-[11px] font-mono">
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                status.tone === "good" && "bg-emerald-400",
                status.tone === "warn" && "bg-amber-400 animate-pulse",
                status.tone === "bad" && "bg-red-400 animate-pulse"
              )}
            />
            <span className="text-zinc-300">{loading ? "Checking" : status.label}</span>
          </div>

          <a
            href="/settings?tab=digest"
            className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-[0.15em] text-zinc-500 hover:text-emerald-400 transition-colors group"
          >
            <Sparkles className="w-3 h-3" strokeWidth={1.5} />
            <span>Schedule</span>
            <ArrowUpRight className="w-3 h-3 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" strokeWidth={1.5} />
          </a>
        </div>

        <div className="hidden lg:block mt-6 max-w-xs text-right">
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-700 mb-1">Sent to</div>
          <div className="text-xs text-zinc-400 leading-relaxed">
            {channelTarget}
            <span className="text-zinc-700"> · </span>
            <span className="text-emerald-400 font-mono">{channelSchedule}</span>
          </div>
        </div>
      </div>
    </motion.section>
  );
}
