"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, Play, FlaskConical, Settings, BookOpen, BarChart3, GitBranch, Activity } from "lucide-react";

interface DashboardEmptyStateProps {
  hasOverview: boolean;
}

const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 120, damping: 22 } },
};

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

const QUICK_LINKS = [
  { href: "/pipeline",     label: "Pipeline",     icon: GitBranch },
  { href: "/test-cases",   label: "Test Cases",   icon: FlaskConical },
  { href: "/requirements", label: "Requirements", icon: BookOpen },
  { href: "/settings",     label: "Settings",     icon: Settings },
];

export function DashboardEmptyState({ hasOverview }: DashboardEmptyStateProps) {
  return (
    <motion.section
      initial="hidden"
      animate="show"
      variants={stagger}
      className="relative overflow-hidden rounded-[2.5rem] border border-white/[0.06] bg-gradient-to-b from-white/[0.02] to-transparent"
    >
      <div className="pointer-events-none absolute inset-0">
        <div
          className="absolute -top-32 left-1/2 -translate-x-1/2 w-[800px] h-[400px] rounded-full blur-[120px] opacity-50"
          style={{ background: "radial-gradient(circle, rgba(52,211,153,0.10), transparent 70%)" }}
        />
      </div>

      <div className="relative px-8 py-16 sm:py-20 flex flex-col items-center text-center">
        <motion.div
          variants={item}
          className="w-16 h-16 rounded-2xl border border-white/[0.08] bg-white/[0.02] flex items-center justify-center mb-6"
        >
          <BarChart3 className="w-7 h-7 text-zinc-500" strokeWidth={1.25} />
        </motion.div>

        <motion.h2
          variants={item}
           className="text-2xl md:text-3xl font-medium tracking-tighter text-zinc-100 leading-none"
        >
          No data yet
        </motion.h2>

        <motion.p
          variants={item}
          className="text-sm text-zinc-500 mt-3 max-w-md leading-relaxed"
        >
          {hasOverview
            ? "Your dashboard is connected but no tests have run yet. Start a pipeline to populate the KPIs, charts, and failure signals."
            : "Connect a repository and run your first pipeline. Test results, coverage, and quality trends will populate here."}
        </motion.p>

        <motion.div variants={item} className="mt-8 flex items-center gap-3">
          <Link
            href="/pipeline"
            className="group inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full bg-emerald-500 text-zinc-950 font-semibold text-sm shadow-[0_8px_32px_-8px_rgba(52,211,153,0.45)] hover:shadow-[0_12px_40px_-8px_rgba(52,211,153,0.55)] hover:scale-[1.02] active:scale-[0.98] transition-all"
          >
            <Play className="w-4 h-4" strokeWidth={2.5} fill="currentColor" />
            Start your first pipeline
            <span className="ml-1 w-5 h-5 rounded-full bg-zinc-950/15 flex items-center justify-center transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5">
              <ArrowUpRight className="w-3 h-3" strokeWidth={2.5} />
            </span>
          </Link>
        </motion.div>

        <motion.div
          variants={item}
          className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-3"
        >
          {QUICK_LINKS.map((q) => {
            const Icon = q.icon;
            return (
              <Link
                key={q.href}
                href={q.href}
                className="flex items-center gap-1.5 text-[12px] text-zinc-500 hover:text-emerald-400 transition-colors"
              >
                <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
                {q.label}
              </Link>
            );
          })}
        </motion.div>

        <motion.div
          variants={item}
          className="mt-10 flex items-center gap-2 text-[10px] font-mono text-zinc-700"
        >
          <Activity className="w-3 h-3" strokeWidth={1.5} />
          <span>Last backend sync: just now</span>
        </motion.div>
      </div>
    </motion.section>
  );
}
