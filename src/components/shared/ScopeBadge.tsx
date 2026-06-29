"use client";

import { Globe, Folder } from "lucide-react";

interface ScopeBadgeProps {
  scope?: string;
}

export function ScopeBadge({ scope }: ScopeBadgeProps) {
  if (!scope || scope === "project") {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-zinc-800/60 text-zinc-500 font-mono">
        <Folder className="w-2.5 h-2.5" strokeWidth={2} />
        P
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 font-mono">
      <Globe className="w-2.5 h-2.5" strokeWidth={2} />
      G
    </span>
  );
}
