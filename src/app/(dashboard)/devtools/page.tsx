"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Network, Target, Container, ChevronRight } from "lucide-react";

const TOOLS = [
  {
    id: "agent-eval",
    label: "Agent Evaluation",
    desc: "Quality scores, verdicts, and trends for agent outputs",
    href: "/agent-eval",
    icon: Target,
    color: "text-emerald-400 bg-emerald-500/10",
  },
  {
    id: "knowledge-graph",
    label: "Knowledge Graph",
    desc: "Interactive codebase graph with community detection",
    href: "/knowledge-graph",
    icon: Network,
    color: "text-zinc-400 bg-zinc-500/10",
  },
  {
    id: "sandbox",
    label: "Sandbox Manager",
    desc: "Container lifecycle, resource gauges, and shell access",
    href: "/sandbox",
    icon: Container,
    color: "text-blue-400 bg-blue-500/10",
  },
];

export default function DevToolsPage() {
  const pathname = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div className="max-w-[1200px] mx-auto px-8 pt-8 pb-12">
      <div className="mb-8">
        <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">Dev Tools</div>
        <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Developer Tools</h1>
        <p className="text-[13px] text-zinc-500 mt-0.5">Agent evaluation, codebase analysis, and sandbox management</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {TOOLS.map((tool) => {
          const Icon = tool.icon;
          const isHovered = hovered === tool.id;
          return (
            <Link key={tool.id} href={tool.href}
              onMouseEnter={() => setHovered(tool.id)} onMouseLeave={() => setHovered(null)}
              className={cn(
                "group relative rounded-[2rem] border p-6 transition-all duration-300",
                "hover:translate-y-[-2px]",
                isHovered
                  ? "border-emerald-500/30 bg-emerald-500/[0.03]"
                  : "border-white/[0.06] bg-white/[0.02]"
              )}>
              <div className="flex items-center gap-4 mb-4">
                <div className={cn("w-12 h-12 rounded-2xl flex items-center justify-center", tool.color)}>
                  <Icon className="w-6 h-6" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[15px] font-semibold text-zinc-100">{tool.label}</div>
                  <div className="text-[12px] text-zinc-600 mt-0.5">{tool.desc}</div>
                </div>
                <ChevronRight className={cn(
                  "w-5 h-5 text-zinc-600 transition-all duration-300",
                  isHovered ? "translate-x-1 text-emerald-400" : ""
                )} strokeWidth={1.5} />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
