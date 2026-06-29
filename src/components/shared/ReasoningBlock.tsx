"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, ChevronDown, ChevronRight, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface ReasoningBlockProps {
  content: string;
  isStreaming?: boolean;
  startedAt?: number;
  completedAt?: number;
  defaultOpen?: boolean;
}

export function ReasoningBlock({ content, isStreaming, startedAt, completedAt, defaultOpen }: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen ?? true);

  if (!content && !isStreaming) return null;

  const duration = completedAt && startedAt ? Math.round((completedAt - startedAt) / 1000) : null;
  const elapsed = duration !== null
    ? duration >= 60 ? `${Math.floor(duration / 60)}m ${duration % 60}s` : `${duration}s`
    : null;

  return (
    <div className="border border-amber-500/10 rounded-3xl overflow-hidden mb-3 bg-amber-500/[0.02]">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-4 py-2.5 text-xs text-zinc-500 hover:text-zinc-300 bg-amber-500/[0.03] hover:bg-amber-500/[0.06] transition-colors"
      >
        {open ? <ChevronDown size={12} strokeWidth={1.5} /> : <ChevronRight size={12} strokeWidth={1.5} />}
        <Brain size={12} strokeWidth={1.5} className="text-amber-400/60" />
        <span className="font-medium text-zinc-400">Thinking</span>
          {isStreaming && (
          <span className="flex gap-0.5 ml-1">
            <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" style={{ animationDelay: "0ms" }} />
            <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" style={{ animationDelay: "150ms" }} />
            <span className="w-1 h-1 rounded-full bg-amber-400 animate-pulse" style={{ animationDelay: "300ms" }} />
          </span>
        )}
        <span className="ml-auto flex items-center gap-3">
          {elapsed && (
            <span className="flex items-center gap-1 text-[10px] text-zinc-600 font-mono">
              <Clock size={10} strokeWidth={1.5} />
              {elapsed}
            </span>
          )}
          <span className="text-zinc-700 text-[10px] font-mono">{content.length} chars</span>
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className={cn(
              "px-4 py-3 text-xs text-amber-400/70 italic leading-relaxed border-t border-amber-500/10 font-mono whitespace-pre-wrap",
              isStreaming && "bg-amber-500/[0.02]"
            )}>
              {content}
              {isStreaming && (
                <span className="inline-block w-1.5 h-3.5 bg-amber-400/60 ml-0.5 animate-pulse align-text-bottom" />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
