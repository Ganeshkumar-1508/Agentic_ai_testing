"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Sparkles, ChevronDown } from "lucide-react";

interface AISummaryBannerProps {
  summary?: string;
  loading?: boolean;
}

export function AISummaryBanner({ summary, loading }: AISummaryBannerProps) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-3xl p-4">
        <div className="w-full h-4 rounded-full shimmer-bg" />
      </div>
    );
  }

  if (!summary) return null;

  const isLong = summary.length > 120;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.4, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-emerald-500/5 border border-emerald-500/10 rounded-3xl p-4"
    >
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
          <Sparkles className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-medium text-emerald-400/80 uppercase tracking-wider mb-1">
            AI Summary
          </div>
          <p className={cn(
            "text-sm text-neutral-300 leading-relaxed",
            !expanded && isLong && "line-clamp-2"
          )}>
            {summary}
          </p>
          {isLong && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 mt-1 text-xs text-emerald-400/60 hover:text-emerald-400 transition-colors"
            >
              <ChevronDown className={cn("w-3 h-3 transition-transform", expanded && "rotate-180")} strokeWidth={1.5} />
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
