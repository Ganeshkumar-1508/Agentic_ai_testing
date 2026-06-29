"use client";

import { motion } from "framer-motion";
import { Hash, AtSign, MessageSquare, Inbox, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface DigestConfig {
  id: string;
  platform: string;
  channel_id: string;
  schedule: string;
  enabled: boolean;
  created_at?: string;
}

interface DigestChannelsProps {
  configs: DigestConfig[];
}

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 110, damping: 22 } },
};

function platformIcon(platform: string) {
  const p = (platform || "").toLowerCase();
  if (p.includes("slack")) return <Hash className="w-3.5 h-3.5" strokeWidth={1.5} />;
  if (p.includes("email") || p.includes("smtp")) return <AtSign className="w-3.5 h-3.5" strokeWidth={1.5} />;
  return <MessageSquare className="w-3.5 h-3.5" strokeWidth={1.5} />;
}

function platformTone(platform: string) {
  const p = (platform || "").toLowerCase();
  if (p.includes("slack")) return { text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/15" };
  if (p.includes("email") || p.includes("smtp")) return { text: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/15" };
  return { text: "text-zinc-300", bg: "bg-white/[0.04]", border: "border-white/[0.06]" };
}

export function DigestChannels({ configs }: DigestChannelsProps) {
  const enabled = configs.filter((c) => c.enabled).length;

  return (
    <motion.section
      variants={item}
      className="rounded-[2rem] p-6 lg:p-7 card-wireframe"
    >
      <header className="flex items-end justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600 mb-1.5">
            Delivery
          </div>
          <h2 className="text-base font-medium text-zinc-100 tracking-tight">
            Where this digest goes
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-mono text-zinc-500">
            {enabled} active · {configs.length} configured
          </span>
          <a
            href="/settings?tab=digest"
            className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-[0.12em] px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
          >
            <Plus className="w-3 h-3" strokeWidth={2} />
            Add
          </a>
        </div>
      </header>

      {configs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="w-9 h-9 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-zinc-700 mb-3">
            <Inbox className="w-4 h-4" strokeWidth={1.5} />
          </div>
          <p className="text-xs text-zinc-400">No delivery channels yet.</p>
          <p className="text-[10px] text-zinc-700 mt-1 font-mono max-w-xs">
            Add Slack, Teams, or email to receive this brief every morning.
          </p>
        </div>
      ) : (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {configs.map((cfg) => {
            const tone = platformTone(cfg.platform);
            return (
              <motion.li
                key={cfg.id}
                variants={item}
                className="flex items-center gap-3 p-3 rounded-xl border border-white/[0.04] bg-white/[0.015] row-hover"
              >
                <span
                  className={cn(
                    "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center border",
                    tone.bg,
                    tone.border,
                    tone.text
                  )}
                >
                  {platformIcon(cfg.platform)}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-200 capitalize">{cfg.platform}</span>
                    {!cfg.enabled && (
                      <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-700 px-1.5 py-0.5 rounded bg-white/[0.03] border border-white/[0.04]">
                        paused
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] font-mono text-zinc-500 truncate mt-0.5">
                    {cfg.channel_id}
                  </div>
                </div>
                <code className="hidden sm:inline-block text-[10px] font-mono text-zinc-600 px-2 py-1 rounded bg-white/[0.02] border border-white/[0.04]">
                  {cfg.schedule}
                </code>
              </motion.li>
            );
          })}
        </ul>
      )}
    </motion.section>
  );
}
