"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface FlowEvent {
  id: string; type: string; raw_type: string;
  agent_id: string; parent_id: string | null; depth: number;
  duration_ms: number | null; token_count: number | null;
  tool_name: string | null; content_preview: string | null;
  created_at: string | null; payload: any;
}

interface Props {
  event: FlowEvent | null;
  onClose: () => void;
}

function fmtDur(ms: number | null): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function syntaxHighlight(obj: any): string {
  const json = JSON.stringify(obj, null, 2);
  if (!json) return "null";
  return json.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"([^"]+)":/g, '<span class="text-blue-400">"$1"</span>:')
    .replace(/: "([^"]+)"/g, (_, m) => `: <span class="text-emerald-400">"${m}"</span>`)
    .replace(/: (\d+\.?\d*)/g, (_, m) => `: <span class="text-amber-400">${m}</span>`)
    .replace(/: (true|false)/g, (_, m) => `: <span class="text-zinc-400">${m}</span>`)
    .replace(/: (null)/g, (_, m) => `: <span class="text-neutral-600">${m}</span>`);
}

const TYPE_BADGES: Record<string, string> = {
  tool_call: "text-blue-400 bg-blue-500/10 border-blue-500/15",
  tool_result: "text-emerald-400 bg-emerald-500/10 border-emerald-500/15",
  reasoning: "text-amber-400 bg-amber-500/10 border-amber-500/15",
  error: "text-red-400 bg-red-500/10 border-red-500/15",
  delegate: "text-zinc-400 bg-zinc-500/10 border-zinc-500/15",
  llm: "text-zinc-400 bg-zinc-500/10 border-zinc-500/15",
  round: "text-zinc-400 bg-zinc-500/10 border-zinc-500/15",
  agent: "text-zinc-400 bg-zinc-500/10 border-zinc-500/15",
};

export function DetailDrawer({ event, onClose }: Props) {
  return (
    <AnimatePresence>
      {event ? (
        <motion.div
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 380, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 80, damping: 24 }}
          className="overflow-hidden flex-shrink-0 border-l border-white/[0.06]"
        >
          <div className="w-[380px] h-full flex flex-col bg-white/[0.015]">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.04]">
              <h4 className="text-sm font-medium text-neutral-200">Event Detail</h4>
              <button
                onClick={onClose}
                className="w-6 h-6 rounded-lg bg-white/[0.04] flex items-center justify-center hover:bg-white/[0.06] transition-colors active:scale-[0.95]"
              >
                <X className="w-3 h-3 text-neutral-500" strokeWidth={1.5} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5" style={{ scrollbarGutter: "stable" }}>
              {/* Metrics grid */}
              <div className="grid grid-cols-2 gap-2">
                <MetricCard label="Duration" value={fmtDur(event.duration_ms)} />
                <MetricCard label="Tokens" value={event.token_count !== null ? String(event.token_count) : "—"} />
                <MetricCard label="Depth" value={String(event.depth)} />
                <MetricCard label="Agent" value={event.agent_id.slice(0, 8) + "..."} mono />
              </div>

              {/* Event type badge */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full border font-medium",
                  TYPE_BADGES[event.type] ?? "text-neutral-400 bg-white/[0.04]"
                )}>
                  {event.type}
                </span>
                {event.tool_name && (
                  <span className="text-[10px] font-mono text-neutral-500 bg-white/[0.03] px-1.5 py-0.5 rounded-md">
                    {event.tool_name}
                  </span>
                )}
                {event.depth > 0 && (
                  <span className="text-[10px] text-zinc-400/60 bg-zinc-500/8 px-1.5 py-0.5 rounded-md">
                    subagent
                  </span>
                )}
              </div>

              {/* Fields */}
              <Field label="Event Type" value={event.raw_type} />
              <Field label="Timestamp" value={event.created_at ?? "—"} mono />
              <Field label="Agent ID" value={event.agent_id || "—"} mono small />
              {event.parent_id && (
                <Field label="Parent Event" value={event.parent_id.slice(0, 12) + "..."} mono small />
              )}
              {event.content_preview && (
                <Field label="Preview" value={event.content_preview} />
              )}

              {/* Full JSON payload */}
              <div>
                <span className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider block mb-2">
                  Full Payload
                </span>
                <div className="bg-card border border-white/[0.06] rounded-3xl p-4 overflow-x-auto">
                  <pre
                    className="text-[11px] font-mono leading-relaxed whitespace-pre-wrap break-all"
                    dangerouslySetInnerHTML={{ __html: syntaxHighlight(event.payload) }}
                  />
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function MetricCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-3xl px-4 py-3">
      <div className="text-[9px] font-semibold text-neutral-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={cn("text-sm font-medium text-neutral-200", mono && "font-mono tabular-nums")}>
        {value}
      </div>
    </div>
  );
}

function Field({ label, value, mono, small }: { label: string; value: string; mono?: boolean; small?: boolean }) {
  return (
    <div>
      <div className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={cn(
        "text-neutral-300",
        mono ? "font-mono" : "font-sans",
        small ? "text-[11px]" : "text-sm"
      )}>
        {value}
      </div>
    </div>
  );
}
