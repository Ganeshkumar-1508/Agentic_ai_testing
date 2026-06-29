"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";

const TABS = [
  { label: "Swarm", href: "/ai-ops/swarm" },
  { label: "Plugins", href: "/ai-ops/plugins" },
  { label: "Skills", href: "/ai-ops/skills" },
  { label: "Governance", href: "/ai-ops/governance" },
  { label: "Infrastructure", href: "/ai-ops/infra" },
];

export default function AiOpsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
        <span className="text-xs font-mono text-zinc-600">/ai-ops</span>
      </div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-zinc-400">
            <path d="M8 3v10M3 8h10" />
            <rect x="1.5" y="1.5" width="13" height="13" rx="3" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-medium tracking-tight text-zinc-100">AI Operations</h1>
          <p className="text-sm text-zinc-600 mt-0.5">Agent orchestration, plugins, skills, and infrastructure</p>
        </div>
      </div>

      <nav className="flex gap-1 mb-8 border-b border-zinc-800/50">
        {TABS.map((tab) => {
          const isActive = pathname === tab.href || (tab.href === "/ai-ops/swarm" && pathname === "/ai-ops");
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
                isActive
                  ? "text-emerald-400 border-emerald-400/80"
                  : "text-zinc-500 border-transparent hover:text-zinc-300 hover:border-zinc-600",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
