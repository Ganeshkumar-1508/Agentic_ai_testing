"use client";

import { memo, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Radio, Trash2, TriangleAlert, Wifi, WifiOff } from "lucide-react";

import { useSessionEvents, type SessionEvent, type SessionEventsState } from "@/lib/hooks/use-session-events";
import { cn } from "@/lib/utils";

/** Default set of event types surfaced in the live activity feed. */
const DEFAULT_EVENT_TYPES = [
  "agent.started",
  "agent.completed",
  "round.started",
  "round.completed",
  "llmcall.completed",
  "ToolExecutionStarted",
  "ToolExecutionCompleted",
  "tool:pending_approval",
  "approval:required",
  "reflexion:injected",
] as const;

export interface LiveEventStreamProps {
  sessionId: string;
  /** Override the default event-type filter. */
  eventTypes?: readonly string[];
  /** Maximum events to render.  Defaults to 100. */
  maxEvents?: number;
  /** Optional className for the outer wrapper. */
  className?: string;
}

// ------------------------------------------------------------------
// Pure helpers
// ------------------------------------------------------------------

function formatTime(ts: number): string {
  // Date is forgiving; ts may be ms (Python time.time()*1000) or seconds.
  const ms = ts > 1e12 ? ts : ts * 1000;
  try {
    return new Date(ms).toISOString().slice(11, 19);
  } catch {
    return String(ts);
  }
}

function shortData(evt: SessionEvent): string {
  const d = evt.data ?? {};
  const tool = (d.tool_name as string | undefined) ?? (d.tool as string | undefined) ?? (d.toolName as string | undefined);
  const preview =
    (d.preview as string | undefined) ??
    (d.input_preview as string | undefined) ??
    (d.text as string | undefined) ??
    (d.value as string | undefined);
  if (tool && preview) return `${tool}: ${preview.slice(0, 80)}`;
  if (tool) return tool;
  if (preview) return preview.slice(0, 100);
  const keys = Object.keys(d);
  return keys.length ? `{${keys.slice(0, 4).join(", ")}}` : "";
}

// ------------------------------------------------------------------
// Status pill — isolated Client Component to keep the perpetual
// pulse animation off the parent render tree (skill rule §5).
// ------------------------------------------------------------------

interface StatusDotProps {
  state: SessionEventsState;
  retryCount: number;
}

const StatusDot = memo(function StatusDot({ state, retryCount }: StatusDotProps) {
  const reduced = useReducedMotion();
  const pulse = state === "open" && !reduced;

  // Color encodes state; saturation kept < 80% via opacity-80.
  const tone =
    state === "open"
      ? "bg-emerald-400/80"
      : state === "reconnecting" || state === "connecting"
        ? "bg-amber-400/80"
        : state === "error"
          ? "bg-red-400/80"
          : "bg-zinc-500/60";

  return (
    <span
      className="relative inline-flex h-2 w-2 shrink-0 items-center justify-center"
      data-testid="live-event-stream-dot"
      data-state={state}
    >
      {pulse ? (
        <motion.span
          aria-hidden
          className={cn("absolute inset-0 rounded-full", tone)}
          animate={{ scale: [1, 2.2, 1], opacity: [0.7, 0, 0.7] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
        />
      ) : null}
      <span className={cn("relative inline-block h-2 w-2 rounded-full", tone)} />
    </span>
  );
});

interface StatusPillProps {
  state: SessionEventsState;
  retryCount: number;
  error: string | null;
}

const StatusPill = memo(function StatusPill({ state, retryCount, error }: StatusPillProps) {
  const { icon: Icon, label, tone } = useMemo(() => {
    if (state === "open") {
      return {
        icon: Wifi,
        label: retryCount > 0 ? `live · reconnected ×${retryCount}` : "live",
        tone: "text-emerald-300/90",
      };
    }
    if (state === "connecting") return { icon: Radio, label: "connecting", tone: "text-amber-300/90" };
    if (state === "reconnecting") return { icon: Radio, label: `reconnecting ×${retryCount}`, tone: "text-amber-300/90" };
    if (state === "error") return { icon: WifiOff, label: error ? `error · ${error}` : "error", tone: "text-red-300/90" };
    if (state === "closed") return { icon: WifiOff, label: "closed", tone: "text-zinc-400" };
    return { icon: Radio, label: "idle", tone: "text-zinc-500" };
  }, [state, retryCount, error]);

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/60 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em]",
        tone,
      )}
      data-testid="live-event-stream-state"
    >
      <StatusDot state={state} retryCount={retryCount} />
      <Icon className="h-3 w-3" aria-hidden />
      <span>{label}</span>
    </div>
  );
});

// ------------------------------------------------------------------
// Event row — memoized so a new event doesn't re-render the others
// ------------------------------------------------------------------

interface EventRowProps {
  event: SessionEvent;
  index: number;
}

const EventRow = memo(function EventRow({ event, index }: EventRowProps) {
  const reduced = useReducedMotion();
  return (
    <motion.li
      layout={!reduced}
      initial={reduced ? { opacity: 1 } : { opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, y: 4 }}
      transition={{ type: "spring", stiffness: 320, damping: 28, mass: 0.4 }}
      className="group flex items-center gap-3 px-3 py-1.5"
    >
      <span className="shrink-0 font-mono text-[10px] tabular-nums text-zinc-500">{formatTime(event.timestamp)}</span>
      <span className="shrink-0 font-mono text-xs text-zinc-200">{event.type}</span>
      <span className="truncate font-mono text-xs text-zinc-400 group-hover:text-zinc-300">{shortData(event)}</span>
    </motion.li>
  );
});

// ------------------------------------------------------------------
// Main component
// ------------------------------------------------------------------

/**
 * Minimal example consumer of {@link useSessionEvents}.
 *
 * Mounts at the bottom of an agent detail page to surface **live**
 * in-memory events as they happen — complementary to `useTraceEvents`
 * (which polls the persisted trace store).
 *
 * Design follows the `design-taste-frontend` skill:
 *   - One accent (emerald-400/80) for the "live" state, plus
 *     functional amber/red for transient states.
 *   - No card boxes; rows separated by `divide-y` lines.
 *   - Status pill carries a breathing dot when `state === "open"`
 *     (perpetual micro-interaction, isolated in a memo'd child).
 *   - New events slide in via Framer `layout` + `AnimatePresence`.
 *   - Honors `prefers-reduced-motion`.
 */
export function LiveEventStream({ sessionId, eventTypes = DEFAULT_EVENT_TYPES, maxEvents = 100, className }: LiveEventStreamProps) {
  const { events, state, retryCount, error, clear, retry } = useSessionEvents(sessionId, { eventTypes, maxEvents });
  const reduced = useReducedMotion();
  // Local "user cleared" flag — stop animating in fresh history until the next
  // genuinely-new event lands.  Cheap boolean state.
  const [userClearedAt, setUserClearedAt] = useState<number | null>(null);

  const onClear = () => {
    setUserClearedAt(Date.now());
    clear();
  };

  // Don't animate the "first paint" of historical events in batches of 30+
  // — that looks like a strobe.  Just snap them in.
  const isInitial = userClearedAt === null && events.length > 0 && state !== "open";

  return (
    <section
      className={cn(
        "flex flex-col overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-950/60 font-sans text-zinc-200",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]",
        className,
      )}
      data-testid="live-event-stream"
      data-state={state}
    >
      <header className="flex items-center justify-between gap-3 border-b border-zinc-800/80 px-3 py-2">
        <div className="flex items-center gap-3">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-zinc-400">live events</h3>
          <StatusPill state={state} retryCount={retryCount} error={error} />
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] tabular-nums text-zinc-500">
            {events.length}
            {maxEvents < Infinity ? `/${maxEvents}` : ""}
          </span>
          {state === "error" ? (
            <button
              type="button"
              onClick={retry}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border border-red-400/40 px-2 py-1",
                "font-mono text-[10px] uppercase tracking-wider text-red-300/90",
                "transition-all duration-200 ease-out hover:border-red-400/70 hover:bg-red-500/10 active:translate-y-px",
              )}
              data-testid="live-event-stream-retry"
            >
              <TriangleAlert className="h-3 w-3" aria-hidden /> retry
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClear}
            disabled={events.length === 0}
            className={cn(
              "inline-flex items-center gap-1 rounded-md border border-zinc-800 px-2 py-1",
                "font-mono text-[10px] uppercase tracking-wider text-zinc-400",
                "transition-all duration-200 ease-out",
                "hover:border-zinc-700 hover:bg-zinc-800/60 hover:text-zinc-200 active:translate-y-px",
                "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-zinc-800 disabled:hover:bg-transparent",
            )}
            data-testid="live-event-stream-clear"
            aria-label="Clear live events"
          >
            <Trash2 className="h-3 w-3" aria-hidden /> clear
          </button>
        </div>
      </header>

      <ol className="divide-y divide-zinc-800/60" data-testid="live-event-stream-list">
        {events.length === 0 ? (
          <li className="flex flex-col items-center justify-center gap-2 px-3 py-8 text-center">
            <Radio className="h-5 w-5 text-zinc-600" aria-hidden />
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-zinc-500">waiting for events</p>
            <p className="max-w-[28ch] text-[11px] leading-relaxed text-zinc-600">
              events from <span className="font-mono text-zinc-400">{sessionId}</span> will appear here in real time
            </p>
          </li>
        ) : (
          <AnimatePresence initial={false}>
            {events.map((evt, i) => (
              <EventRow key={`${evt.timestamp}-${i}-${evt.type}`} event={evt} index={i} />
            ))}
          </AnimatePresence>
        )}
      </ol>

      {isInitial ? null : null}
    </section>
  );
}
