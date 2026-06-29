"use client";

import { useState, useEffect, useMemo } from "react";
import { usePathname } from "next/navigation";
import { Search, Loader2, CheckCircle2, XCircle, LayoutDashboard, MessageSquare, Clock, Timer, Activity, FileText, Beaker, AlertTriangle, History, GitCompare, GitBranch, Container, Cpu, Server, Settings, SlidersHorizontal, Wrench, BookOpen, Radio, Briefcase } from "lucide-react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";

const BREADCRUMB_LABELS: Record<string, { icon: any; label: string }> = {
  "/dashboard": { icon: LayoutDashboard, label: "Dashboard" },
  "/chat": { icon: MessageSquare, label: "Chat" },
  "/sessions": { icon: Clock, label: "Sessions" },
  "/pipeline": { icon: Activity, label: "Pipeline" },
  "/test-cases": { icon: Beaker, label: "Test Cases" },
  "/flaky-tests": { icon: AlertTriangle, label: "Flaky Tests" },
  "/history": { icon: History, label: "Run History" },
  "/history/compare": { icon: GitCompare, label: "Run Comparison" },
  "/traceability": { icon: GitBranch, label: "Traceability" },
  "/sandbox": { icon: Container, label: "Sandbox" },
  "/ai-ops": { icon: Cpu, label: "AI Ops" },
  "/tools": { icon: Wrench, label: "Tools" },
  "/project": { icon: SlidersHorizontal, label: "Project" },
  "/settings": { icon: Settings, label: "Settings" },
  "/activity": { icon: Radio, label: "Activity" },
  "/jobs": { icon: Briefcase, label: "Jobs" },
};

function Breadcrumbs() {
  const pathname = usePathname();
  const segments = useMemo(() => {
    const segs = pathname.split("/").filter(Boolean);
    return segs.map((seg, i) => {
      const path = "/" + segs.slice(0, i + 1).join("/");
      const info = BREADCRUMB_LABELS[path];
      return {
        label: info?.label || seg.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        path,
      };
    });
  }, [pathname]);

  return (
    <nav className="flex items-center gap-1.5 text-sm">
      {segments.map((seg, i) => (
        <span key={seg.path} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-zinc-700 text-[10px]">/</span>}
          <span className={cn(
            "capitalize tracking-tight",
            i === segments.length - 1 ? "text-foreground font-semibold" : "text-muted-foreground"
          )}>
            {seg.label}
          </span>
        </span>
      ))}
    </nav>
  );
}

function RealtimeClock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString("en-US", { hour12: false }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="text-[11px] font-mono text-zinc-500 tabular-nums">{time}</span>;
}

export default function AppHeader() {
  const handleSearchClick = () => {
    document.dispatchEvent(new CustomEvent("opencmdk"));
  };

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between px-8 py-3.5 border-b border-border bg-background/80 backdrop-blur-sm">
      <Breadcrumbs />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSearchClick}
          className="relative hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-zinc-800/50 bg-zinc-900/60 text-xs text-zinc-500 hover:text-zinc-300 hover:border-zinc-700/50 transition-colors w-48"
        >
          <Search className="w-3.5 h-3.5" strokeWidth={1.5} />
          <span>Search...</span>
          <kbd className="ml-auto text-[10px] text-zinc-600 font-mono">&#8984;K</kbd>
        </button>

        <RealtimeClock />

        <PipelineBadge />
      </div>
    </header>
  );
}

function PipelineBadge() {
  const status = usePipelineStore((s) => s.status);
  const totalTokens = usePipelineStore((s) => s.totalTokens);
  const tools = usePipelineStore((s) => s.tools);

  if (status === "idle") return null;

  if (status === "running") {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-blue-400 bg-blue-500/10 border border-blue-500/15 rounded-lg px-2 py-1">
        <Loader2 size={10} className="animate-spin" strokeWidth={2} />
        <span>Pipeline running</span>
        <span className="text-blue-400/60 font-mono tabular-nums">{tools.length} tools</span>
      </div>
    );
  }

  if (status === "completed") {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/15 rounded-lg px-2 py-1">
        <CheckCircle2 size={10} strokeWidth={2} />
        <span>Completed</span>
        <span className="text-emerald-400/60 font-mono tabular-nums">{totalTokens.toLocaleString()}t</span>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-red-400 bg-red-500/10 border border-red-500/15 rounded-lg px-2 py-1">
        <XCircle size={10} strokeWidth={2} />
        <span>Failed</span>
      </div>
    );
  }

  return null;
}
