"use client";

import { cn } from "@/lib/utils";

interface FlowEvent {
  id: string; type: string; raw_type: string;
  agent_id: string; parent_id: string | null; depth: number;
  duration_ms: number | null; token_count: number | null;
  tool_name: string | null; content_preview: string | null;
  created_at: string | null; payload: any;
}

interface Props {
  event: FlowEvent;
  isSelected: boolean;
  onSelect: (event: FlowEvent) => void;
  dotColor: string;
  typeColor: string;
}

function fmtDur(ms: number | null): string {
  if (ms === null || ms === undefined) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleTimeString("en-US", { hour12: false }); }
  catch { return ""; }
}

export function EventRow({ event, isSelected, onSelect, dotColor, typeColor }: Props) {
  const isNested = event.depth > 0;

  return (
    <button
      onClick={() => onSelect(event)}
      className={cn(
        "w-full flex gap-3 px-3 py-2 rounded-[1rem] transition-all text-left active:scale-[0.99] border",
        isSelected
          ? "bg-emerald-500/6 border-emerald-500/12"
          : "bg-transparent border-transparent hover:bg-white/[0.02]",
        isNested && "ml-6 border-l border-zinc-500/15 pl-5"
      )}
    >
      {/* Gutter: dot + time */}
      <div className="flex flex-col items-center gap-1 w-8 shrink-0 pt-0.5">
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotColor)} />
        <span className="text-[9px] font-mono text-neutral-600 tabular-nums leading-none">
          {fmtTime(event.created_at)}
        </span>
      </div>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn("text-[11px] font-medium", typeColor)}>
            {event.type}
          </span>
          {event.tool_name && (
            <span className="text-[10px] text-neutral-500 font-mono">
              {event.tool_name}
            </span>
          )}
          <span className="ml-auto flex items-center gap-2 text-[9px] font-mono tabular-nums text-neutral-600">
            {event.duration_ms !== null && (
              <span>{fmtDur(event.duration_ms)}</span>
            )}
            {event.token_count !== null && event.token_count > 0 && (
              <span>{event.token_count} tok</span>
            )}
            {event.depth > 0 && (
              <span className="text-zinc-400/60">d{event.depth}</span>
            )}
          </span>
        </div>
        {event.content_preview && (
          <p className="text-[11px] text-neutral-500 truncate mt-0.5 leading-snug">
            {event.content_preview}
          </p>
        )}
      </div>
    </button>
  );
}
