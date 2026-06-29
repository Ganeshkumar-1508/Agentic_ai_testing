"use client";

import { motion } from "framer-motion";
import { Bot, GitBranch, CheckCircle2, XCircle, Loader2, Pause, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

interface Session {
  session_id: string;
  status: string;
  goal?: string;
  cost?: number;
  source?: string;
}

interface DigestTimelineProps {
  sessions: Session[];
}

const item = {
  hidden: { opacity: 0, x: -8 },
  show: { opacity: 1, x: 0, transition: { type: "spring" as const, stiffness: 130, damping: 24 } },
};

function statusGlyph(status: string) {
  if (status === "running") return <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />;
  if (status === "completed") return <CheckCircle2 className="w-3 h-3" strokeWidth={2} />;
  if (status === "failed") return <XCircle className="w-3 h-3" strokeWidth={2} />;
  return <Pause className="w-3 h-3" strokeWidth={2} />;
}

function statusTone(status: string) {
  if (status === "running") return { dot: "bg-emerald-400", text: "text-emerald-400", bg: "bg-emerald-500/10" };
  if (status === "completed") return { dot: "bg-zinc-500", text: "text-zinc-400", bg: "bg-white/[0.04]" };
  if (status === "failed") return { dot: "bg-red-400", text: "text-red-400", bg: "bg-red-500/10" };
  return { dot: "bg-zinc-700", text: "text-zinc-500", bg: "bg-white/[0.03]" };
}

function sourceIcon(source?: string) {
  const s = (source || "").toLowerCase();
  if (s.includes("github") || s.includes("pr")) return <GitBranch className="w-3 h-3" strokeWidth={1.5} />;
  return <Bot className="w-3 h-3" strokeWidth={1.5} />;
}

export function DigestTimeline({ sessions }: DigestTimelineProps) {
  const items = Array.isArray(sessions) ? sessions.slice(0, 14) : [];

  return (
    <motion.section
      variants={item}
      className="rounded-[2rem] p-6 lg:p-7 card-wireframe"
    >
      <header className="flex items-end justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600 mb-1.5">
            Overnight activity
          </div>
          <h2 className="text-base font-medium text-zinc-100 tracking-tight">What your agents did</h2>
        </div>
        <div className="text-[10px] font-mono text-zinc-700">
          {items.filter((s) => s.status === "running").length} live
        </div>
      </header>

      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="w-9 h-9 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-zinc-700 mb-3">
            <Inbox className="w-4 h-4" strokeWidth={1.5} />
          </div>
          <p className="text-xs text-zinc-500">No agent activity in the last 24h.</p>
          <p className="text-[10px] text-zinc-700 mt-1 font-mono">Trigger a pipeline to populate this feed.</p>
        </div>
      ) : (
        <ol className="relative space-y-0.5">
          <span className="absolute left-[7px] top-2 bottom-2 w-px bg-gradient-to-b from-white/[0.08] via-white/[0.04] to-transparent" aria-hidden />
          {items.map((s, i) => {
            const tone = statusTone(s.status);
            return (
              <motion.li
                key={s.session_id || i}
                variants={item}
                className="group relative flex items-center gap-3 py-2 pl-1 pr-2 rounded-lg row-hover"
              >
                <span
                  className={cn(
                    "relative z-10 w-3.5 h-3.5 rounded-full flex items-center justify-center shrink-0",
                    tone.bg,
                    tone.text,
                    s.status === "running" && "ring-2 ring-emerald-500/20"
                  )}
                >
                  {statusGlyph(s.status)}
                </span>

                <div className="flex-1 min-w-0 flex items-center gap-2">
                  <span className="text-zinc-500 shrink-0">{sourceIcon(s.source)}</span>
                  <span className="text-xs text-zinc-300 truncate font-mono">
                    {s.goal?.slice(0, 60) || "Untitled session"}
                  </span>
                </div>

                <span
                  className={cn(
                    "shrink-0 text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-full",
                    tone.bg,
                    tone.text
                  )}
                >
                  {s.status}
                </span>

                {(s.cost ?? 0) > 0 && (
                  <span className="shrink-0 text-[10px] font-mono text-zinc-600 tabular-nums w-12 text-right">
                    ${s.cost!.toFixed(3)}
                  </span>
                )}
              </motion.li>
            );
          })}
        </ol>
      )}
    </motion.section>
  );
}
