"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface DigestInsightsProps {
  overview: any;
  loading: boolean;
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 110, damping: 22 } },
};

type Tone = "good" | "warn" | "bad" | "neutral";
type Direction = "up" | "down" | "flat";

function dirIcon(d: Direction) {
  if (d === "up") return <TrendingUp className="w-3 h-3" strokeWidth={2} />;
  if (d === "down") return <TrendingDown className="w-3 h-3" strokeWidth={2} />;
  return <Minus className="w-3 h-3" strokeWidth={2} />;
}

function toneClasses(tone: Tone) {
  return {
    good: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
    warn: "text-amber-400 border-amber-500/20 bg-amber-500/5",
    bad: "text-red-400 border-red-500/20 bg-red-500/5",
    neutral: "text-zinc-400 border-white/[0.06] bg-white/[0.02]",
  }[tone];
}

interface Insight {
  title: string;
  detail: string;
  delta: string;
  direction: Direction;
  tone: Tone;
}

function buildInsights(overview: any): Insight[] {
  if (!overview) return [];
  const tests = overview.tests_24h ?? { total: 0, passed: 0, failed: 0 };
  const passRate = overview.pass_rate_24h ?? 0;
  const failed = tests.failed;
  const flaky = overview.flaky_tests ?? 0;
  const prs = overview.prs_needing_attention ?? 0;

  const out: Insight[] = [];

  if (passRate >= 95) {
    out.push({
      title: "Suite health is strong",
      detail: `Pass rate held above 95% across ${tests.total} executions. Your regression net is tight.`,
      delta: `${passRate.toFixed(1)}%`,
      direction: "up",
      tone: "good",
    });
  } else if (passRate >= 80) {
    out.push({
      title: "Pass rate within healthy band",
      detail: `Some tests regressed overnight — review the failure detail panel before merging the morning PRs.`,
      delta: `${passRate.toFixed(1)}%`,
      direction: "flat",
      tone: "neutral",
    });
  } else {
    out.push({
      title: "Pass rate below threshold",
      detail: `${failed} failures across ${tests.total} tests. Consider pausing merges until triaged.`,
      delta: `${passRate.toFixed(1)}%`,
      direction: "down",
      tone: "bad",
    });
  }

  if (flaky > 5) {
    out.push({
      title: "Flakiness elevated",
      detail: `${flaky} tests exceeded the flakiness threshold. Likely candidates: timing assertions and locator drift.`,
      delta: `${flaky} flaky`,
      direction: "up",
      tone: "warn",
    });
  } else {
    out.push({
      title: "Flakiness quiet",
      detail: `No new flaky patterns detected. Self-healing absorbed the noise without quarantine.`,
      delta: `${flaky} flaky`,
      direction: "down",
      tone: "good",
    });
  }

  if (prs > 0) {
    out.push({
      title: `${prs} PR${prs === 1 ? "" : "s"} waiting for tests`,
      detail: "These have been idle since the last green run. Trigger a re-run or assign an owner.",
      delta: `${prs} open`,
      direction: "flat",
      tone: "warn",
    });
  } else {
    out.push({
      title: "PR queue is clear",
      detail: "All open PRs have a green test attached. No idle branches in the tracker.",
      delta: "0 idle",
      direction: "down",
      tone: "good",
    });
  }

  return out.slice(0, 4);
}

export function DigestInsights({ overview, loading }: DigestInsightsProps) {
  const insights = buildInsights(overview);

  return (
    <motion.section
      variants={item}
      className="rounded-[2rem] p-6 lg:p-7 card-wireframe h-full relative overflow-hidden"
    >
      <div
        className="pointer-events-none absolute -top-24 -right-24 w-64 h-64 rounded-full bg-emerald-500/[0.04] blur-3xl"
        aria-hidden
      />

      <header className="flex items-end justify-between mb-5 relative">
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600 mb-1.5">
            <Sparkles className="w-3 h-3" strokeWidth={1.5} />
            <span>What we noticed</span>
          </div>
          <h2 className="text-base font-medium text-zinc-100 tracking-tight">Pattern insights</h2>
        </div>
        <span className="text-[10px] font-mono text-zinc-700">heuristic · v0.4</span>
      </header>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="p-4 rounded-xl border border-white/[0.04] space-y-2">
              <div className="h-3 w-1/3 rounded shimmer-bg" />
              <div className="h-2.5 w-2/3 rounded shimmer-bg" />
            </div>
          ))}
        </div>
      ) : (
        <ul className="space-y-2.5 relative">
          {insights.map((ins, i) => (
            <motion.li
              key={i}
              variants={item}
              className={cn(
                "p-4 rounded-xl border group transition-colors",
                toneClasses(ins.tone)
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-zinc-100">{ins.title}</div>
                  <p className="text-[11px] text-zinc-400 mt-1.5 leading-relaxed">
                    {ins.detail}
                  </p>
                </div>
                <span
                  className={cn(
                    "shrink-0 flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded-full border",
                    toneClasses(ins.tone)
                  )}
                >
                  {dirIcon(ins.direction)}
                  {ins.delta}
                </span>
              </div>
            </motion.li>
          ))}
        </ul>
      )}
    </motion.section>
  );
}
