"use client";

import { useState, useRef, useEffect } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxEvents } from "@/lib/services/sandbox-client";
import type { SandboxEvent } from "@/lib/types/sandbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Terminal, RotateCcw } from "lucide-react";

export function SandboxTerminal() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const [events, setEvents] = useState<SandboxEvent[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const status = usePipelineStore((s) => s.status);

  useEffect(() => {
    if (!sessionId) return;
    const load = async () => {
      const data = await fetchSandboxEvents(sessionId);
      if (data.length > 0) setEvents(data);
    };
    load();
    if (status === "running") {
      const interval = setInterval(load, 3000);
      return () => clearInterval(interval);
    }
  }, [sessionId, status]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const typeColors: Record<string, string> = {
    agent: "text-zinc-400",
    tool: "text-emerald-400",
    exec: "text-amber-400",
    pass: "text-emerald-400",
    fail: "text-red-400",
    info: "text-neutral-500",
  };

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.04]">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />
          <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">Terminal</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-neutral-600">{events.length} events</span>
          <button type="button" onClick={async () => { if (sessionId) { const data = await fetchSandboxEvents(sessionId); setEvents(data); } }} className="text-neutral-600 hover:text-neutral-300 transition-colors">
            <RotateCcw className="w-3 h-3" strokeWidth={1.5} />
          </button>
        </div>
      </div>
      <div className="bg-zinc-950 rounded-b-3xl">
        <ScrollArea ref={scrollRef} className="h-[200px]">
          <div className="p-4 font-mono text-[11px] leading-relaxed">
            {events.length === 0 && (
              <div className="text-neutral-600 text-center py-8">Waiting for agent activity...</div>
            )}
            {events.map((ev, i) => (
              <div key={i} className="flex gap-2 py-0.5">
                <span className={`shrink-0 w-10 text-[9px] uppercase tracking-wider font-semibold ${typeColors[ev.type] || "text-neutral-500"}`}>
                  {ev.type}
                </span>
                <span className="text-neutral-300">{ev.message}</span>
                {ev.detail && <span className="text-neutral-600 truncate">{ev.detail}</span>}
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
