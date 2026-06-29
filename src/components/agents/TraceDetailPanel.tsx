"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  Terminal, Brain, Bot, List, AlertCircle, MessageSquare,
  Copy, ExternalLink, RotateCw, Hash, Clock, DollarSign,
  FileText, Code2, CheckCircle, XCircle, Share2, Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TraceEvent } from "@/lib/hooks/use-trace-events";

interface TraceDetailPanelProps {
  event: TraceEvent | null;
  allEvents: TraceEvent[];
  onClose: () => void;
  className?: string;
}

interface DetailTab {
  id: string;
  label: string;
  icon: typeof FileText;
}

const tabs: DetailTab[] = [
  { id: "input", label: "Input", icon: FileText },
  { id: "output", label: "Output", icon: Code2 },
  { id: "meta", label: "Meta", icon: Hash },
  { id: "raw", label: "Raw", icon: Terminal },
];

function getEventColor(eventType: string): string {
  if (eventType.startsWith("agent:")) return "text-emerald-400";
  if (eventType.startsWith("round:")) return "text-neutral-400";
  if (eventType.startsWith("llm:")) return "text-zinc-400";
  if (eventType.startsWith("tool:")) return "text-amber-400";
  if (eventType === "reasoning") return "text-blue-400";
  return "text-neutral-500";
}

function getEventBg(eventType: string): string {
  if (eventType.startsWith("agent:")) return "bg-emerald-500/10";
  if (eventType.startsWith("round:")) return "bg-white/[0.03]";
  if (eventType.startsWith("llm:")) return "bg-zinc-500/10";
  if (eventType.startsWith("tool:")) return "bg-amber-500/10";
  if (eventType === "reasoning") return "bg-blue-500/10";
  return "bg-white/[0.02]";
}

function getEventIcon(eventType: string) {
  if (eventType.startsWith("agent:")) return Bot;
  if (eventType.startsWith("round:")) return List;
  if (eventType.startsWith("llm:")) return Brain;
  if (eventType.startsWith("tool:")) return Terminal;
  if (eventType === "reasoning") return MessageSquare;
  return Terminal;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function getDuration(event: TraceEvent, allEvents: TraceEvent[]): number | null {
  if (event.eventType.endsWith(":end") || event.eventType === "tool:error") return null;
  const baseType = event.eventType.replace(/:start$/, ":end");
  const end = allEvents.find(
    (e) => e.eventType === baseType && e.parentId === event.parentId,
  );
  if (!end) return null;
  return new Date(end.createdAt).getTime() - new Date(event.createdAt).getTime();
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-[11px] text-neutral-500">{label}</span>
      <span className={cn("text-[11px] text-neutral-300 text-right max-w-[60%] truncate", mono && "font-mono tabular-nums")}>
        {value}
      </span>
    </div>
  );
}

export function TraceDetailPanel({ event, allEvents, onClose, className }: TraceDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<string>("output");

  if (!event) {
    return (
      <div className={cn("border border-white/[0.06] rounded-3xl bg-surface p-6", className)}>
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Terminal className="w-8 h-8 text-neutral-600 mb-2" strokeWidth={1.2} />
          <p className="text-xs text-neutral-500">Select a trace event to inspect</p>
        </div>
      </div>
    );
  }

  const Icon = getEventIcon(event.eventType);
  const color = getEventColor(event.eventType);
  const bg = getEventBg(event.eventType);
  const d = event.eventData as Record<string, any>;
  const duration = getDuration(event, allEvents);

  const snippet = useMemo(() => {
    return (JSON.stringify(d, null, 2) || "").slice(0, 3000);
  }, [d]);

  const metaItems = useMemo(() => {
    const items: Array<{ label: string; value: string; mono?: boolean }> = [];
    items.push({ label: "Event Type", value: event.eventType, mono: true });

    if (d.model) items.push({ label: "Model", value: d.model as string });
    if (d.provider) items.push({ label: "Provider", value: d.provider as string });
    if (d.total_tokens) items.push({ label: "Total Tokens", value: `${(d.total_tokens as number).toLocaleString()}`, mono: true });
    if (d.prompt_tokens) items.push({ label: "Prompt Tokens", value: `${(d.prompt_tokens as number).toLocaleString()}`, mono: true });
    if (d.completion_tokens) items.push({ label: "Completion Tokens", value: `${(d.completion_tokens as number).toLocaleString()}`, mono: true });
    if (duration) items.push({ label: "Duration", value: formatDuration(duration), mono: true });
    if (d.input_preview) items.push({ label: "Input Preview", value: (d.input as string)?.slice(0, 100) || (d.input_preview as string) });
    if (d.output_preview) items.push({ label: "Output Preview", value: (d.output_preview as string)?.slice(0, 100) });
    if (d.name) items.push({ label: "Tool", value: d.name as string });
    if (d.toolName) items.push({ label: "Tool", value: d.toolName as string });
    if (d.round !== undefined) items.push({ label: "Round", value: `${Number(d.round) + 1}`, mono: true });
    if (d.success !== undefined) items.push({ label: "Success", value: d.success ? "true" : "false", mono: true });
    if (d.error) items.push({ label: "Error", value: (d.error as string).slice(0, 200) });
    if (d.pipeline_step) items.push({ label: "Pipeline Step", value: d.pipeline_step as string });
    return items;
  }, [d, event.eventType, duration]);

  return (
    <motion.div
      initial={{ opacity: 0, x: 8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] as const }}
      className={cn("border border-white/[0.06] rounded-3xl bg-surface overflow-hidden", className)}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4 border-b border-white/[0.06]">
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0", bg)}>
          <Icon className={cn("w-4 h-4", color)} strokeWidth={1.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-neutral-200 truncate">
              {event.eventType.replace(":start", "").replace(":end", "")}
            </span>
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded font-mono font-medium",
              event.eventType.endsWith(":start") && !event.eventType.startsWith("agent") && !event.eventType.startsWith("round")
                ? "bg-amber-500/10 text-amber-400"
                : "bg-emerald-500/10 text-emerald-400",
            )}>
              {event.eventType.endsWith(":start") && !event.eventType.startsWith("agent") && !event.eventType.startsWith("round") ? "running" : "completed"}
            </span>
          </div>
          {duration && (
            <div className="flex items-center gap-3 mt-1 text-[11px] text-neutral-500 font-mono tabular-nums">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" strokeWidth={1.5} />
                {formatDuration(duration)}
              </span>
              {!!d.total_tokens && (
                <span>{(d.total_tokens as number).toLocaleString()}t</span>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-6 h-6 rounded-md bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-neutral-500 hover:text-neutral-300 transition-all active:scale-[0.95] text-[10px]"
        >
          X
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-0.5 px-3 pt-3 border-b border-white/[0.06]">
        {tabs.map((tab) => {
          const TabIcon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-[11px] font-medium transition-all",
                isActive
                  ? "bg-white/[0.04] text-neutral-200 border border-white/[0.06] border-b-transparent -mb-px"
                  : "text-neutral-500 hover:text-neutral-400",
              )}
            >
              <TabIcon className="w-3 h-3" strokeWidth={1.5} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="p-4 max-h-[400px] overflow-y-auto">
        {activeTab === "input" && (
          <div className="space-y-3">
            {d.task && (
              <div>
                <h5 className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5 font-semibold">Task</h5>
                <p className="text-xs text-neutral-300 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] rounded-lg p-3 border border-white/[0.06]">
                  {d.task as string}
                </p>
              </div>
            )}
            {d.arguments && (
              <div>
                <h5 className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5 font-semibold">Arguments</h5>
                <pre className="text-xs text-neutral-400 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] rounded-lg p-3 border border-white/[0.06]">
                  {typeof d.arguments === "string" ? d.arguments : JSON.stringify(d.arguments, null, 2)}
                </pre>
              </div>
            )}
            {d.input && (
              <div>
                <h5 className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5 font-semibold">Input</h5>
                <p className="text-xs text-neutral-300 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] rounded-lg p-3 border border-white/[0.06] max-h-[250px] overflow-y-auto">
                  {typeof d.input === "string" ? d.input : JSON.stringify(d.input, null, 2)}
                </p>
              </div>
            )}
            {!d.task && !d.arguments && !d.input && (
              <p className="text-xs text-neutral-600 text-center py-4">No input data available</p>
            )}
          </div>
        )}

        {activeTab === "output" && (
          <div className="space-y-3">
            {d.result && (
              <div>
                <h5 className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5 font-semibold">Result</h5>
                <div className="text-xs text-neutral-300 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] rounded-lg p-3 border border-white/[0.06] max-h-[300px] overflow-y-auto">
                  {(d.result as string).slice(0, 4000)}
                  {(d.result as string).length > 4000 && (
                    <span className="text-neutral-600 block mt-2">...truncated ({((d.result as string).length - 4000).toLocaleString()} more chars)</span>
                  )}
                </div>
              </div>
            )}
            {d.output && (
              <div>
                <h5 className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5 font-semibold">Output</h5>
                <pre className="text-xs text-neutral-400 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] rounded-lg p-3 border border-white/[0.06] max-h-[300px] overflow-y-auto">
                  {(d.output as string).slice(0, 4000)}
                </pre>
              </div>
            )}
            {d.content_preview && (
              <div>
                <h5 className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5 font-semibold">Content Preview</h5>
                <p className="text-xs text-neutral-400 leading-relaxed bg-white/[0.02] rounded-lg p-3 border border-white/[0.06]">
                  {(d.content_preview as string).slice(0, 2000)}
                </p>
              </div>
            )}
            {d.error && (
              <div>
                <h5 className="text-[10px] text-red-400 uppercase tracking-wider mb-1.5 font-semibold">Error</h5>
                <p className="text-xs text-red-300 font-mono leading-relaxed bg-red-500/5 rounded-lg p-3 border border-red-500/20">
                  {d.error as string}
                </p>
              </div>
            )}
            {!d.result && !d.output && !d.content_preview && !d.error && (
              <p className="text-xs text-neutral-600 text-center py-4">No output data available</p>
            )}
          </div>
        )}

        {activeTab === "meta" && (
          <div className="divide-y divide-white/[0.06]">
            {metaItems.length > 0 ? metaItems.map((item) => (
              <MetaRow key={item.label} {...item} />
            )) : (
              <p className="text-xs text-neutral-600 text-center py-4">No metadata available</p>
            )}
          </div>
        )}

        {activeTab === "raw" && (
          <pre className="text-[11px] text-neutral-400 font-mono leading-relaxed whitespace-pre-wrap bg-white/[0.02] rounded-lg p-3 border border-white/[0.06] max-h-[350px] overflow-y-auto">
            {snippet.length > 5000 ? snippet.slice(0, 5000) + "\n\n// ... truncated" : snippet}
          </pre>
        )}
      </div>

      {/* Actions footer */}
      <div className="flex items-center gap-1.5 px-4 py-2.5 border-t border-white/[0.06]">
        <button type="button" onClick={() => navigator.clipboard.writeText(snippet)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all active:scale-[0.95]">
          <Copy className="w-3 h-3" strokeWidth={1.5} />Copy
        </button>
        <button type="button" onClick={() => navigator.clipboard.writeText(window.location.href)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all active:scale-[0.95]">
          <Share2 className="w-3 h-3" strokeWidth={1.5} />Share
        </button>
        <button type="button" onClick={() => { const blob = new Blob([snippet], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "trace-event.json"; a.click(); URL.revokeObjectURL(url); }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all active:scale-[0.95]">
          <Download className="w-3 h-3" strokeWidth={1.5} />Export
        </button>
      </div>
    </motion.div>
  );
}
