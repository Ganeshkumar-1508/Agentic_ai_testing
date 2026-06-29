"use client";

import { motion } from "framer-motion";
import { AlertOctagon, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

interface Failure {
  test_name: string;
  error?: string;
  created_at?: string;
}

interface DigestFailuresProps {
  failures: Failure[];
  loading: boolean;
}

const item = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 130, damping: 24 } },
};

function formatError(err: string | undefined): string {
  if (!err) return "no error trace";
  return typeof err === "string" && err.length > 140 ? err.slice(0, 140) + "…" : err;
}

export function DigestFailures({ failures, loading }: DigestFailuresProps) {
  const items = Array.isArray(failures) ? failures.slice(0, 6) : [];

  return (
    <motion.section
      variants={item}
      className="rounded-[2rem] p-6 lg:p-7 card-wireframe h-full"
    >
      <header className="flex items-end justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600 mb-1.5">
            Failure detail
          </div>
          <h2 className="text-base font-medium text-zinc-100 tracking-tight">Top failing tests</h2>
        </div>
        <a
          href="/history?status=failed"
          className="text-[10px] font-mono uppercase tracking-[0.12em] text-zinc-600 hover:text-zinc-300 transition-colors"
        >
          View all
        </a>
      </header>

      {loading ? (
        <ul className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <li key={i} className="space-y-1.5 p-2">
              <div className="h-3 w-3/4 rounded shimmer-bg" />
              <div className="h-2.5 w-1/2 rounded shimmer-bg" />
            </li>
          ))}
        </ul>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/15 flex items-center justify-center text-emerald-400 mb-3">
            <Inbox className="w-4 h-4" strokeWidth={1.5} />
          </div>
          <p className="text-xs text-zinc-400">Zero failures. Beautiful.</p>
          <p className="text-[10px] text-zinc-700 mt-1 font-mono">last_failed_at: null</p>
        </div>
      ) : (
        <ul className="space-y-0.5">
          {items.map((f, i) => (
            <motion.li
              key={i}
              variants={item}
              className="group flex gap-3 p-2.5 -mx-2.5 rounded-lg row-hover"
            >
              <span className="shrink-0 w-7 h-7 rounded-lg bg-red-500/8 border border-red-500/15 flex items-center justify-center text-red-400 mt-0.5">
                <AlertOctagon className="w-3.5 h-3.5" strokeWidth={1.5} />
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-mono text-zinc-200 truncate">{f.test_name}</div>
                <div
                  className={cn(
                    "text-[11px] mt-1 font-mono leading-relaxed",
                    "text-zinc-500 line-clamp-2"
                  )}
                >
                  {formatError(f.error)}
                </div>
              </div>
            </motion.li>
          ))}
        </ul>
      )}
    </motion.section>
  );
}
