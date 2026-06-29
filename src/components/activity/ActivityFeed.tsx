"use client";

/**
 * ActivityFeed — scrollable live activity feed with filter chips
 * and a sticky footer showing the SSE connection state.
 *
 * Used by:
 *   - `/activity` (global feed, all event types, all sessions)
 *   - `/jobs/[spec_id]` (per-job feed, filtered by spec_id)
 *
 * The parent owns the session_id + filter set. This component
 * just renders the list, header, and connection-state pill.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Pause,
  Play,
  Trash2,
  ChevronDown,
  Wifi,
  WifiOff,
  Filter,
  Circle,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ActivityItem } from "@/components/activity/ActivityItem";
import {
  ACTIVITY_EVENT_TYPES,
  useActivityFeed,
  type ActivityEventType,
} from "@/lib/hooks/use-activity-feed";

interface ActivityFeedProps {
  sessionId: string | null;
  /** Optional: filter to events whose payload contains this value. */
  payloadMatch?: { key: string; value: unknown };
  /** Title shown above the feed. Default: "Activity". */
  title?: string;
  /** Default filter set. If empty, all event types are shown. */
  initialFilters?: ReadonlyArray<ActivityEventType>;
  /** Hide filter chips (used by per-job detail). */
  hideFilters?: boolean;
  /** Max events to keep in the ring buffer. Default 500. */
  maxEvents?: number;
  /** Cap visible events (UI perf). Default 200. */
  maxVisible?: number;
  /** Empty state message. */
  emptyMessage?: string;
  /** Compact height — used inside the Job Detail page. */
  compact?: boolean;
}

const STATE_BADGE: Record<
  ReturnType<typeof useActivityFeed>["state"],
  { label: string; tone: "ok" | "warn" | "danger" | "muted" }
> = {
  idle: { label: "Idle", tone: "muted" },
  connecting: { label: "Connecting…", tone: "warn" },
  open: { label: "Live", tone: "ok" },
  reconnecting: { label: "Reconnecting…", tone: "warn" },
  closed: { label: "Closed", tone: "muted" },
  error: { label: "Offline", tone: "danger" },
};

const TONE_PILL: Record<"ok" | "warn" | "danger" | "muted", string> = {
  ok: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  warn: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  danger: "bg-red-500/10 text-red-400 border-red-500/20",
  muted: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
};

export function ActivityFeed({
  sessionId,
  payloadMatch,
  title = "Activity",
  initialFilters,
  hideFilters,
  maxEvents,
  maxVisible = 200,
  emptyMessage = "No activity yet. Start a job to see events.",
  compact,
}: ActivityFeedProps) {
  const [activeFilters, setActiveFilters] = useState<ReadonlySet<string>>(() => {
    if (initialFilters && initialFilters.length > 0) return new Set(initialFilters);
    return new Set(ACTIVITY_EVENT_TYPES);
  });
  const [autoScroll, setAutoScroll] = useState(true);

  const feed = useActivityFeed({
    sessionId,
    filters: activeFilters,
    maxEvents,
  });

  // Apply payload-match (per-job filtering) on the client. The
  // backend's EventSourceSink doesn't know about spec-scoped
  // filtering, so we do it here. Cheap O(N) on a ring buffer.
  const visibleEvents = useMemo(() => {
    let events = feed.events;
    if (payloadMatch) {
      events = events.filter((e) => e.payload?.[payloadMatch.key] === payloadMatch.value);
    }
    if (events.length > maxVisible) {
      return events.slice(events.length - maxVisible);
    }
    return events;
  }, [feed.events, payloadMatch, maxVisible]);

  const scrollerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!autoScroll) return;
    if (!visibleEvents.length) return;
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [visibleEvents, autoScroll]);

  const toggleFilter = (type: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  const stateBadge = STATE_BADGE[feed.state];

  return (
    <div
      className={cn(
        "rounded-[2rem] p-6 flex flex-col gap-4",
        compact ? "min-h-[280px]" : "min-h-[480px]",
      )}
      style={{ background: "#0e0e18" }}
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-semibold text-neutral-200 tracking-tight">{title}</h2>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full border tabular-nums",
              TONE_PILL[stateBadge.tone],
            )}
          >
            {feed.state === "open" ? (
              <Wifi className="w-2.5 h-2.5" strokeWidth={2} />
            ) : feed.state === "error" || feed.state === "closed" ? (
              <WifiOff className="w-2.5 h-2.5" strokeWidth={2} />
            ) : (
              <RefreshCw className="w-2.5 h-2.5 animate-spin" strokeWidth={2} />
            )}
            {stateBadge.label}
          </span>
          <span className="text-[10px] font-mono text-zinc-600 tabular-nums">
            {feed.total} total
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <FeedButton
            onClick={feed.togglePause}
            title={feed.paused ? "Resume" : "Pause"}
            active={feed.paused}
          >
            {feed.paused ? <Play className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Pause className="w-3.5 h-3.5" strokeWidth={1.5} />}
          </FeedButton>
          <FeedButton onClick={() => setAutoScroll((s) => !s)} title="Auto-scroll" active={autoScroll}>
            <ChevronDown className={cn("w-3.5 h-3.5", autoScroll && "text-emerald-400")} strokeWidth={1.5} />
          </FeedButton>
          <FeedButton onClick={feed.clear} title="Clear" disabled={feed.total === 0}>
            <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
          </FeedButton>
        </div>
      </div>

      {!hideFilters && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <Filter className="w-3 h-3 text-zinc-600 shrink-0" strokeWidth={1.5} />
          {ACTIVITY_EVENT_TYPES.map((type) => {
            const active = activeFilters.has(type);
            const count = feed.counts[type] ?? 0;
            return (
              <button
                key={type}
                onClick={() => toggleFilter(type)}
                className={cn(
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono tabular-nums border transition-colors",
                  active
                    ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                    : "bg-white/[0.02] border-white/[0.05] text-zinc-500 hover:text-zinc-300",
                )}
              >
                <Circle
                  className={cn(
                    "w-1.5 h-1.5",
                    active ? "fill-emerald-400 text-emerald-400" : "fill-zinc-600 text-zinc-600",
                  )}
                  strokeWidth={2}
                />
                {type}
                {count > 0 && <span className="text-[9px] text-zinc-600">·{count}</span>}
              </button>
            );
          })}
        </div>
      )}

      <div
        ref={scrollerRef}
        className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1"
        style={{ scrollbarGutter: "stable" }}
      >
        <AnimatePresence mode="popLayout" initial={false}>
          {visibleEvents.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm text-zinc-500 text-center py-12"
            >
              {emptyMessage}
            </motion.div>
          ) : (
            visibleEvents.map((e, i) => (
              <ActivityItem
                key={e.id}
                event={e}
                highlight={i === visibleEvents.length - 1}
              />
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function FeedButton({
  onClick,
  title,
  active,
  disabled,
  children,
}: {
  onClick: () => void;
  title: string;
  active?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={cn(
        "p-1.5 rounded-lg transition-colors",
        active
          ? "bg-emerald-500/10 text-emerald-400"
          : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.04]",
        disabled && "opacity-30 cursor-not-allowed hover:bg-transparent",
      )}
    >
      {children}
    </button>
  );
}
