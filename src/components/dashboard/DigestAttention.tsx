"use client";

import { motion } from "framer-motion";
import { GitPullRequest, ShieldAlert, AlertCircle, Inbox, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface DigestAttentionProps {
  overview: any;
  loading: boolean;
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 110, damping: 22 } },
};

function Pill({
  tone,
  children,
}: {
  tone: "good" | "warn" | "bad" | "neutral";
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.12em] px-2 py-1 rounded-full border",
        tone === "good" && "text-emerald-400 border-emerald-500/15 bg-emerald-500/5",
        tone === "warn" && "text-amber-400 border-amber-500/20 bg-amber-500/5",
        tone === "bad" && "text-red-400 border-red-500/20 bg-red-500/5",
        tone === "neutral" && "text-zinc-500 border-white/[0.06] bg-white/[0.02]"
      )}
    >
      {children}
    </span>
  );
}

export function DigestAttention({ overview, loading }: DigestAttentionProps) {
  const prs = overview?.prs_needing_attention ?? 0;
  const failed = overview?.tests_24h?.failed ?? 0;
  const flaky = overview?.flaky_tests ?? 0;
  const quarantined = overview?.quarantined_tests ?? 0;

  const hasAttention = prs > 0 || failed > 0 || flaky > 5;

  return (
    <motion.aside variants={item} className="space-y-4">
      <div className="rounded-[2rem] p-6 card-wireframe">
        <div className="flex items-center justify-between mb-4">
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600">Signal</div>
          <Pill tone={hasAttention ? "warn" : "good"}>
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                hasAttention ? "bg-amber-400 animate-pulse" : "bg-emerald-400"
              )}
            />
            {hasAttention ? "Action required" : "No blockers"}
          </Pill>
        </div>

        <h3 className="text-base font-medium text-zinc-100 tracking-tight">
          {hasAttention ? "Three things to look at" : "Quiet morning"}
        </h3>
        <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">
          {hasAttention
            ? "These are not fires — but a quick triage now will save a debugging session later."
            : "No PRs failing, no quarantine queue, no fresh regressions. Ship something."}
        </p>

        <ul className="mt-5 space-y-1.5">
          <li className="flex items-center gap-3 p-2.5 -mx-2.5 rounded-lg row-hover">
            <span className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-zinc-400 shrink-0">
              <GitPullRequest className="w-3.5 h-3.5" strokeWidth={1.5} />
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-zinc-300">Pull requests without a green test</div>
              <div className="text-[10px] font-mono text-zinc-600">pr_tracker · last_test_status</div>
            </div>
            <span
              className={cn(
                "text-sm font-mono font-semibold tabular-nums",
                prs > 0 ? "text-amber-400" : "text-zinc-600"
              )}
            >
              {loading ? "—" : prs}
            </span>
          </li>

          <li className="flex items-center gap-3 p-2.5 -mx-2.5 rounded-lg row-hover">
            <span className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-zinc-400 shrink-0">
              <AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-zinc-300">Test failures in the last 24h</div>
              <div className="text-[10px] font-mono text-zinc-600">test_results · status='failed'</div>
            </div>
            <span
              className={cn(
                "text-sm font-mono font-semibold tabular-nums",
                failed > 0 ? "text-amber-400" : "text-zinc-600"
              )}
            >
              {loading ? "—" : failed}
            </span>
          </li>

          <li className="flex items-center gap-3 p-2.5 -mx-2.5 rounded-lg row-hover">
            <span className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-zinc-400 shrink-0">
              <ShieldAlert className="w-3.5 h-3.5" strokeWidth={1.5} />
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-zinc-300">Flaky tests above threshold</div>
              <div className="text-[10px] font-mono text-zinc-600">
                flaky_tests · {quarantined} quarantined
              </div>
            </div>
            <span
              className={cn(
                "text-sm font-mono font-semibold tabular-nums",
                flaky > 5 ? "text-amber-400" : "text-zinc-600"
              )}
            >
              {loading ? "—" : flaky}
            </span>
          </li>
        </ul>
      </div>

      <div className="rounded-[2rem] p-6 card-wireframe">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600">Healing</span>
        </div>
        <p className="text-sm text-zinc-300 leading-relaxed">
          {quarantined > 0
            ? `${quarantined} tests auto-quarantined overnight while the team sleeps. Re-enable them after a passing run.`
            : "Self-healing patched 0 tests. No locator drift detected in your suite."}
        </p>
        <a
          href="/flaky-tests"
          className="mt-4 inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-[0.12em] text-zinc-500 hover:text-emerald-400 transition-colors"
        >
          Open quarantine queue
        </a>
      </div>
    </motion.aside>
  );
}
